"""Explicit PostgreSQL persistence and owner-scoped document operations."""

import hashlib
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from atlas.config import Settings
from atlas.errors import AtlasError, not_found
from atlas.ingestion import Chunk, ParsedDocument, parse_document, parser_version, validate_upload
from atlas.retrieval import SearchRequest, SearchResult, terms
from atlas.schemas import Document, Page, Passage

SCHEMA_VERSION = 3
DOCUMENT_SELECT = """SELECT d.*, (SELECT count(*) FROM chunks c WHERE c.document_id=d.id)
AS chunk_count FROM documents d"""
PASSAGE_SELECT = """SELECT c.id,c.document_id,c.ordinal,c.start,c.\"end\",c.text,
c.page_number,c.heading,d.source_key,d.version
FROM chunks c JOIN documents d ON d.id=c.document_id"""


class IngestionJob(BaseModel):
    id: str
    source_key: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempts: int
    error_code: str | None
    document_id: str | None
    created_at: datetime
    updated_at: datetime


@contextmanager
def db_connection(dsn: str) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as db:
        db.execute("SET LOCAL statement_timeout = '10s'")
        db.execute("SET LOCAL lock_timeout = '5s'")
        db.execute("SET LOCAL idle_in_transaction_session_timeout = '15s'")
        yield db


def migrate(dsn: str) -> None:
    """Migration is transactional; existing databases are never implicitly reset."""
    with db_connection(dsn) as db:
        db.execute("SELECT pg_advisory_xact_lock(1895528101)")
        db.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        db.execute("CREATE TABLE IF NOT EXISTS atlas_schema (version integer PRIMARY KEY)")
        current = db.execute(
            "SELECT coalesce(max(version),0) AS version FROM atlas_schema"
        ).fetchone()
        assert current is not None
        if current["version"] > SCHEMA_VERSION:
            raise ValueError("Database schema is newer than this application.")
        for version in range(current["version"] + 1, SCHEMA_VERSION + 1):
            files = list(Path(__file__).with_name("pg_migrations").glob(f"{version:03}_*.sql"))
            if len(files) != 1:
                raise ValueError("Missing or ambiguous PostgreSQL migration.")
            db.execute(files[0].read_text(encoding="utf-8"))
            db.execute("INSERT INTO atlas_schema(version) VALUES (%s)", (version,))


def ready(dsn: str) -> bool:
    try:
        with db_connection(dsn) as db:
            row = db.execute("SELECT max(version) AS version FROM atlas_schema").fetchone()
            extension = db.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone()
            db.execute("SELECT id, search_vector FROM chunks LIMIT 0")
            db.execute("SELECT id FROM documents LIMIT 0")
            db.execute("SELECT id FROM ingestion_jobs LIMIT 0")
            db.execute("SELECT chunk_id,model_digest,dimensions FROM chunk_embeddings LIMIT 0")
            return bool(row and row["version"] == SCHEMA_VERSION and extension)
    except psycopg.Error:
        return False


def owner_lock(db: psycopg.Connection[dict[str, Any]], owner: str) -> None:
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (owner,))


