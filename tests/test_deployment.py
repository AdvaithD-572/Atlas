import secrets
import time
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from atlas.deployment import initialize_runtime, provision_runtime
from atlas.errors import AtlasError
from atlas.postgres import PostgresDocumentService, ready
from atlas.worker import healthy, heartbeat, run_once
from tests.test_postgres import service  # noqa: F401


def test_runtime_role_allows_lifecycle_and_worker_but_denies_administration(service):  # noqa: F811
    role = "atlas_runtime_" + uuid4().hex
    with psycopg.connect(service.dsn) as db:
        schema = db.execute("SELECT current_schema()").fetchone()[0]
    runtime_dsn = provision_runtime(service.dsn, role, secrets.token_urlsafe(32), schema)
    runtime = PostgresDocumentService(service.settings, runtime_dsn)
    try:
        assert ready(runtime_dsn)
        document, _ = runtime.put("alice", "guide", b"runtime source", "text/plain")
        assert runtime.get("alice", document.id) == document
        with pytest.raises(AtlasError) as denied:
            runtime.get("bob", document.id)
        assert denied.value.status == 404
        runtime.delete("alice", document.id)
        assert run_once(runtime) is False
        for query in (
            "CREATE TABLE forbidden (id int)",
            "CREATE ROLE forbidden",
            "ALTER TABLE documents ADD COLUMN forbidden int",
            "TRUNCATE documents CASCADE",
            "INSERT INTO atlas_schema VALUES (999)",
        ):
            with psycopg.connect(runtime_dsn) as db:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    db.execute(query)
        with psycopg.connect(runtime_dsn) as db:
            flags = db.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles "
                "WHERE rolname=current_user"
            ).fetchone()
            assert flags == (False, False, False, False)
    finally:
        with psycopg.connect(service.dsn, autocommit=True) as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_worker_health_requires_recent_progress_and_actual_database(service, tmp_path):  # noqa: F811
    path = tmp_path / "worker.heartbeat"
    assert not healthy(service, path)
    heartbeat(path)
    assert healthy(service, path)
    path.write_text(str(time.time() - 60))
    assert not healthy(service, path)
    path.write_text("nan")
    assert not healthy(service, path)
    path.write_text(str(time.time() + 60))
    assert not healthy(service, path)
    heartbeat(path)
    broken = PostgresDocumentService(service.settings, "host=127.0.0.1 port=1 dbname=missing")
    assert not healthy(broken, path)


def test_worker_cli_reads_runtime_dsn_file(service, tmp_path, monkeypatch):  # noqa: F811
    from atlas import worker

    path = tmp_path / "runtime.dsn"
    path.write_text(service.dsn)
    monkeypatch.delenv("ATLAS_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("ATLAS_POSTGRES_DSN_PATH", str(path))
    monkeypatch.setenv("ATLAS_TOKEN_HASHES", '{"alice":"' + "a" * 64 + '"}')
    job = service.enqueue("alice", "file-config", b"Runtime file configuration", "text/plain")
    monkeypatch.setattr("sys.argv", ["atlas.worker", "once"])
    worker.main()
    assert service.job("alice", job.id).status == "succeeded"


def test_runtime_provisioning_rolls_back_its_files_and_role_on_write_failure(
    service,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    import os

    from atlas import deployment

    # The existing fixture has a private schema, so provision its grants there.
    with psycopg.connect(service.dsn) as db:
        schema = db.execute("SELECT current_schema()").fetchone()[0]
    roles = []

    def provision_scoped(dsn, role, password):
        roles.append(role)
        return provision_runtime(dsn, role, password, schema)

    original = os.open

    def fail_second(path, flags, mode):
        if path.name == "runtime-container.dsn":
            raise OSError("Synthetic disk failure")
        return original(path, flags, mode)

    (tmp_path / "postgres.dsn").write_text(service.dsn)
    monkeypatch.setattr(deployment, "provision_runtime", provision_scoped)
    monkeypatch.setattr(deployment.os, "open", fail_second)
    with pytest.raises(RuntimeError, match="provisioning undone"):
        initialize_runtime(tmp_path)
    assert not (tmp_path / "runtime.dsn").exists()
    assert not (tmp_path / "runtime-container.dsn").exists()
    with psycopg.connect(service.dsn) as db:
        assert db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (roles[0],)).fetchone() is None
