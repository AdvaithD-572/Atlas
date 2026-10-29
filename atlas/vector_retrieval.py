"""Bounded exact cosine baseline and explicit RRF, with no cross-owner cache."""

import json
import math
import threading
import time
from typing import Literal, Protocol

from pydantic import BaseModel

from atlas.errors import AtlasError
from atlas.postgres import PASSAGE_SELECT, PostgresDocumentService, db_connection, owner_lock
from atlas.providers import Embeddings
from atlas.retrieval import SearchRequest
from atlas.schemas import Passage

MAX_INDEX_CHUNKS = 128
MAX_SEARCH_CHUNKS = 10000
FUSION_DEPTH = 20


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> Embeddings: ...


class VectorIndexResult(BaseModel):
    document_id: str
    document_version: int
    chunk_count: int
    embedding_model: str
    model_digest: str
    dimensions: int
    index_version: str = "cosine-exact-v1"


class VectorSearchResult(BaseModel):
    status: Literal["evidence_found", "insufficient_evidence"]
    mode: Literal["vector", "hybrid"]
    passages: list[Passage]
    embedding_model: str
    model_digest: str
    dimensions: int
    indexed_chunks: int
    unindexed_chunks: int
    retrieval_version: str
    candidate_limit: int = MAX_SEARCH_CHUNKS
    truncated: bool = False
    rrf_rank_constant: int | None = None
    fusion_depth: int | None = None
    duration_ms: float


def reciprocal_rank_fusion(
    rankings: list[list[str]], rank_constant: int = 60, limit: int = 20
) -> list[tuple[str, float]]:
    if rank_constant < 1 or not 1 <= limit <= 40:
        raise ValueError("Invalid fusion parameters.")
    scores: dict[str, float] = {}
    for ranking in rankings:
        # A duplicated ID contributes at most once in each input ranking.
        for rank, identifier in enumerate(dict.fromkeys(ranking), 1):
            scores[identifier] = scores.get(identifier, 0) + 1 / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]


def validated_embedding_identity(result: Embeddings, count: int) -> tuple[str, str, int]:
    if len(result.vectors) != count or not result.vectors:
        raise AtlasError("provider_invalid", "Embedding count does not match.", 502)
    dimensions = len(result.vectors[0])
    if (
        not 1 <= dimensions <= 4096
        or not 1 <= len(result.model) <= 100
        or len(result.model_digest) != 64
        or any(c not in "0123456789abcdef" for c in result.model_digest)
    ):
        raise AtlasError("provider_invalid", "Embedding metadata is invalid.", 502)
    for vector in result.vectors:
        # pgvector stores float32; constrain before SQL conversion.
        if (
            len(vector) != dimensions
            or any(not math.isfinite(v) or abs(v) > 3.4e38 for v in vector)
            or not math.isfinite(sum(v * v for v in vector))
            or sum(v * v for v in vector) <= 1e-70
        ):
            raise AtlasError("provider_invalid", "Embedding values are invalid.", 502)
    return result.model, result.model_digest, dimensions


