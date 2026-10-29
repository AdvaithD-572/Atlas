"""Real PostgreSQL contracts; synthetic fixtures are not benchmark data."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from atlas.config import Settings
from atlas.errors import AtlasError
from atlas.main import create_app
from atlas.postgres import PostgresDocumentService, db_connection, migrate, ready
from atlas.retrieval import SearchRequest
from atlas.worker import claim, process, run_once
from tests.test_formats import pdf_bytes


@pytest.fixture
def service():
    dsn = os.environ.get("ATLAS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("ATLAS_TEST_POSTGRES_DSN is required for real PostgreSQL tests")
    schema = "atlas_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    # Do not fall back to application tables in public if a test table is missing.
    scoped = make_conninfo(dsn, options=f"-c search_path={schema}")
    settings = Settings(token_hashes={"alice": hashlib.sha256(b"test-only").hexdigest()})
    try:
        migrate(scoped)
        yield PostgresDocumentService(settings, scoped)
    finally:
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_pg_lifecycle_search_isolation(service):
    assert ready(service.dsn)
    migrate(service.dsn)
    first, created = service.put("alice", "guide", b"Atlas token rotation guide", "text/plain")
    assert created
    repeat, created = service.put("alice", "guide", b"Atlas token rotation guide", "text/plain")
    assert not created and repeat == first
    passage = service.passages("alice", first.id, 10, 0).items[0]
    assert service.citation("alice", passage.id).text == "Atlas token rotation guide"
    for operation in (
        lambda: service.get("bob", first.id),
        lambda: service.citation("bob", passage.id),
        lambda: service.delete("bob", first.id),
    ):
        with pytest.raises(AtlasError):
            operation()
    assert not service.list("bob", 10, 0).items
    assert (
        service.search("bob", SearchRequest(question="rotation")).status == "insufficient_evidence"
    )
    assert service.search("alice", SearchRequest(question="rotation")).passages[0].id == passage.id
    changed, _ = service.put("alice", "guide", b"Replacement content", "text/plain")
    assert changed.id == first.id and changed.version == 2
    with pytest.raises(AtlasError):
        service.citation("alice", passage.id)
    service.delete("alice", first.id)
    assert not service.list("alice", 10, 0).items
    assert not service.search("alice", SearchRequest(question="replacement")).passages


@pytest.mark.parametrize(
    "media,raw,page,heading",
    [
        ("application/pdf", pdf_bytes("Rotate tokens safely"), 1, None),
        ("text/html", b"<h1>Rotation</h1><p>Rotate tokens safely</p>", None, "Rotation"),
    ],
    ids=["pdf", "html"],
)
def test_pg_format_worker_locations_and_dedup(service, media, raw, page, heading):
    queued = service.enqueue("alice", "format", raw, media)
    assert run_once(service)
    job = service.job("alice", queued.id)
    assert job.status == "succeeded"
    document = service.get("alice", job.document_id)
    passage = service.citation("alice", service.passages("alice", document.id, 10, 0).items[0].id)
    assert (passage.page_number, passage.heading) == (page, heading)
    assert service.search("alice", SearchRequest(question="tokens")).passages[0] == passage
    with pytest.raises(AtlasError):
        service.citation("bob", passage.id)
    assert service.put("alice", "format", raw, media)[0] == document
    with db_connection(service.dsn) as db:
        assert (
            db.execute("SELECT raw FROM ingestion_jobs WHERE id=%s", (job.id,)).fetchone()["raw"]
            is None
        )
    service.delete("alice", document.id)
    with pytest.raises(AtlasError):
        service.citation("alice", passage.id)


def test_pg_bad_pdf_job_does_not_replace_valid_document(service):
    original, _ = service.put("alice", "guide", b"Original", "text/plain")
    job = service.enqueue("alice", "guide", b"%PDF-malformed", "application/pdf")
    assert run_once(service)
    failed = service.job("alice", job.id)
    assert failed.status == "failed" and failed.attempts == 1 and failed.error_code == "invalid_pdf"
    assert service.get("alice", original.id) == original
    assert not run_once(service)


def test_pg_delete_during_parse_fences_publication(service, monkeypatch):
    from atlas.ingestion import parse_document

    doc, _ = service.put("alice", "race", b"Original", "text/plain")
    service.enqueue("alice", "race", b"<p>Replacement</p>", "text/html")
    work = claim(service)
    assert work is not None

    def delete_while_parsing(raw, media_type, maximum):
        service.delete("alice", doc.id)
        return parse_document(raw, media_type, maximum)

    monkeypatch.setattr("atlas.worker.parse_document", delete_while_parsing)
    assert not process(service, work)
    assert not service.list("alice", 10, 0).items


def test_pg_location_migration_preserves_existing_data(service):
    doc, _ = service.put("alice", "legacy", b"Legacy source", "text/plain")
    old_passage = service.passages("alice", doc.id, 10, 0).items[0]
    # Reconstruct v2 within this isolated disposable schema, then apply v3 twice.
    with db_connection(service.dsn) as db:
        db.execute("ALTER TABLE chunks DROP COLUMN page_number, DROP COLUMN heading")
        db.execute("DELETE FROM atlas_schema WHERE version=3")
    migrate(service.dsn)
    migrate(service.dsn)
    assert service.get("alice", doc.id) == doc
    assert service.citation("alice", old_passage.id) == old_passage


def test_pg_queue_owner_and_success(service):
    job = service.enqueue("alice", "guide", b"Queued indexing text", "text/plain")
    assert job.status == "queued" and job.attempts == 0
    with pytest.raises(AtlasError):
        service.job("bob", job.id)
    assert run_once(service)
    done = service.job("alice", job.id)
    assert done.status == "succeeded" and done.attempts == 1
    assert service.get("alice", done.document_id).source_key == "guide"
    assert not run_once(service)


def test_pg_claim_lease_recovery_and_stale_claim(service):
    job = service.enqueue("alice", "guide", b"Recover safely", "text/plain")
    old = claim(service)
    assert old is not None
    with db_connection(service.dsn) as db:
        db.execute(
            """UPDATE ingestion_jobs SET lease_until=clock_timestamp()-interval '1 second'
            WHERE id=%s""",
            (job.id,),
        )
    newer = claim(service)
    assert newer is not None and newer.lease_token != old.lease_token
    assert not process(service, old)
    assert process(service, newer)
    assert service.job("alice", job.id).attempts == 2


def test_pg_delete_and_newer_write_fence_claim(service):
    doc, _ = service.put("alice", "guide", b"Original", "text/plain")
    queued = service.enqueue("alice", "guide", b"Stale replacement", "text/plain")
    work = claim(service)
    assert work is not None
    service.delete("alice", doc.id)
    assert not process(service, work)
    # Deletion purges job metadata/payloads as well as document/chunk data.
    with pytest.raises(AtlasError):
        service.job("alice", queued.id)
    assert not service.list("alice", 10, 0).items
    second = service.enqueue("alice", "guide", b"Another old write", "text/plain")
    work = claim(service)
    service.put("alice", "guide", b"Newest synchronous write", "text/plain")
    assert work is not None and not process(service, work)
    assert service.job("alice", second.id).status == "cancelled"


def test_pg_concurrent_dedup_and_single_claim(service):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: service.put("alice", "same", b"Same", "text/plain"), range(8))
        )
    assert sum(created for _, created in results) == 1
    service.enqueue("alice", "job", b"Job", "text/plain")
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: claim(service), range(4)))
    assert sum(item is not None for item in claims) == 1


def test_pg_bounded_retry_and_payload_cleanup(service):
    job = service.enqueue("alice", "guide", b"Retry source", "text/plain")
    for attempt in range(3):
        work = claim(service)
        assert work is not None and work.attempts == attempt + 1
        with db_connection(service.dsn) as db:
            db.execute(
                """UPDATE ingestion_jobs SET lease_until=clock_timestamp()-interval '1 second'
                WHERE id=%s""",
                (job.id,),
            )
    assert claim(service) is None
    assert service.job("alice", job.id).status == "failed"
    with db_connection(service.dsn) as db:
        assert (
            db.execute("SELECT raw FROM ingestion_jobs WHERE id=%s", (job.id,)).fetchone()["raw"]
            is None
        )


def test_pg_quota_and_transaction_rollback(service, monkeypatch):
    service.settings.max_documents = 1
    original, _ = service.put("alice", "one", b"Original", "text/plain")
    with pytest.raises(AtlasError):
        service.put("alice", "two", b"Other", "text/plain")

    def fail(*args):
        raise RuntimeError("synthetic insert failure")

    monkeypatch.setattr(service, "_insert_chunks", fail)
    with pytest.raises(RuntimeError):
        service.put("alice", "one", b"Replacement", "text/plain")
    assert service.get("alice", original.id) == original


def test_pg_retryable_failure_rolls_back_then_retries(service, monkeypatch):
    original, _ = service.put("alice", "guide", b"Original", "text/plain")
    job = service.enqueue("alice", "guide", b"Replacement", "text/plain")
    work = claim(service)
    assert work is not None
    actual = service._insert_chunks

    def transient(*args):
        raise psycopg.OperationalError("Synthetic connection fault; no external provider mocked")

    monkeypatch.setattr(service, "_insert_chunks", transient)
    assert not process(service, work)
    assert service.get("alice", original.id) == original
    retry = service.job("alice", job.id)
    assert retry.status == "queued" and retry.error_code == "storage_unavailable"
    assert claim(service) is None  # Bounded exponential backoff applies.
    monkeypatch.setattr(service, "_insert_chunks", actual)
    with db_connection(service.dsn) as db:
        db.execute(
            "UPDATE ingestion_jobs SET available_at=clock_timestamp() WHERE id=%s", (job.id,)
        )
    assert run_once(service)
    assert service.job("alice", job.id).status == "succeeded"
    assert service.get("alice", original.id).version == 2


def test_pg_permanent_failure_and_revocation_release_payload(service, monkeypatch):
    job = service.enqueue("alice", "broken", b"Sensitive staged document", "text/plain")

    def permanent(*args):
        raise RuntimeError("SYNTHETIC_PRIVATE_ERROR")

    monkeypatch.setattr(service, "_insert_chunks", permanent)
    assert run_once(service)
    assert service.job("alice", job.id).status == "failed"
    assert service.job("alice", job.id).error_code == "processing_failed"
    assert not service.list("alice", 10, 0).items
    other = service.enqueue("alice", "revoked", b"Now revoked", "text/plain")
    service.settings.token_hashes.clear()
    assert run_once(service)
    assert service.job("alice", other.id).error_code == "owner_revoked"
    with db_connection(service.dsn) as db:
        rows = db.execute("SELECT raw FROM ingestion_jobs").fetchall()
        assert all(row["raw"] is None for row in rows)


def test_pg_queue_dedup_replacement_and_bounds(service):
    first = service.enqueue("alice", "guide", b"Same", "text/plain")
    assert service.enqueue("alice", "guide", b"Same", "text/plain").id == first.id
    old = claim(service)
    replacement = service.enqueue("alice", "guide", b"Changed", "text/plain")
    assert replacement.id != first.id
    assert old is not None and not process(service, old)
    assert service.job("alice", first.id).status == "cancelled"
    for number in range(19):
        service.enqueue("alice", f"source-{number}", b"Queued", "text/plain")
    with pytest.raises(AtlasError, match="full"):
        service.enqueue("alice", "overflow", b"Other", "text/plain")
    # The rejected write must not disturb an earlier pending job.
    assert service.job("alice", replacement.id).status == "queued"


def test_pg_search_cap_and_tenant_independent_ranking(service):
    service.settings.chunk_size = 64
    service.settings.chunk_overlap = 0
    service.put("alice", "guide", b"rotation " * 1600, "text/plain")
    before = service.search("alice", SearchRequest(question="rotation", limit=3))
    assert before.truncated and len(before.passages) == 3
    service.put("bob", "foreign", b"rotation " * 1000, "text/plain")
    after = service.search("alice", SearchRequest(question="rotation", limit=3))
    assert after.passages == before.passages
    assert not service.search("alice", SearchRequest(question="' | & !")).passages


def test_pg_vector_extension_is_real(service):
    with db_connection(service.dsn) as db:
        result = db.execute(
            "SELECT '[1,0]'::public.vector OPERATOR(public.<=>) '[0,1]'::public.vector AS distance"
        ).fetchone()
        assert result["distance"] == pytest.approx(1.0)


def test_pg_readiness_rejects_schema_drift(service):
    with db_connection(service.dsn) as db:
        db.execute("INSERT INTO atlas_schema(version) VALUES (999)")
    healthy = ready(service.dsn)
    assert not healthy
    with pytest.raises(ValueError, match="newer"):
        migrate(service.dsn)
    with db_connection(service.dsn) as db:
        db.execute("DELETE FROM atlas_schema WHERE version=999")
        # This isolated test schema now has embedding foreign keys too.
        db.execute("DROP TABLE chunks CASCADE")
    healthy = ready(service.dsn)
    assert not healthy


def test_pg_job_configuration_and_staging_quota(service):
    with pytest.raises(ValueError, match="Lease"):
        claim(service, lease_seconds=1)
    job = service.enqueue("alice", "guide", b"Staged", "text/plain")
    with db_connection(service.dsn) as db:
        db.execute("UPDATE ingestion_jobs SET parser_version='future' WHERE id=%s", (job.id,))
    assert run_once(service)
    assert service.job("alice", job.id).error_code == "config_changed"
    service.settings.max_owner_chars = 1024
    with pytest.raises(AtlasError, match="quota"):
        service.enqueue("alice", "too-large", b"X" * 1025, "text/plain")
    with pytest.raises(AtlasError):
        service.passages("alice", str(uuid4()), 10, 0)


def test_local_postgres_credentials_are_private_output_and_not_overwritten(tmp_path, capsys):
    from atlas.worker import init_local

    init_local(tmp_path)
    original = (tmp_path / "postgres.env").read_text()
    password = original.strip().split("=", 1)[1]
    assert len(password) >= 40
    assert password in (tmp_path / "postgres.dsn").read_text()
    assert password not in capsys.readouterr().out
    with pytest.raises(ValueError, match="already exist"):
        init_local(tmp_path)
    assert (tmp_path / "postgres.env").read_text() == original


def test_worker_cli_once_and_migrate_use_real_database(service, monkeypatch, capsys):
    from atlas import worker

    monkeypatch.setenv("ATLAS_POSTGRES_DSN", service.dsn)
    runtime_settings = service.settings.model_copy(update={"postgres_dsn": SecretStr(service.dsn)})
    monkeypatch.setattr(worker, "Settings", lambda: runtime_settings)
    monkeypatch.setattr("sys.argv", ["atlas.worker", "migrate"])
    worker.main()
    job = service.enqueue("alice", "cli", b"CLI indexed document", "text/plain")
    monkeypatch.setattr("sys.argv", ["atlas.worker", "once"])
    worker.main()
    assert service.job("alice", job.id).status == "succeeded"
    assert service.dsn not in capsys.readouterr().out


def test_worker_cli_requires_dsn_and_initializes_locally(tmp_path, monkeypatch):
    from atlas import worker

    monkeypatch.delenv("ATLAS_POSTGRES_DSN", raising=False)
    monkeypatch.setattr("sys.argv", ["atlas.worker", "once"])
    with pytest.raises(SystemExit) as failure:
        worker.main()
    assert failure.value.code == 2
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["atlas.worker", "init-local"])
    worker.main()
    assert Path(".local/postgres.env").is_file()


def test_pg_real_http_queue_auth_status_search_and_delete(service):
    settings = service.settings.model_copy(
        update={
            "postgres_dsn": SecretStr(service.dsn),
            "token_hashes": {
                "alice": hashlib.sha256(b"test-only").hexdigest(),
                "bob": hashlib.sha256(b"test-bob").hexdigest(),
            },
        }
    )
    alice = {"Authorization": "Bearer test-only", "Content-Type": "text/plain"}
    bob = {"Authorization": "Bearer test-bob"}
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.post("/v1/ingestions/guide", content=b"No auth").status_code == 401
        accepted = client.post(
            "/v1/ingestions/guide", content=b"Token rotation guide", headers=alice
        )
        assert accepted.status_code == 202
        job_id = accepted.json()["id"]
        assert client.get(f"/v1/jobs/{job_id}", headers=bob).status_code == 404
        assert run_once(service)
        completed = client.get(f"/v1/jobs/{job_id}", headers=alice).json()
        assert completed["status"] == "succeeded"
        result = client.post(
            "/v1/search",
            json={"question": "rotation"},
            headers={"Authorization": "Bearer test-only"},
        )
        assert result.status_code == 200
        assert result.json()["retrieval_version"] == "postgres-simple-overlap-v1"
        citation = result.json()["passages"][0]["id"]
        assert client.get(f"/v1/citations/{citation}", headers=bob).status_code == 404
        doc_id = completed["document_id"]
        assert client.delete(f"/v1/documents/{doc_id}", headers=alice).status_code == 204
        assert client.get(f"/v1/jobs/{job_id}", headers=alice).status_code == 404
        assert client.get(f"/v1/citations/{citation}", headers=alice).status_code == 404
