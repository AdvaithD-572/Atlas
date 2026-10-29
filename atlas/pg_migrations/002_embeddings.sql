CREATE TABLE chunk_embeddings (
    chunk_id text PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model text NOT NULL,
    model_digest text NOT NULL CHECK(model_digest ~ '^[0-9a-f]{64}$'),
    dimensions integer NOT NULL CHECK(dimensions BETWEEN 1 AND 4096),
    embedding public.vector NOT NULL,
    index_version text NOT NULL DEFAULT 'cosine-exact-v1',
    indexed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK(public.vector_dims(embedding) = dimensions)
);
CREATE INDEX embeddings_model ON chunk_embeddings(model, model_digest, dimensions);
