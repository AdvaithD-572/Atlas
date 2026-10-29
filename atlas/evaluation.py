"""Deterministic evaluation tools; no built-in benchmark or model judge."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVALUATOR_VERSION = "atlas-eval-v1"
DISTRIBUTION = {
    "direct": 25,
    "multi_document": 20,
    "unanswerable": 20,
    "conflicting_outdated": 15,
    "difficult": 20,
}
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Nonblank = Annotated[str, Field(min_length=1, max_length=4000)]


class DatasetCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    case_id: Identifier
    category: Literal[
        "direct", "multi_document", "unanswerable", "conflicting_outdated", "difficult"
    ]
    question: str = Field(min_length=1, max_length=512)
    answerable: bool
    expected_facts: list[Nonblank]
    relevant_passages: dict[Identifier, Digest]
    scoring_notes: Nonblank
    human_reviewer: Identifier | None
    reviewed_at: str | None
    synthetic: bool = False

    @field_validator("question", "scoring_notes")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if any(not fact.strip() for fact in self.expected_facts):
            raise ValueError("Expected facts must not be blank")
        if self.answerable and (not self.expected_facts or not self.relevant_passages):
            raise ValueError("Answerable cases require facts and passages")
        if self.category == "unanswerable" and self.answerable:
            raise ValueError("Unanswerable category cannot be answerable")
        if (self.human_reviewer is None) != (self.reviewed_at is None):
            raise ValueError("Reviewer and review timestamp must be supplied together")
        if self.reviewed_at is not None:
            stamp = datetime.fromisoformat(self.reviewed_at)
            if stamp.tzinfo is None or stamp > datetime.now(UTC):
                raise ValueError("Review timestamp needs timezone and cannot be in the future")
        return self


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    mode: Literal["lexical", "vector", "hybrid"] = "lexical"
    k: int = Field(default=5, ge=1, le=20)
    retrieval_version: Literal[
        "fts5-overlap-v1", "postgres-simple-overlap-v1", "cosine-exact-v1", "rrf60-depth20-v1"
    ] = "fts5-overlap-v1"
    experiment_id: Identifier = "lexical-baseline"
    corpus_version: Identifier = "unspecified"
    chunking_version: Identifier = "unspecified"
    model_id: str | None = None
    model_digest: Digest | None = None
    generate_answers: bool = False
    generation_model_id: str | None = Field(default=None, min_length=1, max_length=100)
    generation_model_digest: Digest | None = None
    prompt_version: Identifier | None = None

    @model_validator(mode="after")
    def pinned_mode(self) -> Self:
        if self.generate_answers:
            if (
                not self.generation_model_id
                or self.generation_model_digest is None
                or self.prompt_version is None
                or self.k > 5
            ):
                raise ValueError("Answer runs require pinned generation identity/prompt and k <= 5")
        elif any(
            value is not None
            for value in (
                self.generation_model_id,
                self.generation_model_digest,
                self.prompt_version,
            )
        ):
            raise ValueError("Generation configuration requires an answer run")
        if self.mode == "lexical":
            if self.retrieval_version not in {"fts5-overlap-v1", "postgres-simple-overlap-v1"}:
                raise ValueError("Lexical retrieval version required")
            if self.model_id is not None or self.model_digest is not None:
                raise ValueError("Lexical search has no embedding model")
        else:
            expected = "cosine-exact-v1" if self.mode == "vector" else "rrf60-depth20-v1"
            if self.retrieval_version != expected or not self.model_id or self.model_digest is None:
                raise ValueError("Semantic search requires pinned version, model and digest")
        return self


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    retrieved_passage_ids: list[Identifier]
    cited_passage_ids: list[Identifier] | None = None
    abstained: bool | None = None
    answer_correctness: float | None = Field(default=None, ge=0, le=1)
    faithfulness: float | None = Field(default=None, ge=0, le=1)
    rating_reviewer: Identifier | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    truncated: bool = False

    @model_validator(mode="after")
    def require_reviewer(self) -> Self:
        if (
            self.answer_correctness is not None or self.faithfulness is not None
        ) and self.rating_reviewer is None:
            raise ValueError("Answer ratings require an actual reviewer")
        return self


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def corpus_digest(corpus: Mapping[str, str]) -> str:
    """Hash canonical passage-ID -> original document content-SHA256 mapping."""
    return _digest(dict(corpus))


@dataclass(frozen=True)
class FrozenDataset:
    cases: tuple[DatasetCase, ...]
    dataset_hash: str
    corpus_hash: str
    cases_hash: str
    official: bool


def load_dataset(
    path: Path,
    *,
    expected_dataset_hash: str,
    expected_corpus_hash: str,
    corpus: Mapping[str, str],
    official: bool = False,
) -> FrozenDataset:
    """Validate pinned bytes and source membership before any experiment executes."""
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Dataset exceeds 10 MiB limit")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_dataset_hash:
        raise ValueError("Frozen dataset hash mismatch")
    if corpus_digest(corpus) != expected_corpus_hash:
        raise ValueError("Frozen corpus hash mismatch")
    cases = tuple(
        DatasetCase.model_validate_json(line)
        for line in raw.decode("utf-8-sig").splitlines()
        if line.strip()
    )
    if not cases:
        raise ValueError("Dataset is empty")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Dataset contains duplicate case IDs")
    for case in cases:
        if any(corpus.get(passage) != sha for passage, sha in case.relevant_passages.items()):
            raise ValueError("Relevant passage source hash missing or mismatched")
    if official:
        if len(cases) < 100:
            raise ValueError("Official benchmark requires at least 100 cases")
        if any(case.synthetic or case.human_reviewer is None for case in cases):
            raise ValueError("Official benchmark requires real human-reviewed cases")
        counts: Counter[str] = Counter(case.category for case in cases)
        if any(
            counts[category] * 100 != percent * len(cases)
            for category, percent in DISTRIBUTION.items()
        ):
            raise ValueError("Official benchmark category distribution must be 25/20/20/15/20")
    return FrozenDataset(
        cases,
        digest,
        expected_corpus_hash,
        _digest([case.model_dump() for case in cases]),
        official,
    )


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float | None:
    if k < 1:
        raise ValueError("k must be positive")
    return len(set(retrieved[:k]) & relevant) / len(relevant) if relevant else None


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str], k: int) -> float | None:
    if k < 1:
        raise ValueError("k must be positive")
    if not relevant:
        return None
    return next((1 / rank for rank, item in enumerate(retrieved[:k], 1) if item in relevant), 0.0)


def citation_metrics(cited: Sequence[str], relevant: set[str]) -> dict[str, float | None]:
    citations = set(cited)
    hits = len(citations & relevant)
    return {
        "precision": hits / len(citations) if citations else None,
        "recall": hits / len(relevant) if relevant else None,
    }


def abstention_metrics(values: Sequence[tuple[bool, bool]]) -> dict[str, int | float | None]:
    """Input pairs are (answerable, abstained); positive means should abstain."""
    tp = sum(not answerable and abstained for answerable, abstained in values)
    fp = sum(answerable and abstained for answerable, abstained in values)
    tn = sum(answerable and not abstained for answerable, abstained in values)
    fn = sum(not answerable and not abstained for answerable, abstained in values)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "accuracy": (tp + tn) / len(values) if values else None,
        "count": len(values),
    }


def _mean(values: Sequence[float | None]) -> dict[str, float | int | None]:
    present = [value for value in values if value is not None]
    return {"value": sum(present) / len(present) if present else None, "count": len(present)}


def run_experiment(
    dataset: FrozenDataset,
    config: ExperimentConfig,
    observe: Callable[[DatasetCase, ExperimentConfig], Observation],
) -> dict[str, Any]:
    """Run serially; callback owns provider timeouts and authorization context."""
    if _digest([case.model_dump() for case in dataset.cases]) != dataset.cases_hash:
        raise ValueError("Frozen dataset was modified")
    rows: list[dict[str, Any]] = []
    abstentions: list[tuple[bool, bool]] = []
    for case in dataset.cases:
        started = time.perf_counter()
        row: dict[str, Any] = {
            "case_id": case.case_id,
            "category": case.category,
            "failed": False,
            "error": None,
        }
        try:
            observation = observe(case, config)
            relevant = set(case.relevant_passages)
            citations = (
                citation_metrics(observation.cited_passage_ids, relevant)
                if observation.cited_passage_ids is not None
                else {"precision": None, "recall": None}
            )
            row.update(observation.model_dump())
            row.update(
                retrieval_recall_at_k=recall_at_k(
                    observation.retrieved_passage_ids, relevant, config.k
                ),
                retrieval_mrr=reciprocal_rank(
                    observation.retrieved_passage_ids, relevant, config.k
                ),
                citation_precision=citations["precision"],
                citation_recall=citations["recall"],
            )
            if observation.abstained is not None:
                abstentions.append((case.answerable, observation.abstained))
        except Exception:
            # Error text can contain credentials, questions, documents or provider payloads.
            row.update(failed=True, error="observation_failed")
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        rows.append(row)
    latencies = sorted(row["latency_ms"] for row in rows)
    metrics = (
        "retrieval_recall_at_k",
        "retrieval_mrr",
        "citation_precision",
        "citation_recall",
        "answer_correctness",
        "faithfulness",
    )
    summary: dict[str, Any] = {
        metric: _mean([row.get(metric) for row in rows]) for metric in metrics
    }
    summary.update(
        count=len(rows),
        failures=sum(row["failed"] for row in rows),
        abstention=abstention_metrics(abstentions),
        latency_ms={f"p{p}": latencies[math.ceil(p / 100 * len(rows)) - 1] for p in (50, 95, 99)},
    )
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "dataset_hash": dataset.dataset_hash,
        "corpus_hash": dataset.corpus_hash,
        "official": dataset.official,
        "config": config.model_dump(),
        "config_hash": _digest(config.model_dump()),
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "cases": rows,
    }


def lexical_http_observer(
    client: Any, headers: Mapping[str, str]
) -> Callable[[DatasetCase, ExperimentConfig], Observation]:
    """Authenticated query observer; historical function name retained for callers."""
    from atlas.questions import AnswerResult
    from atlas.retrieval import SearchResult
    from atlas.vector_retrieval import VectorSearchResult

    def observe(case: DatasetCase, config: ExperimentConfig) -> Observation:
        endpoint = "/v1/answers" if config.generate_answers else "/v1/search"
        response = client.post(
            endpoint if config.mode == "lexical" else f"{endpoint}?mode={config.mode}",
            headers=dict(headers),
            json={"question": case.question, "limit": config.k},
        )
        response.raise_for_status()
        answer_result = (
            AnswerResult.model_validate(response.json()) if config.generate_answers else None
        )
        result = (
            answer_result.retrieval
            if answer_result is not None
            else (
                SearchResult.model_validate(response.json())
                if config.mode == "lexical"
                else VectorSearchResult.model_validate(response.json())
            )
        )
        if result.retrieval_version != config.retrieval_version:
            raise ValueError("Retrieval version mismatch")
        if isinstance(result, VectorSearchResult):
            if (
                result.mode != config.mode
                or result.embedding_model != config.model_id
                or result.model_digest != config.model_digest
                or result.unindexed_chunks != 0
            ):
                raise ValueError("Embedding identity or corpus coverage mismatch")
        elif config.mode != "lexical":
            raise ValueError("Retrieval mode mismatch")
        if answer_result is not None:
            answer = answer_result.answer
            no_inference = (
                not result.passages
                and not answer_result.passages
                and answer.status == "insufficient_evidence"
                and not answer.claims
                and answer.model_digest is None
            )
            if (
                answer.model != config.generation_model_id
                or answer.prompt_version != config.prompt_version
                or (not no_inference and answer.model_digest != config.generation_model_digest)
            ):
                raise ValueError("Generation identity mismatch")
            evidence = {passage.id: passage for passage in answer_result.passages}
            retrieved = {passage.id: passage for passage in result.passages}
            if (
                answer_result.retrieval_version != result.retrieval_version
                or any(retrieved.get(key) != passage for key, passage in evidence.items())
                or (answer.status == "insufficient_evidence") != (not answer.claims)
                or any(
                    key not in evidence or claim.text not in evidence[key].text
                    for claim in answer.claims
                    for key in claim.citation_ids
                )
            ):
                raise ValueError("Answer evidence mismatch")
            return Observation(
                retrieved_passage_ids=list(retrieved),
                cited_passage_ids=list(
                    dict.fromkeys(key for claim in answer.claims for key in claim.citation_ids)
                ),
                abstained=answer.status == "insufficient_evidence",
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                # No semantic rating is inferred from extraction; local compute is unknown.
                truncated=result.truncated,
            )
        return Observation(
            retrieved_passage_ids=[passage.id for passage in result.passages],
            truncated=result.truncated,
        )

    return observe


def write_report(result: Mapping[str, Any], output: Path) -> None:
    """Write minimized artifacts; refuse overwriting previous runs."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    fields = [
        "case_id",
        "category",
        "failed",
        "error",
        "latency_ms",
        "retrieval_recall_at_k",
        "retrieval_mrr",
        "citation_precision",
        "citation_recall",
        "answer_correctness",
        "faithfulness",
        "abstained",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
    ]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["cases"])
    summary = result["summary"]
    lines = [
        "# Atlas evaluation",
        "",
        f"Official benchmark: {result['official']}",
        f"Dataset SHA256: {result['dataset_hash']}",
        f"Corpus SHA256: {result['corpus_hash']}",
        f"Evaluator: {result['evaluator_version']}",
        f"Failures: {summary['failures']}/{summary['count']}",
        "",
        "Metric values exclude nulls; counts disclose scored cases. Failed cases remain failures.",
        "Citation scores measure passage-ID overlap, not semantic claim support.",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
    ]
    (output / "results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a pinned Atlas retrieval evaluation")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--dataset-sha256", required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--official", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--mode", choices=["lexical", "vector", "hybrid"], default="lexical")
    parser.add_argument("--retrieval-version", default="fts5-overlap-v1")
    parser.add_argument("--model-id")
    parser.add_argument("--model-digest")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--generation-model-id")
    parser.add_argument("--generation-model-digest")
    parser.add_argument("--prompt-version")
    parser.add_argument("--corpus-version", default="unspecified")
    parser.add_argument("--chunking-version", default="unspecified")
    args = parser.parse_args()
    from urllib.parse import urlparse

    import httpx

    url = urlparse(args.base_url)
    if url.username or url.password or url.query or url.fragment:
        parser.error("Base URL must not contain credentials, query or fragment")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        parser.error("Remote APIs require HTTPS")
    token = os.environ.get("ATLAS_EVAL_TOKEN")
    if not token:
        parser.error("Set ATLAS_EVAL_TOKEN without placing credentials on the command line")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        config = ExperimentConfig(
            k=args.k,
            mode=args.mode,
            retrieval_version=args.retrieval_version,
            model_id=args.model_id,
            model_digest=args.model_digest,
            generate_answers=args.answers,
            generation_model_id=args.generation_model_id,
            generation_model_digest=args.generation_model_digest,
            prompt_version=args.prompt_version,
            experiment_id=f"{args.mode}-{'answers' if args.answers else 'baseline'}",
            corpus_version=args.corpus_version,
            chunking_version=args.chunking_version,
        )
        with httpx.Client(
            base_url=args.base_url,
            timeout=300 if args.answers else 130,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            def snapshot() -> dict[str, str]:
                corpus: dict[str, str] = {}
                offset = 0
                while True:
                    response = client.get(
                        "/v1/documents", headers=headers, params={"limit": 100, "offset": offset}
                    )
                    response.raise_for_status()
                    page = response.json()
                    for document in page["items"]:
                        chunk_offset = 0
                        while True:
                            chunks = client.get(
                                f"/v1/documents/{document['id']}/chunks",
                                headers=headers,
                                params={"limit": 100, "offset": chunk_offset},
                            )
                            chunks.raise_for_status()
                            chunk_page = chunks.json()
                            for passage in chunk_page["items"]:
                                corpus[passage["id"]] = document["content_hash"]
                            chunk_offset += len(chunk_page["items"])
                            if chunk_offset >= chunk_page["total"]:
                                break
                            if not chunk_page["items"]:
                                raise ValueError("Invalid pagination")
                    offset += len(page["items"])
                    if offset >= page["total"]:
                        return corpus
                    if not page["items"]:
                        raise ValueError("Invalid pagination")

            corpus = snapshot()
            frozen = load_dataset(
                args.dataset,
                expected_dataset_hash=args.dataset_sha256,
                expected_corpus_hash=args.corpus_sha256,
                corpus=corpus,
                official=args.official,
            )
            result = run_experiment(frozen, config, lexical_http_observer(client, headers))
            if corpus_digest(snapshot()) != frozen.corpus_hash:
                raise ValueError("Corpus changed during evaluation")
            write_report(result, args.output)
    except Exception:
        parser.exit(
            1, "Evaluation failed; inspect inputs, authorization and service availability.\n"
        )


if __name__ == "__main__":
    main()
