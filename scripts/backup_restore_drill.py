"""Real pg_dump/restore drill on newly created synthetic databases only."""

import hashlib
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from atlas.config import Settings
from atlas.errors import AtlasError
from atlas.postgres import PostgresDocumentService, migrate, ready
from atlas.worker import run_once


def command(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(args, capture_output=True, timeout=120, check=False)
    if check and result.returncode:
        raise RuntimeError("Backup/restore subprocess failed; raw output withheld")
    return result


def fingerprint(dsn: str) -> str:
    values = {}
    with psycopg.connect(dsn) as db:
        for table in ("atlas_schema", "documents", "chunks", "ingestion_jobs", "chunk_embeddings"):
            rows = db.execute(
                sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(sql.Identifier(table))
            ).fetchall()
            values[table] = sorted(row[0] for row in rows)
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def main() -> None:
    admin = Path(".local/postgres.dsn").read_text().strip()
    run = uuid4().hex
    source, restored = f"atlas_drill_source_{run}", f"atlas_drill_restore_{run}"
    allowed = {source, restored}
    created: list[str] = []
    container = (
        command(["docker", "compose", "--env-file", ".local/postgres.env", "ps", "-q", "postgres"])
        .stdout.decode()
        .strip()
    )
    directory = Path(".local/backup-drills") / run
    directory.mkdir(parents=True, exist_ok=False)
    dump_path = f"/tmp/atlas-{run}.dump"
    try:
        for name in (source, restored):
            with psycopg.connect(admin, autocommit=True) as db:
                db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            created.append(name)
        source_dsn, restored_dsn = (
            make_conninfo(admin, dbname=name) for name in (source, restored)
        )
        migrate(source_dsn)
        settings = Settings(token_hashes={"alice": hashlib.sha256(b"synthetic-drill").hexdigest()})
        service = PostgresDocumentService(settings, source_dsn)
        doc, _ = service.put("alice", "guide", b"Synthetic source version one", "text/plain")
        doc, _ = service.put("alice", "guide", b"Synthetic source version two", "text/plain")
        service.put("bob", "private", b"Synthetic second owner", "text/plain")
        job = service.enqueue("alice", "queued", b"Synthetic queued source", "text/plain")
        assert run_once(service)
        passage = service.passages("alice", doc.id, 100, 0).items[0]
        with psycopg.connect(source_dsn) as db:
            db.execute(
                """INSERT INTO chunk_embeddings
                (chunk_id,model,model_digest,dimensions,embedding)
                VALUES (%s,'synthetic-drill',%s,2,'[1,0]'::public.vector)""",
                (passage.id, "a" * 64),
            )
        expected = fingerprint(source_dsn)
        started = time.perf_counter()
        command(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-c",
                'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump "$@"',
                "--",
                "-U",
                "atlas",
                "-d",
                source,
                "-Fc",
                "-f",
                dump_path,
            ]
        )
        command(["docker", "cp", f"{container}:{dump_path}", str(directory / "backup.dump")])
        backup_ms = (time.perf_counter() - started) * 1000
        digest = hashlib.sha256((directory / "backup.dump").read_bytes()).hexdigest()
        started = time.perf_counter()
        command(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-c",
                'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_restore "$@"',
                "--",
                "-U",
                "atlas",
                "-d",
                restored,
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                dump_path,
            ]
        )
        restore_ms = (time.perf_counter() - started) * 1000
        assert ready(restored_dsn) and fingerprint(restored_dsn) == expected
        recovered = PostgresDocumentService(settings, restored_dsn)
        assert recovered.get("alice", doc.id).version == 2
        assert recovered.citation("alice", passage.id) == passage
        assert recovered.job("alice", job.id).status == "succeeded"
        try:
            recovered.get("bob", doc.id)
        except AtlasError as error:
            assert error.status == 404
        else:
            raise AssertionError("Restored owner isolation failed")
        corrupt = directory / "corrupt.dump"
        corrupt.write_bytes(b"deliberately invalid backup fixture")
        command(["docker", "cp", str(corrupt), f"{container}:{dump_path}.corrupt"])
        assert (
            command(
                ["docker", "exec", container, "pg_restore", "--list", dump_path + ".corrupt"],
                check=False,
            ).returncode
            != 0
        )
        report = {
            "status": "passed",
            "scope": "synthetic disposable database restore",
            "backup_sha256": digest,
            "row_fingerprint": expected,
            "backup_ms": backup_ms,
            "restore_ms": restore_ms,
            "checks": [
                "schema",
                "documents and versions",
                "chunks and citations",
                "vectors",
                "jobs",
                "owner isolation",
                "corrupt dump rejected",
            ],
            "production_rto_claim": False,
        }
        (directory / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        # Only databases created by this invocation can be removed; never Atlas.
        for name in reversed(created):
            if name not in allowed or not name.startswith("atlas_drill_"):
                raise RuntimeError("Refusing cleanup outside the disposable drill")
            with psycopg.connect(admin, autocommit=True) as db:
                db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        command(
            ["docker", "exec", container, "rm", "-f", dump_path, dump_path + ".corrupt"],
            check=False,
        )


if __name__ == "__main__":
    main()
