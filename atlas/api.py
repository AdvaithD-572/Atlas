import asyncio
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from atlas.errors import AtlasError
from atlas.ingestion import MEDIA_TYPES
from atlas.postgres import IngestionJob, PostgresDocumentService
from atlas.questions import AnswerResult, answer_question
from atlas.retrieval import SearchRequest, SearchResult
from atlas.schemas import Document, Page, Passage
from atlas.security import principal
from atlas.services import DocumentService
from atlas.vector_retrieval import PostgresVectorService, VectorIndexResult, VectorSearchResult

router = APIRouter(prefix="/v1")
Owner = Annotated[str, Depends(principal)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]
RetrievalMode = Literal["lexical", "vector", "hybrid"]


def service(request: Request) -> DocumentService | PostgresDocumentService:
    return cast(DocumentService | PostgresDocumentService, request.app.state.documents)


Service = Annotated[DocumentService | PostgresDocumentService, Depends(service)]


async def read_bounded(request: Request, maximum: int) -> bytes:
    body = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(body) + len(chunk) > maximum:
                    raise AtlasError("payload_too_large", "Request exceeds the size limit.", 413)
                body.extend(chunk)
    except TimeoutError as exc:
        raise AtlasError("upload_timeout", "Request timed out.", 408) from exc
    return bytes(body)


@router.put("/documents/{key}", response_model=Document)
async def upload(
    request: Request,
    response: Response,
    owner: Owner,
    documents: Service,
    key: Annotated[str, Path(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}$")],
) -> Document:
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in MEDIA_TYPES:
        raise AtlasError("unsupported_type", "Use PDF, HTML, Markdown or plain text.", 415)
    body = await read_bounded(request, documents.settings.max_upload_bytes)
    result, created = await run_in_threadpool(documents.put, owner, key, body, media)
    response.status_code = 201 if created else 200
    response.headers["Location"] = f"/v1/documents/{result.id}"
    return result


@router.get("/documents", response_model=Page[Document])
def list_documents(
    owner: Owner, documents: Service, limit: Limit = 20, offset: Offset = 0
) -> Page[Document]:
    return documents.list(owner, limit, offset)


@router.get("/documents/{document_id}", response_model=Document)
def get_document(document_id: UUID, owner: Owner, documents: Service) -> Document:
    return documents.get(owner, str(document_id))


@router.get("/documents/{document_id}/chunks", response_model=Page[Passage])
def get_chunks(
    document_id: UUID, owner: Owner, documents: Service, limit: Limit = 20, offset: Offset = 0
) -> Page[Passage]:
    return documents.passages(owner, str(document_id), limit, offset)


@router.get("/citations/{chunk_id}", response_model=Passage)
def get_citation(chunk_id: UUID, owner: Owner, documents: Service) -> Passage:
    return documents.citation(owner, str(chunk_id))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, owner: Owner, documents: Service) -> Response:
    documents.delete(owner, str(document_id))
    return Response(status_code=204)


def vector_service(request: Request) -> PostgresVectorService:
    vectors = request.app.state.vectors
    if vectors is None:
        raise AtlasError("vector_disabled", "Vector retrieval is not enabled.", 503)
    return cast(PostgresVectorService, vectors)


@router.post("/search", response_model=SearchResult | VectorSearchResult)
async def search(
    request: Request, owner: Owner, documents: Service, mode: RetrievalMode = "lexical"
) -> SearchResult | VectorSearchResult:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise AtlasError("unsupported_type", "Search requires application/json.", 415)
    raw = await read_bounded(request, 8192)
    try:
        payload = SearchRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise AtlasError("validation_error", "Invalid search request.", 422) from exc
    if mode == "lexical":
        return await run_in_threadpool(documents.search, owner, payload)
    return await run_in_threadpool(vector_service(request).search, owner, payload, mode)


class Capabilities(BaseModel):
    generation_enabled: bool
    retrieval_modes: list[RetrievalMode] = ["lexical"]
    backend: Literal["sqlite", "postgres"]


@router.get("/capabilities", response_model=Capabilities)
def capabilities(request: Request, owner: Owner, documents: Service) -> Capabilities:
    return Capabilities(
        generation_enabled=request.app.state.settings.generation_enabled,
        retrieval_modes=["lexical", "vector", "hybrid"]
        if request.app.state.vectors is not None
        else ["lexical"],
        backend="postgres" if isinstance(documents, PostgresDocumentService) else "sqlite",
    )


@router.post("/answers", response_model=AnswerResult)
async def answers(
    request: Request, owner: Owner, documents: Service, mode: RetrievalMode = "lexical"
) -> AnswerResult:
    if not request.app.state.settings.generation_enabled:
        raise AtlasError("generation_disabled", "Local generation is not enabled.", 503)
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise AtlasError("unsupported_type", "Questions require application/json.", 415)
    raw = await read_bounded(request, 8192)
    try:
        payload = SearchRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise AtlasError("validation_error", "Invalid question request.", 422) from exc
    if mode == "lexical":
        return await run_in_threadpool(
            answer_question, documents, request.app.state.provider, owner, payload
        )
    vectors = vector_service(request)
    return await run_in_threadpool(
        answer_question,
        documents,
        request.app.state.provider,
        owner,
        payload,
        lambda scope, query: vectors.search(scope, query, mode),
    )


@router.post("/documents/{document_id}/vector-index", response_model=VectorIndexResult)
def index_vectors(document_id: UUID, request: Request, owner: Owner) -> VectorIndexResult:
    return vector_service(request).index_document(owner, str(document_id))


@router.post("/ingestions/{key}", response_model=IngestionJob, status_code=202)
async def enqueue_ingestion(
    request: Request,
    owner: Owner,
    documents: Service,
    key: Annotated[str, Path(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}$")],
) -> IngestionJob:
    if not isinstance(documents, PostgresDocumentService):
        raise AtlasError("queue_unavailable", "Background ingestion requires PostgreSQL.", 503)
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    raw = await read_bounded(request, documents.settings.max_upload_bytes)
    return await run_in_threadpool(documents.enqueue, owner, key, raw, media)


@router.get("/jobs/{job_id}", response_model=IngestionJob)
def job(job_id: UUID, owner: Owner, documents: Service) -> IngestionJob:
    if not isinstance(documents, PostgresDocumentService):
        raise AtlasError("queue_unavailable", "Background ingestion requires PostgreSQL.", 503)
    return documents.job(owner, str(job_id))
