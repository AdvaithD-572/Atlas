import time
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel

from atlas.errors import AtlasError
from atlas.providers import GroundedAnswer, KnowledgeProvider
from atlas.retrieval import SearchRequest, SearchResult
from atlas.schemas import Passage
from atlas.vector_retrieval import VectorSearchResult


class EvidenceStore(Protocol):
    def search(self, owner: str, query: SearchRequest) -> SearchResult: ...
    def citation(self, owner: str, chunk_id: str) -> Passage: ...


class AnswerResult(BaseModel):
    answer: GroundedAnswer
    passages: list[Passage]
    retrieval_version: str
    duration_ms: float
    retrieval: SearchResult | VectorSearchResult


def answer_question(
    store: EvidenceStore,
    provider: KnowledgeProvider,
    owner: str,
    query: SearchRequest,
    retrieve: Callable[[str, SearchRequest], SearchResult | VectorSearchResult] | None = None,
) -> AnswerResult:
    started = time.perf_counter()
    retrieval = (retrieve or store.search)(
        owner, query.model_copy(update={"limit": min(query.limit, 5)})
    )
    evidence: list[Passage] = []
    size = 0
    for passage in retrieval.passages:
        if size + len(passage.text) <= 12000:
            evidence.append(passage)
            size += len(passage.text)
    answer = provider.generate(query.question, evidence)
    # Provider calls can take seconds. Revalidate every source after inference so an
    # update/deletion while the model ran cannot return an already stale citation.
    for passage in evidence:
        try:
            current = store.citation(owner, passage.id)
        except AtlasError as exc:
            if exc.status == 404:
                raise AtlasError(
                    "evidence_changed", "Sources changed. Run the question again.", 409
                ) from None
            raise
        if current != passage:
            raise AtlasError("evidence_changed", "Sources changed. Run the question again.", 409)
    return AnswerResult(
        answer=answer,
        passages=evidence,
        retrieval_version=retrieval.retrieval_version,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        retrieval=retrieval,
    )
