"""Answer-observation contracts with an explicitly synthetic generator."""

import json

import pytest
from pydantic import ValidationError

from atlas.evaluation import (
    DatasetCase,
    ExperimentConfig,
    lexical_http_observer,
    run_experiment,
    write_report,
)
from atlas.providers import PROMPT_VERSION
from tests.test_evaluation import dataset, row
from tests.test_questions import ALICE, FakeGenerator, enable, upload


def config(**updates):
    return ExperimentConfig(
        **{
            "generate_answers": True,
            "generation_model_id": "explicit-test-fake",
            "generation_model_digest": "d" * 64,
            "prompt_version": PROMPT_VERSION,
            **updates,
        }
    )


class PinnedFake(FakeGenerator):
    def generate(self, question, passages):
        return (
            super()
            .generate(question, passages)
            .model_copy(
                update={
                    "model_digest": "d" * 64 if passages else None,
                    "input_tokens": 12 if passages else None,
                    "output_tokens": 4 if passages else None,
                }
            )
        )


def test_answer_observer_records_outcomes_but_not_invented_quality(client):
    upload(client)
    enable(client, PinnedFake())
    observed = lexical_http_observer(client, ALICE)(
        DatasetCase.model_validate(row(question="retry")), config()
    )
    assert observed.abstained is False
    assert observed.cited_passage_ids == observed.retrieved_passage_ids
    assert observed.input_tokens == 12 and observed.output_tokens == 4
    assert observed.answer_correctness is None and observed.faithfulness is None
    assert observed.estimated_cost_usd is None  # Local compute was not measured.
    empty = lexical_http_observer(client, ALICE)(
        DatasetCase.model_validate(row(question="qzzxnonexistent")), config()
    )
    assert empty.abstained is True
    assert empty.cited_passage_ids == [] and empty.input_tokens is None


def test_answer_mode_requires_pinned_identity_prompt_and_actual_top_k():
    for updates in (
        {"generation_model_digest": None},
        {"generation_model_id": None},
        {"prompt_version": None},
        {"k": 6},
        {"generate_answers": False},
    ):
        with pytest.raises(ValidationError):
            config(**updates)


@pytest.mark.parametrize(
    "updates",
    [
        {"generation_model_digest": "b" * 64},
        {"generation_model_id": "wrong-model"},
        {"prompt_version": "unrecognized-version"},
    ],
)
def test_answer_identity_mismatch_fails_closed(client, updates):
    upload(client)
    enable(client, PinnedFake())
    with pytest.raises(ValueError, match="Generation identity"):
        lexical_http_observer(client, ALICE)(
            DatasetCase.model_validate(row(question="retry")), config(**updates)
        )


def test_answer_observer_rejects_fabricated_claim_support(client):
    class UnsupportedClaim(PinnedFake):
        def generate(self, question, passages):
            answer = super().generate(question, passages)
            return answer.model_copy(
                update={"claims": [answer.claims[0].model_copy(update={"text": "Invented claim."})]}
            )

    upload(client)
    enable(client, UnsupportedClaim())
    with pytest.raises(ValueError, match="evidence"):
        lexical_http_observer(client, ALICE)(
            DatasetCase.model_validate(row(question="retry")), config()
        )


def test_answer_report_omits_content_and_provider_failures_remain_failures(client, tmp_path):
    upload(client)
    enable(client, PinnedFake())
    frozen = dataset(tmp_path, [row(question="retry")])
    result = run_experiment(frozen, config(), lexical_http_observer(client, ALICE))
    output = tmp_path / "answer-results"
    write_report(result, output)
    text = (output / "results.json").read_text()
    assert "The retry limit" not in text and "retry" not in text
    assert json.loads(text)["cases"][0]["abstained"] is False
    assert result["summary"]["answer_correctness"] == {"value": None, "count": 0}
    client.app.state.provider = None
    failed = run_experiment(frozen, config(), lexical_http_observer(client, ALICE))
    assert failed["summary"]["failures"] == 1
    assert failed["summary"]["abstention"]["count"] == 0


def test_answer_cli_pins_model_and_persists_real_outcomes(client, tmp_path, monkeypatch):
    import hashlib

    from atlas.evaluation import corpus_digest, main

    identifier = upload(client)
    enable(client, PinnedFake())
    document = client.get(f"/v1/documents/{identifier}", headers=ALICE).json()
    passages = client.get(f"/v1/documents/{identifier}/chunks", headers=ALICE).json()["items"]
    corpus = {passage["id"]: document["content_hash"] for passage in passages}
    path = tmp_path / "answer-fixture.jsonl"
    path.write_text(json.dumps(row(question="retry", relevant_passages=corpus)), encoding="utf-8")
    output = tmp_path / "cli-answers"
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
            "--answers",
            "--generation-model-id",
            "explicit-test-fake",
            "--generation-model-digest",
            "d" * 64,
            "--prompt-version",
            PROMPT_VERSION,
        ],
    )
    monkeypatch.setattr("httpx.Client", lambda **_: client)
    main()
    report = json.loads((output / "results.json").read_text())
    assert report["config"]["generate_answers"] is True
    assert report["summary"]["citation_precision"] == {"value": 1.0, "count": 1}
    assert report["summary"]["abstention"]["count"] == 1
    assert report["summary"]["answer_correctness"] == {"value": None, "count": 0}
    assert report["summary"]["failures"] == 0
