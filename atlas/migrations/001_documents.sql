CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    source_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version > 0),
    content_hash TEXT NOT NULL,
    media_type TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    chunk_size INTEGER NOT NULL,
    chunk_overlap INTEGER NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'indexed'),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner, source_key)
);
CREATE INDEX documents_owner_id ON documents(owner, id);
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    start INTEGER NOT NULL,
    end INTEGER NOT NULL,
    text TEXT NOT NULL,
    UNIQUE(document_id, ordinal),
    CHECK(start >= 0 AND end > start)
);
CREATE INDEX chunks_document ON chunks(document_id);

