"""Adversarial contract fixtures; mock model responses, no real-model quality claim."""

import asyncio
import json
import time

import httpx
import pytest

from atlas.errors import AtlasError
from atlas.providers import OllamaProvider
from atlas.schemas import Passage


def passage(identifier: str, text: str) -> Passage:
    return Passage(
        id=identifier,
        document_id="document-1",
        source_key="fixture.txt",
        version=1,
        ordinal=0,
        start=0,
        end=len(text),
        text=text,
    )


def provider_with(response: dict) -> OllamaProvider:
    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "qwen3:1.7b", "digest": "a" * 64},
                        {"name": "all-minilm:latest", "digest": "b" * 64},
                    ]
                },
            )
        return httpx.Response(200, json=response)

    return OllamaProvider(transport=httpx.MockTransport(serve))


def test_each_citation_must_support_its_claim():
    provider = provider_with(
        {
            "message": {
                "content": json.dumps(
                    {
                        "status": "answered",
                        "claims": [
                            {
                                "text": "Service uses port 9911.",
                                "citation_ids": ["p1", "p2"],
                                "quotes": ["Service uses port 9911.", "It rains."],
                            }
                        ],
                    }
                )
            }
        }
    )
    with pytest.raises(AtlasError):
        provider.generate(
            "Which port?", [passage("p1", "Service uses port 9911."), passage("p2", "It rains.")]
        )


def test_whitespace_claim_is_not_answer_content():
    provider = provider_with(
        {
            "message": {
                "content": json.dumps(
                    {
                        "status": "answered",
                        "claims": [
                            {
                                "text": " ",
                                "citation_ids": ["p1"],
                                "quotes": ["Service uses port 9911."],
                            }
                        ],
                    }
                )
            }
        }
    )
    with pytest.raises(AtlasError):
        provider.generate("Which port?", [passage("p1", "Service uses port 9911.")])


@pytest.mark.parametrize("component", [1e308, 10**1000], ids=["norm-overflow", "integer-overflow"])
def test_embedding_rejects_unsafe_numeric_magnitudes(component):
    provider = provider_with({"embeddings": [[component]]})
    with pytest.raises(AtlasError) as caught:
        provider.embed(["Synthetic text"])
    assert caught.value.code == "provider_invalid"


def test_stream_cannot_extend_total_deadline_indefinitely(monkeypatch):
    # Logical clock only: does not wait 61 seconds or contact a model.
    import atlas.providers as module

    elapsed = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(module.time, "perf_counter", lambda: elapsed[0])

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"value":'
            elapsed[0] += 61
            yield b"true}"

    provider = OllamaProvider(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream()))
    )
    with pytest.raises(AtlasError):
        provider._request("GET", "/api/tags")


@pytest.mark.parametrize(
    "remote", [{"remote_host": "https://ollama.com"}, {"remote_model": "remote-model"}]
)
def test_local_alias_with_remote_metadata_is_rejected_before_sending_evidence(remote):
    sent = []

    def serve(request):
        sent.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:1.7b", "digest": "a" * 64, **remote}]}
            )
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "status": "answered",
                            "claims": [
                                {
                                    "text": "Synthetic text.",
                                    "citation_ids": ["p1"],
                                    "quotes": ["Synthetic text."],
                                }
                            ],
                        }
                    )
                }
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(serve))
    with pytest.raises(AtlasError):
        provider.generate("Synthetic question?", [passage("p1", "Synthetic text.")])
    assert sent == ["/api/tags"]


def test_generation_response_cannot_claim_a_different_model():
    provider = provider_with(
        {
            "model": "unexpected-model",
            "done": True,
            "message": {
                "content": json.dumps(
                    {
                        "status": "answered",
                        "claims": [
                            {
                                "text": "Synthetic text.",
                                "citation_ids": ["p1"],
                                "quotes": ["Synthetic text."],
                            }
                        ],
                    }
                )
            },
        }
    )
    with pytest.raises(AtlasError):
        provider.generate("Synthetic question?", [passage("p1", "Synthetic text.")])


def test_deadline_cancels_transport_and_releases_capacity():
    cancelled = []

    async def blocked(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
        return httpx.Response(200, json={})

    provider = OllamaProvider(transport=httpx.MockTransport(blocked))
    started = time.monotonic()
    with pytest.raises(AtlasError) as failure:
        provider._request("GET", "/api/tags", budget=0.02)
    assert failure.value.code == "provider_timeout"
    assert time.monotonic() - started < 1
    assert cancelled == [True]
    assert provider._slots.acquire(blocking=False)
    assert provider._slots.acquire(blocking=False)
    provider._slots.release()
    provider._slots.release()
