import hashlib
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from atlas.__main__ import provision
from atlas.config import Settings
from atlas.database import connection, migrate, ready
from atlas.ingestion import chunk_text, parse_text
from atlas.main import create_app
from atlas.security import RateLimiter
from atlas.services import DocumentService
from tests.test_lifecycle import headers


@pytest.fixture
def settings(tmp_path):
    config = Settings(
        database_path=tmp_path / "data.db",
        chunk_size=80,
        chunk_overlap=10,
        token_hashes={"alice": hashlib.sha256(("alice" * 16).encode()).hexdigest()},
    )
    migrate(config.database_path)
    return config


def test_exact_unicode_spans_and_overlap():
    text = "# Guide\r\n日本語🙂 café\n" * 20
    chunks = chunk_text(text, 80, 10)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)
    for index, chunk in enumerate(chunks):
        assert chunk.text == text[chunk.start : chunk.end]
        if index:
            assert chunk.start == chunks[index - 1].end - 10
    assert chunks[0].text + "".join(chunk.text[10:] for chunk in chunks[1:]) == text
    assert chunk_text("", 80, 10) == []
    with pytest.raises(ValueError):
        chunk_text(text, 10, 10)


@pytest.mark.parametrize(
    "raw,media,maximum",
    [(b"x", "application/pdf", 5), (b"xx", "text/plain", 1)],
    ids=["type", "size"],
)
def test_service_validates_even_without_http(raw, media, maximum):
    from atlas.errors import AtlasError

    with pytest.raises(AtlasError):
        parse_text(raw, media, maximum)


def test_atomic_rollback_of_replacement(settings):
    service = DocumentService(settings)
    original, _ = service.put("alice", "guide", b"Original source", "text/plain")
    passage = service.passages("alice", original.id, 20, 0).items[0]
    with patch("atlas.services.insert_chunks", side_effect=sqlite3.OperationalError("synthetic")):
        with pytest.raises(sqlite3.OperationalError):
            service.put("alice", "guide", b"Replacement", "text/plain")
    assert service.get("alice", original.id) == original
    assert service.citation("alice", passage.id).text == "Original source"


def test_atomic_rollback_of_first_ingestion(settings):
    service = DocumentService(settings)
    with patch("atlas.services.insert_chunks", side_effect=sqlite3.OperationalError("synthetic")):
        with pytest.raises(sqlite3.OperationalError):
            service.put("alice", "guide", b"New content", "text/plain")
    assert service.list("alice", 20, 0).total == 0


def test_concurrent_dedup_and_config_reindex(settings):
    service = DocumentService(settings)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: service.put("alice", "same", b"Repeated", "text/plain"), range(8))
        )
    assert sum(created for _, created in results) == 1
    assert {doc.version for doc, _ in results} == {1}
    original = results[0][0]
    new_config = Settings(**{**settings.model_dump(), "chunk_size": 100})
    updated, created = DocumentService(new_config).put("alice", "same", b"Repeated", "text/plain")
    assert not created
    assert updated.id == original.id
    assert updated.version == 2


def test_deletion_cascades_and_pagination(settings):
    service = DocumentService(settings)
    one, _ = service.put("alice", "one", b"Long text " * 50, "text/markdown")
    service.put("alice", "two", b"Second", "text/plain")
    first = service.list("alice", 1, 0)
    second = service.list("alice", 1, 1)
    assert first.total == second.total == 2
    assert first.items[0].id != second.items[0].id
    chunks = service.passages("alice", one.id, 1, 1)
    assert chunks.total > 1 and chunks.items[0].ordinal == 1
    service.delete("alice", one.id)
    with connection(settings.database_path) as db:
        assert (
            db.execute("SELECT count(*) FROM chunks WHERE document_id=?", (one.id,)).fetchone()[0]
            == 0
        )


def test_quota_is_checked_inside_transaction(settings):
    settings.max_documents = 1
    service = DocumentService(settings)
    service.put("alice", "one", b"One", "text/plain")
    from atlas.errors import AtlasError

    with pytest.raises(AtlasError, match="quota"):
        service.put("alice", "two", b"Two", "text/plain")
    service.put("alice", "one", b"Replacement", "text/plain")
    settings.max_owner_chars = 1024
    with pytest.raises(AtlasError, match="quota"):
        service.put("alice", "one", b"X" * 1025, "text/plain")


