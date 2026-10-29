"""API contracts; synthetic test inputs are not benchmark evidence."""

import pytest
from fastapi.testclient import TestClient

from atlas.config import Settings
from atlas.database import migrate
from atlas.main import create_app


def headers(owner: str = "alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {owner * 16}", "Content-Type": "text/plain"}


def upload(client: TestClient, text: str = "Atlas stores authorized technical documentation."):
    return client.put("/v1/documents/guide", content=text.encode(), headers=headers())


def test_authentication_and_readiness(client: TestClient):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/v1/documents").status_code == 401
    assert client.get("/v1/documents", headers=headers("unknown")).status_code == 401


def test_lifecycle_dedup_version_source_delete(client: TestClient):
    first = upload(client)
    assert first.status_code == 201
    doc = first.json()
    assert doc["version"] == 1
    assert doc["status"] == "indexed"
    repeated = upload(client)
    assert repeated.status_code == 200
    assert repeated.json() == doc
    chunks = client.get(f"/v1/documents/{doc['id']}/chunks", headers=headers()).json()
    chunk = chunks["items"][0]
    source = client.get(f"/v1/citations/{chunk['id']}", headers=headers()).json()
    assert source["text"] == "Atlas stores authorized technical documentation."
    assert source["start"] == 0
    updated = upload(client, "New content replaces the old version.").json()
    assert updated["id"] == doc["id"]
    assert updated["version"] == 2
    assert client.get(f"/v1/citations/{chunk['id']}", headers=headers()).status_code == 404
    assert client.delete(f"/v1/documents/{doc['id']}", headers=headers()).status_code == 204
    assert client.get("/v1/documents", headers=headers()).json()["items"] == []
    assert client.get(f"/v1/documents/{doc['id']}", headers=headers()).status_code == 404


def test_cross_owner_access_is_denied(client: TestClient):
    doc = upload(client).json()
    chunk = client.get(f"/v1/documents/{doc['id']}/chunks", headers=headers()).json()["items"][0]
    for route in (
        f"/v1/documents/{doc['id']}",
        f"/v1/documents/{doc['id']}/chunks",
        f"/v1/citations/{chunk['id']}",
    ):
        assert client.get(route, headers=headers("bob")).status_code == 404
    assert client.delete(f"/v1/documents/{doc['id']}", headers=headers("bob")).status_code == 404
    assert client.get("/v1/documents", headers=headers("bob")).json()["items"] == []
    other = client.put("/v1/documents/guide", content=b"Bob's content", headers=headers("bob"))
    assert other.status_code == 201
    assert other.json()["id"] != doc["id"]


@pytest.mark.parametrize(
    "body,media,status",
    [
        (b"", "text/plain", 422),
        (b"   ", "text/plain", 422),
        (b"\xff", "text/plain", 422),
        (b"zero\x00byte", "text/plain", 422),
        (b"%PDF-fake", "application/pdf", 422),
        (b"<script>only code</script>", "text/html", 422),
        (b"x" * 262145, "text/plain", 413),
    ],
    ids=["empty", "whitespace", "invalid-utf8", "binary", "pdf", "html", "oversize"],
)
def test_invalid_upload_preserves_existing(
    client: TestClient, body: bytes, media: str, status: int
):
    original = upload(client).json()
    response = client.put(
        "/v1/documents/guide", content=body, headers={**headers(), "Content-Type": media}
    )
    assert response.status_code == status
    assert client.get(f"/v1/documents/{original['id']}", headers=headers()).json() == original


def test_persistence_and_migration_idempotence(client: TestClient, settings: Settings):
    doc = upload(client).json()
    migrate(settings.database_path)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"/v1/documents/{doc['id']}", headers=headers()).json() == doc


def test_unmigrated_storage_not_ready(settings: Settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 503


def test_validation_does_not_echo_sensitive_input(client: TestClient):
    result = client.get("/v1/documents?limit=PRIVATE_PAYLOAD", headers=headers())
    assert result.status_code == 422
    assert "PRIVATE_PAYLOAD" not in result.text
