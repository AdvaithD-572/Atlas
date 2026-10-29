# Local operations and API

Use README commands from repository root. `uv sync --locked` installs the exact
lockfile; `uv run` ensures project dependency consistency per the
[official uv documentation](https://docs.astral.sh/uv/guides/projects/).
The default SQLite profile needs no external service. PostgreSQL, worker and
local-model profiles have separate requirements below. `.env.example` documents
environment variables; it is not
automatically loaded. Set variables in the process environment when overriding.

## API contracts

All `/v1` routes require `Authorization: Bearer <token>`. Unauthenticated requests
return 401; missing and other-owner resources both return 404. Errors use
`{"error":{"code":"...","message":"..."}}`; no submitted values echoed.

| Route | Contract |
|---|---|
| PUT /v1/documents/{source_key} | Raw UTF-8 `text/plain` or `text/markdown`; creates 201 + Location, replacement/dedup 200 |
| GET /v1/documents | `limit` 1–100, `offset` 0–100000; items/total/limit/offset |
| GET /v1/documents/{id} | Index metadata, version/hash/config/count; no full text |
| GET /v1/documents/{id}/chunks | Paginated source passages in ordinal order |
| GET /v1/citations/{chunk_id} | Current owner-authorized passage and half-open Unicode character span |
| DELETE /v1/documents/{id} | 204, atomic document/chunk removal |
| POST /v1/search?mode=lexical | JSON question (1–512 chars), limit (1–20); authorized excerpts; mode also accepts vector/hybrid when enabled |
| POST /v1/answers?mode=lexical | JSON question; structured extracted claims, checked citations, conflicts/abstention and model metadata; generation must be enabled |
| POST /v1/documents/{id}/vector-index | Explicit bounded semantic index; PostgreSQL and embeddings must be enabled |
| GET /v1/capabilities | Authenticated backend, retrieval modes and generation availability |
| POST /v1/ingestions/{source_key} | PostgreSQL only: raw UTF-8 upload, 202 job status |
| GET /v1/jobs/{id} | Owner-scoped state, attempts and safe error code |
| GET /health/live | Process responds; no dependency claim |
| GET /health/ready | Expected schema/tables and installed configured model metadata; 503 when unavailable; no inference-quality claim |

Upload keys: 1–120 characters, alphanumeric first, then alphanumeric/underscore/
dot/hyphen. They are source identifiers, never filesystem paths. Raw Markdown is
stored literally, not rendered as HTML. Source spans are zero-based Unicode code
point offsets in unchanged decoded UTF-8; CRLF and Unicode are preserved.

Per-process authenticated limit defaults to 120 requests/minute/principal, with
429/Retry-After. Storage lock wait is five seconds; upload read timeout ten seconds.
Launch with the README concurrency limit. No distributed rate limit or reverse
proxy is included. Use a TLS reverse proxy and production identity design before
network deployment; no TLS bypass is appropriate.

## Administration and retention

Explicit `python -m atlas migrate --database PATH` applies numbered SQL files in
one transaction and is idempotent. Runtime will not create missing storage. Take
an owner-authorized offline backup before migrations. Initial schema rollback is
restore-from-backup; dropping tables destroys documents and is not automated.
Do not edit applied migrations; append a new version.

Credential provisioning uses exclusive token creation and a short file lock.
If a process dies holding `.local/.credentials.lock`, verify no provision process
is running before removing that exact stale lock. Keep the token file private;
Unix mode 0600 is requested, while Windows ACLs must be managed by the operator.
Removing a digest and restarting revokes access, not documents. Do not recycle
an owner ID to another person without an explicit ownership decision.

Replacement removes prior text/chunks and invalidates previous citation IDs.
Deletion removes active database records and derived chunks transactionally;
there are no app caches or stored query transcripts. SQLite secure_delete is on.
This is not a forensic erasure claim for SSD blocks, backups or OneDrive history.
Use synthetic/non-sensitive documents until storage location and backup retention
are chosen. A non-synced directory can be set with ATLAS_DATABASE_PATH and
ATLAS_CREDENTIALS_PATH. Credential files also need the chosen backup policy.

Application logs emit only generated request IDs, HTTP method, status, duration
and exception class. Uvicorn access logging is disabled by the launch command to
avoid recording query strings. Do not enable verbose request/body logging.

Lexical retrieval uses SQLite FTS5 OR matching on at most 32 unique query tokens,
materializes only owner-authorized candidates (200 cap, explicit truncated flag),
and ranks by query-term coverage then term density. Ties use source key/ordinal.
Scores never use other owners' corpus statistics. This simple baseline is not
BM25 or a confidence/sufficiency estimator; matching text may not answer a question.
FTS triggers and backfill follow [SQLite's FTS5 documentation](https://www.sqlite.org/fts5.html).
Migration 003 enables FTS secure-delete; SQLite >=3.42 with FTS5 is required.
No-evidence means no lexical hits, not a model judgment of answerability.

## PostgreSQL and local inference

Provision the local principal as described in README. Generate database
credentials only on first setup; `init-local` refuses to overwrite existing files.
Never print expanded Compose config or the generated DSN.

```powershell
uv run --locked python -m atlas.worker init-local
docker compose --env-file .local/postgres.env config --quiet
docker compose --env-file .local/postgres.env up -d --wait
$env:ATLAS_POSTGRES_DSN = (Get-Content .local/postgres.dsn -Raw).Trim()
uv run --locked python -m atlas.worker migrate
```

The same environment can run the API using the README command. Run
`uv run --locked python -m atlas.worker run` in another terminal with the same
DSN and principal registry. PostgreSQL migration 002 adds embeddings; readiness
expects schema version 2. SQLite and PostgreSQL have separate migration histories.
For API-only configuration, `ATLAS_POSTGRES_DSN_PATH=.local/postgres.dsn` is an
alternative; do not set both DSN settings. Restart API and worker on revocation.

Optional native local generation and semantic search:

```powershell
$env:ATLAS_GENERATION_ENABLED = 'true'
$env:ATLAS_VECTOR_ENABLED = 'true'
$env:ATLAS_EMBEDDING_MODEL = 'all-minilm:latest'
$env:ATLAS_GENERATION_MODEL = 'qwen3:1.7b'
```

These model names were exercised against local Ollama on port 11434. Models must
already be installed, and server metadata must identify a local model. Cloud
models and non-loopback providers are rejected. The API pins installed digests in
responses; a model change requires reindexing documents. Select **Index for
semantic search** for each document before vector/hybrid search. At most 128
chunks are indexed per call; larger documents return a safe limit error.
Source replacement removes old embeddings. Coverage is reported by search.
The generation UI is capability-gated, and tokens stay only in browser memory.

Real PostgreSQL tests use isolated disposable schemas:

```powershell
$env:ATLAS_TEST_POSTGRES_DSN = (Get-Content .local/postgres.dsn -Raw).Trim()
uv run --locked pytest -q --tb=no --cov=atlas --cov-report=term
```

Without this variable the PostgreSQL tests are skipped. `--tb=no` prevents pytest
assertion introspection from exposing connection strings. Never use production
credentials or a production database for these tests.

## Local container package

Docker Desktop, generated database credentials and the provisioned principal
registry are prerequisites. Start PostgreSQL as above, then:

```powershell
docker build -t atlas-app:local .
docker compose --env-file .local/postgres.env -f compose.yaml -f compose.app.yaml config --quiet
docker compose --env-file .local/postgres.env -f compose.yaml -f compose.app.yaml --profile tools run --rm migrate
docker compose --env-file .local/postgres.env -f compose.yaml -f compose.app.yaml up -d --wait api worker
uv run --locked python -m scripts.container_smoke
```

Open `http://127.0.0.1:8080`. The image runs as UID/GID 10001, serves the built
frontend under a self-only CSP, and uses a read-only runtime filesystem with a
bounded temporary mount. API readiness probes storage. The worker has no health
probe; a running container alone does not prove job progress. The smoke explicitly
enqueues, polls, searches, resolves a source and deletes its synthetic document.

This container profile disables models. Host Ollama's loopback endpoint is not
container loopback; do not weaken the provider boundary to make this profile use
host networking. The full model path was verified with the native API and local
Ollama, not with this container profile.

Stop the app with the same Compose files and `stop api worker`; ordinary
`down` preserves the database volume. Never add `-v` as routine recovery.
Backup restoration, production roles/TLS and remote deployment are unverified.
Pinned CI checks exist in `.github/workflows/ci.yml`, but no hosted run is claimed.
See [deployment evidence](engineering/deployment-evidence.md).