def test_safe_errors_and_content_free_logs(settings, caplog):
    with TestClient(create_app(settings)) as client:
        assert logging.getLogger("atlas.requests").isEnabledFor(logging.INFO)
        response = client.put(
            "/v1/documents/secret-name", content=b"PRIVATE_DOCUMENT", headers=headers()
        )
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]
        with patch("atlas.api.DocumentService.list", side_effect=RuntimeError("PRIVATE_EXCEPTION")):
            failure = client.get("/v1/documents", headers=headers())
        assert failure.status_code == 500
        with patch(
            "atlas.api.DocumentService.list", side_effect=sqlite3.OperationalError("PRIVATE_DB")
        ):
            failure = client.get("/v1/documents", headers=headers())
        assert failure.status_code == 503
        assert "PRIVATE_DB" not in failure.text
    logs = "\n".join(record.message for record in caplog.records if record.name == "atlas.requests")
    for sensitive in ("PRIVATE_DOCUMENT", "PRIVATE_EXCEPTION", "secret-name", "alice" * 16):
        assert sensitive not in logs
    assert all("request_id" in json.loads(line) for line in logs.splitlines())


def test_rate_limiting_and_recovery(settings):
    from atlas.errors import AtlasError

    limiter = RateLimiter(1)
    with patch("atlas.security.time.monotonic", return_value=0):
        limiter.admit("alice")
        with pytest.raises(AtlasError):
            limiter.admit("alice")
    with patch("atlas.security.time.monotonic", return_value=61):
        limiter.admit("alice")
    settings.requests_per_minute = 1
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/documents", headers=headers()).status_code == 200
        response = client.get("/v1/documents", headers=headers())
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"


def test_startup_requires_valid_unique_credentials(tmp_path):
    digest = "a" * 64
    bad = [{}, {"alice": "raw-token"}, {"bad/owner": digest}, {"alice": digest, "bob": digest}]
    for token_hashes in bad:
        with pytest.raises(ValidationError):
            Settings(token_hashes=token_hashes, credentials_path=tmp_path / "missing")
    with pytest.raises(ValidationError):
        Settings(token_hashes={"alice": digest}, chunk_size=80, chunk_overlap=80)


def test_provision_without_echo_or_overwrite(tmp_path, capsys):
    provision("alice", tmp_path)
    token = (tmp_path / "alice.token").read_text()
    assert len(token) >= 40
    assert token not in capsys.readouterr().out
    config = Settings(credentials_path=tmp_path / "credentials.json")
    assert config.token_hashes["alice"] == hashlib.sha256(token.encode()).hexdigest()
    with pytest.raises(ValueError, match="already exists"):
        provision("alice", tmp_path)
    with pytest.raises(ValueError):
        provision("../../escape", tmp_path)
    assert (tmp_path / "alice.token").read_text() == token


def test_future_schema_rejected_and_missing_tables_unready(settings):
    with connection(settings.database_path) as db:
        db.execute("PRAGMA user_version=999")
    assert not ready(settings.database_path)
    with pytest.raises(ValueError):
        migrate(settings.database_path)
    with connection(settings.database_path) as db:
        db.execute("PRAGMA user_version=1")
        db.execute("DROP TABLE chunks")
    assert not ready(settings.database_path)


def test_chunk_amplification_is_bounded(settings):
    from atlas.errors import AtlasError

    with pytest.raises(ValidationError, match="half"):
        Settings(**{**settings.model_dump(), "chunk_overlap": 79})
    with pytest.raises(AtlasError, match="chunk limit"):
        chunk_text("a" * 1048576, 64, 32)


def test_concurrent_provision_preserves_principals(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda owner: provision(owner, tmp_path), ["one", "two", "three", "four"]))
    credentials = json.loads((tmp_path / "credentials.json").read_text())
    assert set(credentials) == {"one", "two", "three", "four"}
    for owner, digest in credentials.items():
        assert hashlib.sha256((tmp_path / f"{owner}.token").read_bytes()).hexdigest() == digest


def test_bad_startup_credentials_not_in_error():
    with pytest.raises(ValidationError) as caught:
        Settings(token_hashes={"alice": "SYNTHETIC_RAW_SECRET"})
    assert "SYNTHETIC_RAW_SECRET" not in str(caught.value)


def test_provision_failure_can_retry(tmp_path):
    with patch("atlas.__main__.json.dump", side_effect=OSError("synthetic disk failure")):
        with pytest.raises(OSError):
            provision("alice", tmp_path)
    assert not list(tmp_path.iterdir())
    provision("alice", tmp_path)
    assert (tmp_path / "alice.token").exists()
