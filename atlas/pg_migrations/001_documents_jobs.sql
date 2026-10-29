CREATE TABLE documents (
    id text PRIMARY KEY,
    owner text NOT NULL,
    source_key text NOT NULL,
    version integer NOT NULL CHECK(version > 0),
    content_hash text NOT NULL,
    media_type text NOT NULL,
    parser_version text NOT NULL,
    chunk_size integer NOT NULL CHECK(chunk_size BETWEEN 64 AND 4000),
    chunk_overlap integer NOT NULL CHECK(chunk_overlap BETWEEN 0 AND chunk_size / 2),
    text text NOT NULL,
    status text NOT NULL CHECK(status = 'indexed'),
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE(owner, source_key)
);
CREATE INDEX documents_owner_id ON documents(owner, id);
CREATE TABLE chunks (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    start integer NOT NULL,
    "end" integer NOT NULL,
    text text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    embedding public.vector,
    UNIQUE(document_id, ordinal),
    CHECK(start >= 0 AND "end" > start)
);
CREATE INDEX chunks_document ON chunks(document_id);
CREATE INDEX chunks_lexical ON chunks USING gin(search_vector);
CREATE TABLE ingestion_jobs (
    id text PRIMARY KEY,
    owner text NOT NULL,
    source_key text NOT NULL,
    raw bytea,
    media_type text NOT NULL,
    content_hash text NOT NULL,
    parser_version text NOT NULL,
    chunk_size integer NOT NULL,
    chunk_overlap integer NOT NULL,
    status text NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
    error_code text,
    document_id text REFERENCES documents(id) ON DELETE SET NULL,
    lease_token text,
    lease_until timestamptz,
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK(raw IS NULL OR octet_length(raw) <= 1048576)
);
CREATE INDEX jobs_claim ON ingestion_jobs(status, available_at, created_at);
CREATE INDEX jobs_owner_key ON ingestion_jobs(owner, source_key);
CREATE UNIQUE INDEX jobs_one_active_source ON ingestion_jobs(owner, source_key)
    WHERE status IN ('queued', 'running');
