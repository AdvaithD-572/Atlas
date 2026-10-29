"""Run paired reranking and separately attributed local-model answer diagnostics."""

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import httpx

from atlas.errors import AtlasError
from atlas.evaluation import (
    ExperimentConfig,
    FrozenDataset,
    lexical_http_observer,
    recall_at_k,
    reciprocal_rank,
)
from atlas.providers import PROMPT_VERSION
from atlas.quality_study import JUDGE_PROMPT, RANK_PROMPT, StudyModel
from atlas.questions import AnswerResult
from atlas.vector_retrieval import VectorSearchResult


def mean(rows: list[dict[str, Any]], key: str) -> dict[str, float | int | None]:
    values = [row[key] for row in rows if row.get(key) is not None]
    return {"value": sum(values) / len(values) if values else None, "count": len(values)}


def summarize(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    latency = sorted(row["reranking_ms"] for row in rows if "reranking_ms" in row)
    summary = {
        key: mean(rows, key)
        for key in (
            "baseline_recall",
            "baseline_mrr",
            "reranked_recall",
            "reranked_mrr",
            "abstention_correct",
            "model_fact_coverage",
            "model_claim_relevance",
            "model_status_appropriate",
        )
    }
    summary["attempted"] = len(rows)
    paired = [row for row in rows if row.get("reranked_recall") is not None]
    summary["paired_baseline_recall"] = mean(paired, "baseline_recall")
    summary["paired_baseline_mrr"] = mean(paired, "baseline_mrr")
    for key in ("recall", "mrr"):
        scored = [{"score": row.get("reranked_" + key, 0)} for row in rows if row["answerable"]]
        summary["reranked_" + key + "_failures_as_zero"] = mean(scored, "score")
    for key in ("rerank_failed", "answer_failed", "judge_failed"):
        stage = key.removesuffix("_failed")
        attempted = sum(bool(row[stage + "_attempted"]) for row in rows)
        summary[stage + "_attempted"] = attempted
        summary[stage + "_skipped"] = len(rows) - attempted
        summary[key] = sum(bool(row[key] and row[stage + "_attempted"]) for row in rows)
    summary["judge_contradictions"] = sum(bool(row.get("judge_contradiction")) for row in rows)
    summary["abstention_correct_failures_as_zero"] = {
        "value": sum(row.get("abstention_correct", 0) for row in rows) / len(rows),
        "count": len(rows),
    }
    for stage in ("answer", "judge"):
        durations = sorted(row[stage + "_ms"] for row in rows if stage + "_ms" in row)
        summary[stage + "_p95_ms"] = (
            durations[math.ceil(0.95 * len(durations)) - 1] if durations else None
        )
    p95 = latency[math.ceil(0.95 * len(latency)) - 1] if latency else None
    summary["reranking_p95_ms"] = p95
    gate = bool(
        not summary["rerank_failed"]
        and summary["rerank_skipped"] == 0
        and p95 is not None
        and p95 <= 2000
        and summary["reranked_recall"]["value"] is not None
        and summary["reranked_recall"]["value"] >= summary["baseline_recall"]["value"] + 0.02
        and summary["reranked_mrr"]["value"] >= summary["baseline_mrr"]["value"]
    )
    return summary, gate


def run_study(
    client: httpx.Client,
    dataset: FrozenDataset,
    output: Path,
    embedding_model: str,
    embedding_digest: str,
) -> None:
    output.mkdir(exist_ok=False)
    model = StudyModel()
    tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5, trust_env=False)
    tags.raise_for_status()
    digest = next(m["digest"] for m in tags.json()["models"] if m["name"] == model.generation_model)
    config = ExperimentConfig(
        mode="hybrid",
        retrieval_version="rrf60-depth20-v1",
        model_id=embedding_model,
        model_digest=embedding_digest,
        generate_answers=True,
        generation_model_id=model.generation_model,
        generation_model_digest=digest,
        prompt_version=PROMPT_VERSION,
        experiment_id="automated-quality-study",
        corpus_version="atlas-docs-v1",
        chunking_version="utf8-literal-v1-400-80",
    )
    protocol = {
        "evaluator_version": "quality-study-v2",
        "official": False,
        "human_reviewed": False,
        "holdout": False,
        "dataset_hash": dataset.dataset_hash,
        "corpus_hash": dataset.corpus_hash,
        "generator": config.model_dump(),
        "study_model": model.generation_model,
        "study_model_digest": digest,
        "reranker_prompt": RANK_PROMPT,
        "judge_prompt": JUDGE_PROMPT,
        "candidate_depth": 20,
        "k": 5,
        "temperature": 0,
        "seed": 0,
        "workload": "serial, shared local host",
        "retention_gate": {
            "recall_gain_min": 0.02,
            "mrr_regression_max": 0,
            "additional_failures_max": 0,
            "added_p95_ms_max": 2000,
        },
        "limitations": [
            "AI draft labels",
            "same generator and judge",
            "no human calibration",
            "canonical spans omit equivalent relevant passages",
            "no untouched holdout",
        ],
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    (output / "verification.json").write_text(
        json.dumps({"status": "pending_final_corpus_check"}), encoding="utf-8"
    )
    captured: list[httpx.Response] = []

    def capture(response: httpx.Response) -> None:
        if response.request.url.path == "/v1/answers":
            response.read()
            captured[:] = [response]

    client.event_hooks["response"].append(capture)
    rows: list[dict[str, Any]] = []
    try:
        observe = lexical_http_observer(client, {})
        with (output / "cases.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
            for case in dataset.cases:
                row: dict[str, Any] = {
                    "case_id": case.case_id,
                    "category": case.category,
                    "answerable": case.answerable,
                    "rerank_failed": False,
                    "answer_failed": False,
                    "judge_failed": False,
                    "rerank_attempted": False,
                    "answer_attempted": False,
                    "judge_attempted": False,
                }
                stage = "candidates"
                started = time.perf_counter()
                try:
                    response = client.post(
                        "/v1/search?mode=hybrid",
                        json={
                            "question": case.question,
                            "limit": 20,
                        },
                    )
                    response.raise_for_status()
                    result = VectorSearchResult.model_validate(response.json())
                    if (
                        result.unindexed_chunks
                        or result.model_digest != embedding_digest
                        or result.embedding_model != embedding_model
                        or result.mode != "hybrid"
                        or result.retrieval_version != config.retrieval_version
                    ):
                        raise ValueError("Candidate configuration mismatch")
                    pool = result.passages
                    row["retrieval_ms"] = (time.perf_counter() - started) * 1000
                    ids = [p.id for p in pool]
                    row["candidate_ids"] = ids
                    row["candidate_hash"] = hashlib.sha256(
                        json.dumps([p.model_dump() for p in pool], sort_keys=True).encode()
                    ).hexdigest()
                    row["truncated"] = result.truncated
                    row["baseline_recall"] = recall_at_k(ids, set(case.relevant_passages), 5)
                    row["baseline_mrr"] = reciprocal_rank(ids, set(case.relevant_passages), 5)
                    stage = "rerank"
                    row["rerank_attempted"] = True
                    started = time.perf_counter()
                    try:
                        ranked, usage = model.rank(case.question, pool, digest)
                        row["reranked_ids"] = [p.id for p in ranked[:5]]
                        row["reranker_usage"] = usage.model_dump()
                        row["reranked_recall"] = recall_at_k(
                            row["reranked_ids"], set(case.relevant_passages), 5
                        )
                        row["reranked_mrr"] = reciprocal_rank(
                            row["reranked_ids"], set(case.relevant_passages), 5
                        )
                    except Exception as error:
                        row["rerank_failed"] = True
                        row["rerank_error"] = (
                            error.code if isinstance(error, AtlasError) else type(error).__name__
                        )
                    finally:
                        row["reranking_ms"] = (time.perf_counter() - started) * 1000
                    stage = "answer"
                    row["answer_attempted"] = True
                    started = time.perf_counter()
                    observation = observe(case, config)
                    row["answer_ms"] = (time.perf_counter() - started) * 1000
                    row["answer_observation"] = observation.model_dump()
                    answer = AnswerResult.model_validate(captured[-1].json())
                    row["abstention_correct"] = float(
                        observation.abstained == (not case.answerable)
                    )
                    stage = "judge"
                    row["judge_attempted"] = True
                    started = time.perf_counter()
                    judgment, usage = model.judge(
                        case.question,
                        case.expected_facts,
                        case.answerable,
                        answer.answer,
                        answer.passages,
                        digest,
                    )
                    row["judge_ms"] = (time.perf_counter() - started) * 1000
                    row["model_judged"] = judgment.model_dump()
                    row["judge_contradiction"] = bool(
                        observation.abstained and any(fact != "missing" for fact in judgment.facts)
                    )
                    row["judge_usage"] = usage.model_dump()
                    row["model_fact_coverage"] = (
                        sum(
                            {"supported": 1, "partial": 0.5, "missing": 0}[v]
                            for v in judgment.facts
                        )
                        / len(judgment.facts)
                        if judgment.facts
                        else None
                    )
                    row["model_claim_relevance"] = (
                        sum(v == "relevant" for v in judgment.claims) / len(judgment.claims)
                        if judgment.claims
                        else None
                    )
                    row["model_status_appropriate"] = float(judgment.status_appropriate)
                except Exception as error:
                    row[stage + "_ms"] = (time.perf_counter() - started) * 1000
                    row["failed_stage"] = stage
                    row["error_code"] = (
                        error.code if isinstance(error, AtlasError) else type(error).__name__
                    )
                    row["rerank_failed"] |= stage in {"candidates", "rerank"}
                    row["answer_failed"] = stage in {"candidates", "rerank", "answer"}
                    row["judge_failed"] = True
                rows.append(row)
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                print(
                    json.dumps({"study_completed": len(rows), "of": len(dataset.cases)}), flush=True
                )
    finally:
        client.event_hooks["response"].remove(capture)
    summary, gate = summarize(rows)
    report = {
        "protocol": protocol,
        "summary": summary,
        "development_gate_passed": gate,
        "application_enabled": False,
        "human_ratings": None,
        "compute_cost_usd": None,
        "provider_service_fee_usd": 0,
    }
    (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "results.md").write_text(
        "# Automated development study\n\nNot human calibrated; not an official benchmark.\n\n"
        + "```json\n"
        + json.dumps(summary, indent=2)
        + "\n```\n\n"
        + f"Development retention gate passed: {gate}. Application reranking stays disabled.\n",
        encoding="utf-8",
    )
