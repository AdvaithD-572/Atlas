"""Mock transport contract tests; actual Ollama smoke is separate evidence."""

import json

import httpx
import pytest

from atlas.errors import AtlasError
from atlas.providers import OllamaProvider
from atlas.schemas import Passage


def tags():
    return {
        "models": [
            {"name": "all-minilm:latest", "digest": "a" * 64},
            {"name": "qwen3:1.7b", "digest": "b" * 64},
        ]
    }


def provider(handler):
    return OllamaProvider(transport=httpx.MockTransport(handler))


def passage():
    return Passage(
        id="chunk-1",
        document_id="doc-1",
        source_key="guide",
        version=1,
        ordinal=0,
        start=0,
        end=29,
        text="The retry limit is three tries.",
    )


def test_embedding_contract_and_metadata():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags())
        assert request.url.path == "/api/embed"
        assert json.loads(request.content)["truncate"] is False
        return httpx.Response(200, json={"embeddings": [[0.0, 1.0, 0.0]], "prompt_eval_count": 4})

    result = provider(handler).embed(["synthetic input"])
    assert result.vectors == [[0.0, 1.0, 0.0]]
    assert result.model_digest == "a" * 64
    assert result.input_tokens == 4


@pytest.mark.parametrize(
    "vectors",
    [[], [[float("nan"), 1]], [[0, 0]], [[1, 0], [0, 1]], [[1], [1, 2]]],
    ids=["empty", "nonfinite", "zero", "count", "shape"],
)
def test_rejects_invalid_embeddings(vectors):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags())
        return httpx.Response(200, text=json.dumps({"embeddings": vectors}))

    with pytest.raises(AtlasError, match="invalid"):
        provider(handler).embed(["test"])


def test_structured_generation_checks_citations_and_quotes():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags())
        body = json.loads(request.content)
        assert body["stream"] is False and body["think"] is False
        assert "tools" not in body
        assert "untrusted" in body["messages"][0]["content"]
        content = {
            "status": "answered",
            "claims": [
                {
                    "text": "The retry limit is three tries.",
                    "citation_ids": ["chunk-1"],
                    "quotes": ["three tries"],
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(content)},
                "prompt_eval_count": 10,
                "eval_count": 20,
            },
        )

    answer = provider(handler).generate("What is the retry limit?", [passage()])
    assert answer.status == "answered"
    assert answer.claims[0].citation_ids == ["chunk-1"]
    assert answer.output_tokens == 20


@pytest.mark.parametrize(
    "claim",
    [
        {"text": "Answer", "citation_ids": ["other-owner"], "quotes": ["three"]},
        {"text": "Answer", "citation_ids": ["chunk-1"], "quotes": ["fabricated quote"]},
        {"text": "Answer", "citation_ids": [], "quotes": []},
    ],
    ids=["foreign-id", "false-quote", "uncited"],
)
def test_rejects_unverified_citation_output(claim):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags())
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps({"status": "answered", "claims": [claim]})}},
        )

    with pytest.raises(AtlasError):
        provider(handler).generate("question", [passage()])


def test_empty_evidence_abstains_without_provider_call():
    def handler(request):
        pytest.fail("Empty evidence must not trigger a provider request")

    answer = provider(handler).generate("question", [])
    assert answer.status == "insufficient_evidence"
    assert answer.claims == []


def test_missing_model_and_permanent_error_not_retried():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"models": []})

    with pytest.raises(AtlasError, match="installed"):
        provider(handler).embed(["test"])
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("body", "expected_code", "expected_status"),
    [
        (
            json.dumps({"error": "the input length exceeds the context length"}),
            "embedding_context_exceeded",
            422,
        ),
        ('{"error":"PRIVATE_PROVIDER_ERROR"}', "provider_rejected", 502),
        ("PRIVATE_PROVIDER_ERROR", "provider_rejected", 502),
        (json.dumps(["the input length exceeds the context length"]), "provider_rejected", 502),
        (
            json.dumps(
                {"error": "the input length exceeds the context length", "extra": "x" * 5000}
            ),
            "provider_rejected",
            502,
        ),
    ],
    ids=["context-limit", "unknown", "not-json", "wrong-shape", "oversized-error"],
)
def test_embedding_rejections_are_actionable_bounded_private_and_not_retried(
    body, expected_code, expected_status
):
    calls = []

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags())
        calls.append(request.url.path)
        assert json.loads(request.content)["truncate"] is False
        return httpx.Response(400, text=body)

    with pytest.raises(AtlasError) as error:
        provider(handler).embed(["test"])
    assert error.value.code == expected_code
    assert error.value.status == expected_status
    assert "PRIVATE_PROVIDER_ERROR" not in error.value.message
    assert calls == ["/api/embed"]
    if expected_code == "embedding_context_exceeded":
        assert "smaller document chunks" in error.value.message
        assert "shorter query" in error.value.message


def test_transient_retries_are_bounded():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503, text="PRIVATE_PROVIDER_ERROR")

    with pytest.raises(AtlasError) as caught:
        provider(handler).embed(["test"])
    assert len(calls) == 2
    assert "PRIVATE_PROVIDER_ERROR" not in str(caught.value)


def test_provider_endpoint_is_local_only():
    with pytest.raises(ValueError):
        OllamaProvider(base_url="https://example.com")
