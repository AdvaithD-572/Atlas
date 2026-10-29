"""Bounded PostgreSQL ingestion worker; no external calls or document logging."""

import argparse
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg
from pydantic import ValidationError

from atlas.config import Settings
from atlas.errors import AtlasError
from atlas.ingestion import parse_document, parser_version
from atlas.postgres import PostgresDocumentService, db_connection, migrate, owner_lock, ready

logger = logging.getLogger("atlas.worker")


def heartbeat(path: Path) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(str(time.time()), encoding="ascii")
    temporary.replace(path)


def healthy(service: PostgresDocumentService, path: Path, max_age: float = 45) -> bool:
    try:
        age = time.time() - float(path.read_text(encoding="ascii"))
        return 0 <= age <= max_age and ready(service.dsn)
    except (OSError, ValueError):
        return False


@dataclass(frozen=True)
class Claim:
    id: str
    owner: str
    lease_token: str
    attempts: int


def claim(service: PostgresDocumentService, lease_seconds: int = 30) -> Claim | None:
    if not 5 <= lease_seconds <= 300:
        raise ValueError("Lease must be between five and 300 seconds.")
    with db_connection(service.dsn) as db:
        db.execute("""UPDATE ingestion_jobs SET status='failed',raw=NULL,
            error_code='attempts_exhausted',lease_token=NULL,lease_until=NULL,
            updated_at=clock_timestamp() WHERE status='running' AND attempts>=3
            AND lease_until < clock_timestamp()""")
        row = db.execute("""SELECT id,owner,attempts FROM ingestion_jobs
            WHERE attempts < 3 AND ((status='queued' AND available_at <= clock_timestamp())
            OR (status='running' AND lease_until < clock_timestamp()))
            ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if row is None:
            return None
        token = str(uuid4())
        db.execute(
            """UPDATE ingestion_jobs SET status='running',attempts=attempts+1,
            lease_token=%s,lease_until=clock_timestamp()+%s*interval '1 second',
            updated_at=clock_timestamp() WHERE id=%s""",
            (token, lease_seconds, row["id"]),
        )
        return Claim(row["id"], row["owner"], token, row["attempts"] + 1)


def _failure(service: PostgresDocumentService, work: Claim, code: str, retry: bool) -> None:
    retry = retry and work.attempts < 3
    delay = min(2**work.attempts, 30) + secrets.randbelow(1000) / 1000
    with db_connection(service.dsn) as db:
        owner_lock(db, work.owner)
        db.execute(
            """UPDATE ingestion_jobs SET status=%s,error_code=%s,
            raw=CASE WHEN %s THEN raw ELSE NULL END,lease_token=NULL,lease_until=NULL,
            available_at=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp()
            WHERE id=%s AND owner=%s AND status='running' AND lease_token=%s""",
            (
                "queued" if retry else "failed",
                code,
                retry,
                delay,
                work.id,
                work.owner,
                work.lease_token,
            ),
        )


def process(service: PostgresDocumentService, work: Claim) -> bool:
    """Commit only while the job's lease and principal authorization remain valid."""
    started = time.perf_counter()
    try:
        with db_connection(service.dsn) as db:
            source = db.execute(
                """SELECT * FROM ingestion_jobs WHERE id=%s AND owner=%s
                AND status='running' AND lease_token=%s AND lease_until>clock_timestamp()""",
                (work.id, work.owner, work.lease_token),
            ).fetchone()
        if source is None:
            return False
        if work.owner not in service.settings.token_hashes:
            raise AtlasError("owner_revoked", "Principal no longer authorized.", 403)
        if source["parser_version"] != parser_version(source["media_type"]):
            raise AtlasError("config_changed", "Re-enqueue with the current parser.", 409)
        parsed = parse_document(
            bytes(source["raw"]), source["media_type"], service.settings.max_upload_bytes
        )
        with db_connection(service.dsn) as db:
            # Same lock order as enqueue/put/delete: owner, then job.
            owner_lock(db, work.owner)
            row = db.execute(
                """SELECT * FROM ingestion_jobs WHERE id=%s AND owner=%s
                AND status='running' AND lease_token=%s AND lease_until>clock_timestamp()
                FOR UPDATE""",
                (work.id, work.owner, work.lease_token),
            ).fetchone()
            if row is None:
                return False
            if work.owner not in service.settings.token_hashes:
                raise AtlasError("owner_revoked", "Principal no longer authorized.", 403)
            if row["parser_version"] != parsed.parser_version:
                raise AtlasError("config_changed", "Re-enqueue with the current parser.", 409)
            document, _ = service._write(
                db,
                work.owner,
                row["source_key"],
                bytes(row["raw"]),
                row["media_type"],
                row["chunk_size"],
                row["chunk_overlap"],
                parsed,
            )
            db.execute(
                """UPDATE ingestion_jobs SET status='succeeded',raw=NULL,error_code=NULL,
                document_id=%s,lease_token=NULL,lease_until=NULL,updated_at=clock_timestamp()
                WHERE id=%s AND owner=%s AND lease_token=%s""",
                (document.id, work.id, work.owner, work.lease_token),
            )
        logger.info(
            json.dumps(
                {
                    "event": "job_succeeded",
                    "job_id": work.id,
                    "attempt": work.attempts,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        )
        return True
    except AtlasError as exc:
        _failure(service, work, exc.code, exc.code in {"parser_busy", "parser_unavailable"})
    except (
        psycopg.OperationalError,
        psycopg.errors.SerializationFailure,
        psycopg.errors.DeadlockDetected,
    ) as exc:
        logger.warning(
            json.dumps(
                {"event": "job_retry", "job_id": work.id, "exception_type": type(exc).__name__}
            )
        )
        _failure(service, work, "storage_unavailable", True)
    except Exception as exc:
        logger.error(
            json.dumps(
                {"event": "job_failed", "job_id": work.id, "exception_type": type(exc).__name__}
            )
        )
        _failure(service, work, "processing_failed", False)
    return False


def run_once(service: PostgresDocumentService) -> bool:
    work = claim(service)
    if work is None:
        return False
    process(service, work)
    return True


def init_local(directory: Path = Path(".local")) -> None:
    """Generate ignored local credentials once; never overwrite or print values."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / "postgres.env", directory / "postgres.dsn"]
    if any(path.exists() for path in paths):
        raise ValueError("Local PostgreSQL credentials already exist; preserve them.")
    password = secrets.token_urlsafe(32)
    values = [
        f"ATLAS_POSTGRES_PASSWORD={password}\n",
        f"postgresql://atlas:{password}@127.0.0.1:55432/atlas",
    ]
    for path, value in zip(paths, values, strict=True):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
    print("Local PostgreSQL credentials created in .local; keep these files private.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas PostgreSQL administration and worker")
    parser.add_argument("command", choices=["init-local", "migrate", "once", "run", "health"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "init-local":
        init_local()
        return
    if args.command == "migrate":
        dsn = os.environ.get("ATLAS_POSTGRES_DSN")
        if not dsn:
            parser.error("Set the migration administrator DSN securely in the environment.")
        migrate(dsn)
        print("PostgreSQL schema migrated.")
        return
    try:
        settings = Settings()
    except ValidationError:
        parser.error("Configure valid runtime credentials and a PostgreSQL DSN or DSN file.")
    if settings.postgres_dsn is None:
        parser.error("Configure a runtime PostgreSQL DSN or DSN file.")
    service = PostgresDocumentService(settings, settings.postgres_dsn.get_secret_value())
    heartbeat_path = Path(os.environ.get("ATLAS_WORKER_HEARTBEAT", "/tmp/atlas-worker.heartbeat"))
    if args.command == "health":
        raise SystemExit(0 if healthy(service, heartbeat_path) else 1)
    if args.command == "once":
        run_once(service)
        return
    while True:
        try:
            processed = run_once(service)
            heartbeat(heartbeat_path)
            if not processed:
                time.sleep(1)
        except psycopg.Error as exc:
            logger.error(
                json.dumps(
                    {"event": "worker_storage_unavailable", "exception_type": type(exc).__name__}
                )
            )
            time.sleep(5)


if __name__ == "__main__":
    main()
