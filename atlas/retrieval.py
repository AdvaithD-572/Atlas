import re
import time
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from atlas.database import connection
from atlas.schemas import Passage


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=512)
    limit: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    status: Literal["evidence_found", "insufficient_evidence"]
    mode: Literal["lexical_excerpts"] = "lexical_excerpts"
    answer: None = None
    retrieval_version: Literal["fts5-overlap-v1", "postgres-simple-overlap-v1"] = "fts5-overlap-v1"
    passages: list[Passage]
    candidate_limit: int = 200
    truncated: bool
    duration_ms: float


def terms(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def lexical_search(database_path: Path, owner: str, query: SearchRequest) -> SearchResult:
    started = time.perf_counter()
    tokens = list(dict.fromkeys(terms(query.question)))[:32]
    passages: list[Passage] = []
    truncated = False
    if tokens:
        # Token characters exclude quote/operators, and MATCH remains a bound value.
        expression = " OR ".join('"' + token + '"' for token in tokens)
        with connection(database_path) as db:
            rows = db.execute(
                """SELECT c.*, d.source_key, d.version FROM chunk_search
                JOIN chunks c ON c.rowid=chunk_search.rowid
                JOIN documents d ON d.id=c.document_id
                WHERE chunk_search MATCH ? AND d.owner=?
                ORDER BY d.source_key, c.ordinal LIMIT 201""",
                (expression, owner),
            ).fetchall()
        truncated = len(rows) > 200
        candidates = [Passage.model_validate(dict(row)) for row in rows[:200]]

        def rank(passage: Passage) -> tuple[float, float, str, int]:
            counts = Counter(terms(passage.text))
            # No global IDF/statistics: another owner's corpus cannot affect this score.
            coverage = sum(token in counts for token in tokens) / len(tokens)
            density = sum(counts[token] for token in tokens) / max(sum(counts.values()), 1)
            return (-coverage, -density, passage.source_key, passage.ordinal)

        passages = sorted(candidates, key=rank)[: query.limit]
    return SearchResult(
        status="evidence_found" if passages else "insufficient_evidence",
        passages=passages,
        truncated=truncated,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
    )
