"""Real API/storage orchestration with an explicitly fake generation provider."""

import pytest

from atlas.errors import AtlasError
from atlas.providers import Claim, GroundedAnswer

ALICE = {"Authorization": "Bearer " + "alice" * 16}
BOB = {"Authorization": "Bearer " + "bob" * 16}


class FakeGenerator:
    def __init__(self, callback=None):
        self.callback = callback
        self.seen = []

    def generate(self, question, passages):
        self.seen = passages
        if self.callback:
            self.callback()
        return GroundedAnswer(
            status="answered" if passages else "insufficient_evidence",
            claims=[Claim(text=p.text, citation_ids=[p.id], quotes=[p.text]) for p in passages],
            model="explicit-test-fake",
            model_digest=None,
        )


def enable(client, provider):
    client.app.state.settings.generation_enabled = True
    client.app.state.provider = provider


def upload(client):
    response = client.put(
        "/v1/documents/retries",
        headers={**ALICE, "Content-Type": "text/plain"},
        content=b"The retry limit is three tries.",
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_capabilities_and_answer_auth_disabled(client):
    assert client.get("/v1/capabilities").status_code == 401
    assert client.post("/v1/answers", json={"question": "retry"}).status_code == 401
    assert client.get("/v1/capabilities", headers=ALICE).json() == {
        "generation_enabled": False,
        "retrieval_modes": ["lexical"],
        "backend": "sqlite",
    }
    response = client.post("/v1/answers", headers=ALICE, json={"question": "retry"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "generation_disabled"


def test_answer_retrieves_only_owner_evidence_and_resolves_source(client):
    upload(client)
    fake = FakeGenerator()
    enable(client, fake)
    response = client.post("/v1/answers", headers=BOB, json={"question": "retry"})
    assert response.status_code == 200
    assert response.json()["answer"]["status"] == "insufficient_evidence"
    assert fake.seen == []
    response = client.post("/v1/answers", headers=ALICE, json={"question": "retry"})
    assert response.status_code == 200
    result = response.json()
    citation = result["answer"]["claims"][0]["citation_ids"][0]
    assert client.get(f"/v1/citations/{citation}", headers=ALICE).json() == result["passages"][0]
    assert client.get(f"/v1/citations/{citation}", headers=BOB).status_code == 404
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("mutation", ["delete", "replace"])
def test_changes_during_generation_do_not_return_stale_evidence(client, mutation):
    identifier = upload(client)
    store = client.app.state.documents

    def change():
        if mutation == "delete":
            store.delete("alice", identifier)
        else:
            store.put("alice", "retries", b"New retry policy.", "text/plain")

    enable(client, FakeGenerator(change))
    response = client.post("/v1/answers", headers=ALICE, json={"question": "retry"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "evidence_changed"


def test_provider_error_is_safe_and_payloads_are_bounded(client):
    def fail():
        raise AtlasError("provider_timeout", "Local model request failed or timed out.", 503)

    enable(client, FakeGenerator(fail))
    assert client.post("/v1/answers", headers=ALICE, content=b"text").status_code == 415
    assert client.post("/v1/answers", headers=ALICE, json={"question": ""}).status_code == 422
    assert (
        client.post("/v1/answers", headers=ALICE, json={"question": "x" * 9000}).status_code == 413
    )
    response = client.post("/v1/answers", headers=ALICE, json={"question": "retry"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_timeout"


def test_sqlite_queue_unavailable_and_auth_enforced(client):
    assert client.post("/v1/ingestions/guide", content=b"test").status_code == 401
    response = client.post("/v1/ingestions/guide", headers=ALICE, content=b"test")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "queue_unavailable"
