import hashlib
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from atlas.config import Settings
from atlas.database import connection
from atlas.errors import AtlasError, not_found
from atlas.ingestion import Chunk, parse_document
from atlas.retrieval import SearchRequest, SearchResult, lexical_search
from atlas.schemas import Document, Page, Passage

DOCUMENT_SELECT = """
SELECT d.*, (SELECT count(*) FROM chunks c WHERE c.document_id=d.id) AS chunk_count
FROM documents d
"""
PASSAGE_SELECT = """
SELECT c.*, d.source_key, d.version FROM chunks c
JOIN documents d ON d.id=c.document_id
"""


def insert_chunks(db: sqlite3.Connection, document_id: str, chunks: list[Chunk]) -> None:
    db.executemany(
        "INSERT INTO chunks (id,document_id,ordinal,start,end,text,page_number,heading) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (str(uuid4()), document_id, c.ordinal, c.start, c.end, c.text, c.page_number, c.heading)
            for c in chunks
        ],
    )


class DocumentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, owner: str, query: SearchRequest) -> SearchResult:
        return lexical_search(self.settings.database_path, owner, query)

    def put(self, owner: str, key: str, raw: bytes, media_type: str) -> tuple[Document, bool]:
        parsed = parse_document(raw, media_type, self.settings.max_upload_bytes)
        text = parsed.text
        chunks = parsed.chunks(self.settings.chunk_size, self.settings.chunk_overlap)
        digest = hashlib.sha256(raw).hexdigest()
        now = datetime.now(UTC).isoformat()
        with connection(self.settings.database_path) as db:
            # Serialize read-modify-write and quota checks to prevent lost versions.
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                DOCUMENT_SELECT + " WHERE owner=? AND source_key=?", (owner, key)
            ).fetchone()
            if old and all(
                (
                    old["content_hash"] == digest,
                    old["parser_version"] == parsed.parser_version,
                    old["chunk_size"] == self.settings.chunk_size,
                    old["chunk_overlap"] == self.settings.chunk_overlap,
                    old["media_type"] == media_type,
                )
            ):
                return Document.model_validate(dict(old)), False
            count, chars = db.execute(
                "SELECT count(*), coalesce(sum(length(text)), 0) FROM documents WHERE owner=?",
                (owner,),
            ).fetchone()
            if (not old and count >= self.settings.max_documents) or (
                chars - (len(old["text"]) if old else 0) + len(text) > self.settings.max_owner_chars
            ):
                raise AtlasError("quota_exceeded", "Document storage quota exceeded.", 409)
            document_id = old["id"] if old else str(uuid4())
            version = old["version"] + 1 if old else 1
            if old:
                db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                db.execute(
                    """UPDATE documents SET version=?,content_hash=?,media_type=?,parser_version=?,
                    chunk_size=?,chunk_overlap=?,text=?,updated_at=? WHERE id=? AND owner=?""",
                    (
                        version,
                        digest,
                        media_type,
                        parsed.parser_version,
                        self.settings.chunk_size,
                        self.settings.chunk_overlap,
                        text,
                        now,
                        document_id,
                        owner,
                    ),
                )
            else:
                db.execute(
                    "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        document_id,
                        owner,
                        key,
                        version,
                        digest,
                        media_type,
                        parsed.parser_version,
                        self.settings.chunk_size,
                        self.settings.chunk_overlap,
                        text,
                        "indexed",
                        now,
                        now,
                    ),
                )
            insert_chunks(db, document_id, chunks)
            row = db.execute(
                DOCUMENT_SELECT + " WHERE d.id=? AND owner=?", (document_id, owner)
            ).fetchone()
            return Document.model_validate(dict(row)), old is None

    def get(self, owner: str, document_id: str) -> Document:
        with connection(self.settings.database_path) as db:
            row = db.execute(
                DOCUMENT_SELECT + " WHERE d.id=? AND owner=?", (document_id, owner)
            ).fetchone()
            if row is None:
                raise not_found()
            return Document.model_validate(dict(row))

    def list(self, owner: str, limit: int, offset: int) -> Page[Document]:
        with connection(self.settings.database_path) as db:
            db.execute("BEGIN")
            total = db.execute("SELECT count(*) FROM documents WHERE owner=?", (owner,)).fetchone()[
                0
            ]
            rows = db.execute(
                DOCUMENT_SELECT + " WHERE owner=? ORDER BY d.id LIMIT ? OFFSET ?",
                (owner, limit, offset),
            ).fetchall()
            return Page(
                items=[Document.model_validate(dict(row)) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    def passages(self, owner: str, document_id: str, limit: int, offset: int) -> Page[Passage]:
        with connection(self.settings.database_path) as db:
            db.execute("BEGIN")
            doc = db.execute(
                "SELECT id FROM documents WHERE id=? AND owner=?", (document_id, owner)
            ).fetchone()
            if doc is None:
                raise not_found()
            total = db.execute(
                "SELECT count(*) FROM chunks WHERE document_id=?", (document_id,)
            ).fetchone()[0]
            rows = db.execute(
                PASSAGE_SELECT + " WHERE d.owner=? AND d.id=? ORDER BY c.ordinal LIMIT ? OFFSET ?",
                (owner, document_id, limit, offset),
            ).fetchall()
            return Page(
                items=[Passage.model_validate(dict(row)) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    def citation(self, owner: str, chunk_id: str) -> Passage:
        with connection(self.settings.database_path) as db:
            row = db.execute(
                PASSAGE_SELECT + " WHERE d.owner=? AND c.id=?", (owner, chunk_id)
            ).fetchone()
            if row is None:
                raise not_found()
            return Passage.model_validate(dict(row))

    def delete(self, owner: str, document_id: str) -> None:
        with connection(self.settings.database_path) as db:
            result = db.execute(
                "DELETE FROM documents WHERE id=? AND owner=?", (document_id, owner)
            )
            if result.rowcount == 0:
                raise not_found()