class PostgresDocumentService:
    def __init__(self, settings: Settings, dsn: str) -> None:
        self.settings = settings
        self.dsn = dsn

    def _cancel(self, db: psycopg.Connection[dict[str, Any]], owner: str, key: str) -> None:
        db.execute(
            """UPDATE ingestion_jobs SET status='cancelled',raw=NULL,
            error_code='superseded',lease_token=NULL,lease_until=NULL,updated_at=clock_timestamp()
            WHERE owner=%s AND source_key=%s AND status IN ('queued','running')""",
            (owner, key),
        )

    def _insert_chunks(
        self, db: psycopg.Connection[dict[str, Any]], document_id: str, chunks: list[Chunk]
    ) -> None:
        with db.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO chunks
                (id,document_id,ordinal,start,"end",text,page_number,heading)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    (
                        str(uuid4()),
                        document_id,
                        c.ordinal,
                        c.start,
                        c.end,
                        c.text,
                        c.page_number,
                        c.heading,
                    )
                    for c in chunks
                ],
            )

    def _write(
        self,
        db: psycopg.Connection[dict[str, Any]],
        owner: str,
        key: str,
        raw: bytes,
        media_type: str,
        size: int,
        overlap: int,
        parsed: ParsedDocument,
    ) -> tuple[Document, bool]:
        text = parsed.text
        chunks = parsed.chunks(size, overlap)
        digest = hashlib.sha256(raw).hexdigest()
        old = db.execute(
            DOCUMENT_SELECT + " WHERE owner=%s AND source_key=%s", (owner, key)
        ).fetchone()
        if old and (
            old["content_hash"],
            old["media_type"],
            old["parser_version"],
            old["chunk_size"],
            old["chunk_overlap"],
        ) == (digest, media_type, parsed.parser_version, size, overlap):
            return Document.model_validate(old), False
        totals = db.execute(
            """SELECT count(*) AS count,coalesce(sum(length(text)),0) AS chars
            FROM documents WHERE owner=%s""",
            (owner,),
        ).fetchone()
        assert totals is not None
        if (not old and totals["count"] >= self.settings.max_documents) or (
            totals["chars"] - (len(old["text"]) if old else 0) + len(text)
            > self.settings.max_owner_chars
        ):
            raise AtlasError("quota_exceeded", "Document storage quota exceeded.", 409)
        identifier = old["id"] if old else str(uuid4())
        now = datetime.now(UTC).isoformat()
        if old:
            db.execute("DELETE FROM chunks WHERE document_id=%s", (identifier,))
            db.execute(
                """UPDATE documents SET version=version+1,content_hash=%s,media_type=%s,
                parser_version=%s,chunk_size=%s,chunk_overlap=%s,text=%s,updated_at=%s
                WHERE id=%s AND owner=%s""",
                (
                    digest,
                    media_type,
                    parsed.parser_version,
                    size,
                    overlap,
                    text,
                    now,
                    identifier,
                    owner,
                ),
            )
        else:
            db.execute(
                """INSERT INTO documents(id,owner,source_key,version,content_hash,media_type,
                parser_version,chunk_size,chunk_overlap,text,status,created_at,updated_at)
                VALUES (%s,%s,%s,1,%s,%s,%s,%s,%s,%s,'indexed',%s,%s)""",
                (
                    identifier,
                    owner,
                    key,
                    digest,
                    media_type,
                    parsed.parser_version,
                    size,
                    overlap,
                    text,
                    now,
                    now,
                ),
            )
        self._insert_chunks(db, identifier, chunks)
        row = db.execute(
            DOCUMENT_SELECT + " WHERE d.id=%s AND owner=%s", (identifier, owner)
        ).fetchone()
        return Document.model_validate(row), old is None

    def put(self, owner: str, key: str, raw: bytes, media_type: str) -> tuple[Document, bool]:
        parsed = parse_document(raw, media_type, self.settings.max_upload_bytes)
        with db_connection(self.dsn) as db:
            owner_lock(db, owner)
            result = self._write(
                db,
                owner,
                key,
                raw,
                media_type,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
                parsed,
            )
            self._cancel(db, owner, key)
            return result

    def get(self, owner: str, document_id: str) -> Document:
        with db_connection(self.dsn) as db:
            row = db.execute(
                DOCUMENT_SELECT + " WHERE d.id=%s AND owner=%s", (document_id, owner)
            ).fetchone()
            if row is None:
                raise not_found()
            return Document.model_validate(row)

    def list(self, owner: str, limit: int, offset: int) -> Page[Document]:
        with db_connection(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            total = db.execute(
                "SELECT count(*) AS total FROM documents WHERE owner=%s", (owner,)
            ).fetchone()
            rows = db.execute(
                DOCUMENT_SELECT + " WHERE owner=%s ORDER BY d.id LIMIT %s OFFSET %s",
                (owner, limit, offset),
            ).fetchall()
            assert total is not None
            return Page(
                items=[Document.model_validate(row) for row in rows],
                total=total["total"],
                limit=limit,
                offset=offset,
            )

    def passages(self, owner: str, document_id: str, limit: int, offset: int) -> Page[Passage]:
        with db_connection(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            doc = db.execute(
                "SELECT id FROM documents WHERE id=%s AND owner=%s", (document_id, owner)
            ).fetchone()
            if doc is None:
                raise not_found()
            total = db.execute(
                "SELECT count(*) AS total FROM chunks WHERE document_id=%s", (document_id,)
            ).fetchone()
            rows = db.execute(
                PASSAGE_SELECT
                + " WHERE d.owner=%s AND d.id=%s ORDER BY c.ordinal LIMIT %s OFFSET %s",
                (owner, document_id, limit, offset),
            ).fetchall()
            assert total is not None
            return Page(
                items=[Passage.model_validate(row) for row in rows],
                total=total["total"],
                limit=limit,
                offset=offset,
            )

    def citation(self, owner: str, chunk_id: str) -> Passage:
        with db_connection(self.dsn) as db:
            row = db.execute(
                PASSAGE_SELECT + " WHERE d.owner=%s AND c.id=%s", (owner, chunk_id)
            ).fetchone()
            if row is None:
                raise not_found()
            return Passage.model_validate(row)

    def delete(self, owner: str, document_id: str) -> None:
        with db_connection(self.dsn) as db:
            owner_lock(db, owner)
            row = db.execute(
                "DELETE FROM documents WHERE id=%s AND owner=%s RETURNING source_key",
                (document_id, owner),
            ).fetchone()
            if row is None:
                raise not_found()
            self._cancel(db, owner, row["source_key"])
            db.execute(
                "DELETE FROM ingestion_jobs WHERE owner=%s AND source_key=%s",
                (owner, row["source_key"]),
            )

    def search(self, owner: str, query: SearchRequest) -> SearchResult:
        started = time.perf_counter()
        tokens = list(dict.fromkeys(terms(query.question)))[:32]
        rows: list[dict[str, Any]] = []
        if tokens:
            # Tokens contain only word characters; query syntax remains a bound parameter.
            expression = " | ".join("'" + token + "'" for token in tokens)
            with db_connection(self.dsn) as db:
                rows = db.execute(
                    PASSAGE_SELECT
                    + """ WHERE d.owner=%s AND c.search_vector
                    @@ to_tsquery('simple',%s) ORDER BY d.source_key,c.ordinal LIMIT 201""",
                    (owner, expression),
                ).fetchall()
        candidates = [Passage.model_validate(row) for row in rows[:200]]

        def rank(passage: Passage) -> tuple[float, float, str, int]:
            counts = Counter(terms(passage.text))
            return (
                -sum(token in counts for token in tokens) / max(len(tokens), 1),
                -sum(counts[token] for token in tokens) / max(sum(counts.values()), 1),
                passage.source_key,
                passage.ordinal,
            )

        passages = sorted(candidates, key=rank)[: query.limit]
        return SearchResult(
            status="evidence_found" if passages else "insufficient_evidence",
            retrieval_version="postgres-simple-overlap-v1",
            passages=passages,
            truncated=len(rows) > 200,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def enqueue(self, owner: str, key: str, raw: bytes, media_type: str) -> IngestionJob:
        # PDF/HTML parsing belongs to the bounded worker, before its write transaction.
        validate_upload(raw, media_type, self.settings.max_upload_bytes)
        if media_type in {"text/plain", "text/markdown"}:
            parse_document(raw, media_type, self.settings.max_upload_bytes)
        digest = hashlib.sha256(raw).hexdigest()
        with db_connection(self.dsn) as db:
            # One enqueue lock bounds global queue depth; worker work does not hold this lock.
            db.execute("SELECT pg_advisory_xact_lock(1895528102)")
            owner_lock(db, owner)
            old = db.execute(
                """SELECT * FROM ingestion_jobs WHERE owner=%s AND source_key=%s
                AND status IN ('queued','running')""",
                (owner, key),
            ).fetchone()
            if old and (
                old["content_hash"],
                old["media_type"],
                old["parser_version"],
                old["chunk_size"],
                old["chunk_overlap"],
            ) == (
                digest,
                media_type,
                parser_version(media_type),
                self.settings.chunk_size,
                self.settings.chunk_overlap,
            ):
                return IngestionJob.model_validate(old)
            self._cancel(db, owner, key)
            db.execute(
                """DELETE FROM ingestion_jobs WHERE owner=%s
                AND status IN ('succeeded','failed','cancelled')
                AND updated_at < clock_timestamp()-interval '7 days'""",
                (owner,),
            )
            stats = db.execute(
                """SELECT count(*) AS total,
                count(*) FILTER (WHERE status IN ('queued','running')) AS active,
                coalesce(sum(octet_length(raw)),0) AS bytes FROM ingestion_jobs WHERE owner=%s""",
                (owner,),
            ).fetchone()
            global_count = db.execute(
                "SELECT count(*) AS total FROM ingestion_jobs WHERE status IN ('queued','running')"
            ).fetchone()
            documents = db.execute(
                """SELECT count(*) AS total,coalesce(sum(length(text)),0) AS chars
                FROM documents WHERE owner=%s""",
                (owner,),
            ).fetchone()
            assert stats is not None and global_count is not None and documents is not None
            if stats["total"] >= 1000 or stats["active"] >= 20 or global_count["total"] >= 2000:
                raise AtlasError("queue_full", "Ingestion queue is full. Retry later.", 429)
            if stats["bytes"] + len(raw) + documents["chars"] > self.settings.max_owner_chars:
                raise AtlasError("quota_exceeded", "Document and staging quota exceeded.", 409)
            identifier = str(uuid4())
            row = db.execute(
                """INSERT INTO ingestion_jobs(id,owner,source_key,raw,media_type,
                content_hash,parser_version,chunk_size,chunk_overlap,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued') RETURNING *""",
                (
                    identifier,
                    owner,
                    key,
                    raw,
                    media_type,
                    digest,
                    parser_version(media_type),
                    self.settings.chunk_size,
                    self.settings.chunk_overlap,
                ),
            ).fetchone()
            return IngestionJob.model_validate(row)

    def job(self, owner: str, job_id: str) -> IngestionJob:
        with db_connection(self.dsn) as db:
            row = db.execute(
                "SELECT * FROM ingestion_jobs WHERE id=%s AND owner=%s", (job_id, owner)
            ).fetchone()
            if row is None:
                raise not_found()
            return IngestionJob.model_validate(row)