class PostgresVectorService:
    def __init__(self, documents: PostgresDocumentService, provider: EmbeddingProvider) -> None:
        self.documents = documents
        self.provider = provider
        self._index_slots = threading.BoundedSemaphore(1)

    def index_document(self, owner: str, document_id: str) -> VectorIndexResult:
        if not self._index_slots.acquire(blocking=False):
            raise AtlasError("index_busy", "Vector indexing is busy. Retry later.", 503)
        try:
            return self._index_document(owner, document_id)
        finally:
            self._index_slots.release()

    def _index_document(self, owner: str, document_id: str) -> VectorIndexResult:
        started = time.monotonic()
        document = self.documents.get(owner, document_id)
        if document.chunk_count > MAX_INDEX_CHUNKS:
            raise AtlasError(
                "vector_index_limit",
                "Vector indexing supports at most 128 passages per document.",
                413,
            )
        with db_connection(self.documents.dsn) as db:
            owner_lock(db, owner)
            rows = db.execute(
                PASSAGE_SELECT + " WHERE d.owner=%s AND d.id=%s ORDER BY c.ordinal",
                (owner, document_id),
            ).fetchall()
        passages = [Passage.model_validate(row) for row in rows]
        if not passages or any(p.version != document.version for p in passages):
            raise AtlasError("evidence_changed", "Sources changed. Retry indexing.", 409)
        identity: tuple[str, str, int] | None = None
        values: list[list[float]] = []
        for offset in range(0, len(passages), 32):
            if time.monotonic() - started > 120:
                raise AtlasError("index_timeout", "Vector indexing exceeded its time budget.", 503)
            batch = passages[offset : offset + 32]
            result = self.provider.embed([p.text for p in batch])
            current_identity = validated_embedding_identity(result, len(batch))
            if identity is not None and current_identity != identity:
                raise AtlasError(
                    "embedding_changed", "Embedding configuration changed. Retry.", 409
                )
            identity = current_identity
            values.extend(result.vectors)
        assert identity is not None
        model, digest, dimensions = identity
        with db_connection(self.documents.dsn) as db:
            owner_lock(db, owner)
            current = db.execute(
                PASSAGE_SELECT + " WHERE d.owner=%s AND d.id=%s ORDER BY c.ordinal",
                (owner, document_id),
            ).fetchall()
            if [Passage.model_validate(row) for row in current] != passages:
                raise AtlasError("evidence_changed", "Sources changed. Retry indexing.", 409)
            with db.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO chunk_embeddings
                    (chunk_id,model,model_digest,dimensions,embedding) VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(chunk_id) DO UPDATE SET model=excluded.model,
                    model_digest=excluded.model_digest,dimensions=excluded.dimensions,
                    embedding=excluded.embedding,indexed_at=clock_timestamp()""",
                    [
                        (p.id, model, digest, dimensions, json.dumps(vector, allow_nan=False))
                        for p, vector in zip(passages, values, strict=True)
                    ],
                )
        return VectorIndexResult(
            document_id=document_id,
            document_version=document.version,
            chunk_count=len(passages),
            embedding_model=model,
            model_digest=digest,
            dimensions=dimensions,
        )

    def search(
        self, owner: str, query: SearchRequest, mode: Literal["vector", "hybrid"] = "vector"
    ) -> VectorSearchResult:
        started = time.perf_counter()
        embedded = self.provider.embed([query.question])
        model, digest, dimensions = validated_embedding_identity(embedded, 1)
        with db_connection(self.documents.dsn) as db:
            owner_lock(db, owner)
            stats = db.execute(
                """SELECT count(*) AS total,count(e.chunk_id) AS indexed
                FROM chunks c JOIN documents d ON d.id=c.document_id
                LEFT JOIN chunk_embeddings e ON e.chunk_id=c.id
                AND e.model=%s AND e.model_digest=%s AND e.dimensions=%s
                WHERE d.owner=%s""",
                (model, digest, dimensions, owner),
            ).fetchone()
            assert stats is not None
            if stats["indexed"] > MAX_SEARCH_CHUNKS:
                raise AtlasError(
                    "search_limit", "Vector search corpus exceeds the work limit.", 413
                )
            rows = db.execute(
                """WITH authorized AS MATERIALIZED (
                SELECT c.id,c.document_id,c.ordinal,c.start,c."end",c.text,c.page_number,c.heading,
                d.source_key,d.version,e.embedding FROM chunks c
                JOIN documents d ON d.id=c.document_id
                JOIN chunk_embeddings e ON e.chunk_id=c.id
                WHERE d.owner=%s AND e.model=%s AND e.model_digest=%s AND e.dimensions=%s)
                SELECT * FROM authorized
                ORDER BY embedding OPERATOR(public.<=>) %s::public.vector,source_key,ordinal
                LIMIT %s""",
                (owner, model, digest, dimensions, json.dumps(embedded.vectors[0]), FUSION_DEPTH),
            ).fetchall()
        passages = [Passage.model_validate(row) for row in rows]
        truncated = False
        if mode == "hybrid":
            lexical = self.documents.search(owner, query.model_copy(update={"limit": FUSION_DEPTH}))
            truncated = lexical.truncated
            by_id = {p.id: p for p in passages + lexical.passages}
            fused = reciprocal_rank_fusion(
                [[p.id for p in passages], [p.id for p in lexical.passages]], limit=query.limit
            )
            passages = [by_id[identifier] for identifier, _ in fused]
        else:
            passages = passages[: query.limit]
        # Lexical and vector reads have separate snapshots. Recheck sources before return.
        for passage in passages:
            try:
                if self.documents.citation(owner, passage.id) != passage:
                    raise AtlasError("evidence_changed", "Sources changed. Search again.", 409)
            except AtlasError as exc:
                if exc.status == 404:
                    raise AtlasError(
                        "evidence_changed", "Sources changed. Search again.", 409
                    ) from None
                raise
        return VectorSearchResult(
            status="evidence_found" if passages else "insufficient_evidence",
            mode=mode,
            passages=passages,
            embedding_model=model,
            model_digest=digest,
            dimensions=dimensions,
            indexed_chunks=stats["indexed"],
            unindexed_chunks=stats["total"] - stats["indexed"],
            retrieval_version="rrf60-depth20-v1" if mode == "hybrid" else "cosine-exact-v1",
            truncated=truncated,
            rrf_rank_constant=60 if mode == "hybrid" else None,
            fusion_depth=FUSION_DEPTH if mode == "hybrid" else None,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
