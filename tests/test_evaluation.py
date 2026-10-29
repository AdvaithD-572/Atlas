"""Synthetic fixtures only: these are not a human-reviewed benchmark."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from atlas.evaluation import (
    DatasetCase,
    ExperimentConfig,
    Observation,
    abstention_metrics,
    citation_metrics,
    corpus_digest,
    load_dataset,
    recall_at_k,
    reciprocal_rank,
    run_experiment,
    write_report,
)

HASH = hashlib.sha256(b"synthetic source").hexdigest()


def row(**updates):
    result = dict(
        case_id="synthetic-1",
        category="direct",
        question="Synthetic question?",
        answerable=True,
        expected_facts=["Synthetic fact"],
        relevant_passages={"passage-1": HASH},
        scoring_notes="Synthetic unit fixture",
        human_reviewer=None,
        reviewed_at=None,
        synthetic=True,
    )
    result.update(updates)
    return result


def dataset(tmp_path, rows=None, official=False):
    path = tmp_path / "fixture.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in (rows or [row()])), encoding="utf-8")
    return load_dataset(
        path,
        expected_dataset_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        expected_corpus_hash=corpus_digest({"passage-1": HASH}),
        corpus={"passage-1": HASH},
        official=official,
    )


def test_ranking_counts_unique_relevant_passages_and_preserves_positions():
    assert recall_at_k(["x", "a", "a", "b"], {"a", "b"}, 3) == 0.5
    assert reciprocal_rank(["x", "a", "b"], {"a", "b"}, 3) == 0.5
    assert recall_at_k([], {"a"}, 5) == 0
    assert reciprocal_rank([], {"a"}, 5) == 0
    assert recall_at_k([], set(), 5) is None
    with pytest.raises(ValueError):
        recall_at_k([], {"a"}, 0)


def test_citation_denominators_and_no_evidence():
    assert citation_metrics(["a", "a", "x"], {"a", "b"}) == {"precision": 0.5, "recall": 0.5}
    assert citation_metrics([], {"a"}) == {"precision": None, "recall": 0.0}
    assert citation_metrics([], set()) == {"precision": None, "recall": None}


def test_abstention_confusion_and_empty_denominators():
    result = abstention_metrics([(False, True), (False, False), (True, True), (True, False)])
    assert result == dict(tp=1, fp=1, tn=1, fn=1, precision=0.5, recall=0.5, accuracy=0.5, count=4)
    assert abstention_metrics([])["accuracy"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"answerable": "true"},
        {"unexpected": 1},
        {"relevant_passages": {"p": "bad"}},
        {"answerable": True, "expected_facts": []},
        {"human_reviewer": "reviewer"},
        {"reviewed_at": "2026-01-01T00:00:00", "human_reviewer": "reviewer"},
        {"category": "unanswerable"},
    ],
)
def test_strict_case_validation(updates):
    with pytest.raises(ValidationError):
        DatasetCase.model_validate(row(**updates))


def test_dataset_integrity_and_official_gate(tmp_path):
    frozen = dataset(tmp_path)
    assert frozen.cases[0].case_id == "synthetic-1"
    with pytest.raises(ValueError, match="100"):
        dataset(tmp_path, official=True)
    with pytest.raises(ValueError, match="duplicate"):
        dataset(tmp_path, [row(), row()])
    with pytest.raises(ValueError, match="source"):
        dataset(tmp_path, [row(relevant_passages={"passage-1": "0" * 64})])
    path = tmp_path / "fixture.jsonl"
    with pytest.raises(ValueError, match="dataset hash"):
        load_dataset(
            path,
            expected_dataset_hash="0" * 64,
            expected_corpus_hash=corpus_digest({"passage-1": HASH}),
            corpus={"passage-1": HASH},
        )


def test_runner_redacts_failure_and_does_not_claim_unrated_metrics(tmp_path):
    frozen = dataset(tmp_path, [row(), row(case_id="synthetic-2")])
    calls = 0

    def callback(case, config):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SECRET document and token")
        return Observation(retrieved_passage_ids=["passage-1"])

    result = run_experiment(frozen, ExperimentConfig(), callback)
    assert result["summary"]["failures"] == 1
    assert result["summary"]["retrieval_recall_at_k"]["count"] == 1
    assert result["summary"]["answer_correctness"]["value"] is None
    assert result["summary"]["abstention"]["count"] == 0
    write_report(result, tmp_path / "report")
    for suffix in ("json", "csv", "md"):
        text = (tmp_path / "report" / f"results.{suffix}").read_text()
        assert "SECRET" not in text
        assert "Synthetic question" not in text
    assert result["cases"][0]["estimated_cost_usd"] is None


def test_runner_rejects_unpinned_semantic_mode(tmp_path):
    with pytest.raises(ValidationError):
        ExperimentConfig(mode="hybrid")


def test_semantic_config_requires_mode_version_and_model_digest():
    config = ExperimentConfig(
        mode="hybrid",
        retrieval_version="rrf60-depth20-v1",
        model_id="synthetic",
        model_digest="a" * 64,
    )
    assert config.mode == "hybrid"
    with pytest.raises(ValidationError):
        ExperimentConfig(
            mode="vector",
            retrieval_version="rrf60-depth20-v1",
            model_id="synthetic",
            model_digest="a" * 64,
        )


def test_lexical_integration_uses_real_index(client, tmp_path):
    from atlas.evaluation import lexical_http_observer

    auth = {"Authorization": "Bearer " + "alice" * 16}
    created = client.put(
        "/v1/documents/eval.txt",
        content=b"A synthetic service uses port 9911.",
        headers={**auth, "Content-Type": "text/plain"},
    ).json()
    passages = client.get(f"/v1/documents/{created['id']}/chunks", headers=auth).json()["items"]
    observation = lexical_http_observer(client, auth)(
        DatasetCase.model_validate(row(question="port 9911")), ExperimentConfig()
    )
    assert observation.retrieved_passage_ids == [passages[0]["id"]]
    assert observation.abstained is None
    assert observation.cited_passage_ids is None


def test_official_gate_rejects_100_synthetic_cases(tmp_path):
    with pytest.raises(ValueError, match="human-reviewed"):
        dataset(
            tmp_path, [row(case_id=f"synthetic-{index}") for index in range(100)], official=True
        )


def test_distribution_gate_is_separate_from_review_metadata(tmp_path):
    # Deliberately invalid metadata fixtures; this is not a reviewed dataset.
    rows = [
        row(
            case_id=f"metadata-fixture-{index}",
            synthetic=False,
            human_reviewer="test-only-not-a-human",
            reviewed_at="2020-01-01T00:00:00Z",
        )
        for index in range(100)
    ]
    with pytest.raises(ValueError, match="distribution"):
        dataset(tmp_path, rows, official=True)


def test_frozen_dataset_and_corpus_mismatch_fail_closed(tmp_path):
    frozen = dataset(tmp_path)
    frozen.cases[0].expected_facts.append("mutation")
    with pytest.raises(ValueError, match="modified"):
        run_experiment(frozen, ExperimentConfig(), lambda *_: Observation(retrieved_passage_ids=[]))
    path = tmp_path / "fixture.jsonl"
    with pytest.raises(ValueError, match="corpus hash"):
        load_dataset(
            path,
            expected_dataset_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
            expected_corpus_hash="0" * 64,
            corpus={"passage-1": HASH},
        )


def test_human_ratings_require_attribution_and_finite_values():
    with pytest.raises(ValidationError, match="reviewer"):
        Observation(retrieved_passage_ids=[], answer_correctness=1.0)
    with pytest.raises(ValidationError):
        Observation(retrieved_passage_ids=[], estimated_cost_usd=float("nan"))
    assert (
        Observation(
            retrieved_passage_ids=[], answer_correctness=0.5, rating_reviewer="test-fixture"
        ).answer_correctness
        == 0.5
    )


def test_report_refuses_overwrite(tmp_path):
    frozen = dataset(tmp_path)
    result = run_experiment(
        frozen, ExperimentConfig(), lambda *_: Observation(retrieved_passage_ids=[])
    )
    output = tmp_path / "output"
    write_report(result, output)
    with pytest.raises(FileExistsError):
        write_report(result, output)


def test_cli_runs_real_api_and_writes_minimized_artifacts(client, tmp_path, monkeypatch):
    from atlas.evaluation import main

    auth = {"Authorization": "Bearer " + "alice" * 16}
    created = client.put(
        "/v1/documents/cli-eval.txt",
        content=b"Synthetic service port 9922.",
        headers={**auth, "Content-Type": "text/plain"},
    ).json()
    passages = client.get(f"/v1/documents/{created['id']}/chunks", headers=auth).json()["items"]
    corpus = {passage["id"]: created["content_hash"] for passage in passages}
    path = tmp_path / "cli-fixture.jsonl"
    path.write_text(
        json.dumps(row(question="port 9922", relevant_passages=corpus)), encoding="utf-8"
    )
    output = tmp_path / "cli-result"
    monkeypatch.setenv("ATLAS_EVAL_TOKEN", "alice" * 16)
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluation",
            str(path),
            "--dataset-sha256",
            hashlib.sha256(path.read_bytes()).hexdigest(),
            "--corpus-sha256",
            corpus_digest(corpus),
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr("httpx.Client", lambda **_: client)
    main()
    result = json.loads((output / "results.json").read_text())
    assert result["summary"]["retrieval_recall_at_k"] == {"value": 1.0, "count": 1}
    assert result["official"] is False
    assert result["summary"]["failures"] == 0
    assert "9922" not in (output / "results.json").read_text()
