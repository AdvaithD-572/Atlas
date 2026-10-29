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
| PUT /v1/documents/{source_key} | Raw UTF-8 `text/plain`, `text/markdown`, `text/html`, or binary `application/pdf`; creates 201 + Location, replacement/dedup 200 |
| GET /v1/documents | `limit` 1–100, `offset` 0–100000; items/total/limit/offset |
| GET /v1/documents/{id} | Index metadata, version/hash/config/count; no full text |
| GET /v1/documents/{id}/chunks | Paginated source passages in ordinal order |
| GET /v1/citations/{chunk_id} | Current owner-authorized passage and half-open Unicode character span |
| DELETE /v1/documents/{id} | 204, atomic document/chunk removal |
| POST /v1/search?mode=lexical | JSON question (1–512 chars), limit (1–20); authorized excerpts; mode also accepts vector/hybrid when enabled |
| POST /v1/answers?mode=lexical | JSON question; structured extracted claims, checked citations, conflicts/abstention and model metadata; generation must be enabled |
| POST /v1/documents/{id}/vector-index | Explicit bounded semantic index; PostgreSQL and embeddings must be enabled |
| GET /v1/capabilities | Authenticated backend, retrieval modes and generation availability |
| POST /v1/ingestions/{source_key} | PostgreSQL only: same four upload formats, 202 job status; worker validates parsing |
| GET /v1/jobs/{id} | Owner-scoped state, attempts and safe error code |
| GET /health/live | Process responds; no dependency claim |
| GET /health/ready | Expected schema/tables and installed configured model metadata; 503 when unavailable; no inference-quality claim |

Upload keys: 1–120 characters, alphanumeric first, then alphanumeric/underscore/
dot/hyphen. They are source identifiers, never filesystem paths. Raw Markdown is
stored literally, not rendered as HTML. Source spans are zero-based Unicode code
point offsets in unchanged decoded UTF-8 for text/Markdown; CRLF and Unicode are
preserved. PDF/HTML spans refer to extracted text, with nullable page number or
heading on each passage. Source locations do not address the original PDF bytes
or HTML markup. Original uploads are not retained after successful indexing.

PDFs require a text layer, at most 200 pages, and at most 1 MiB of extracted text;
there is no OCR or password support. Parsing runs in a child process with a
10-second deadline and one child per API/worker process. Linux additionally caps
address space at 256 MiB and CPU time at eight seconds; Windows lacks this OS
memory ceiling. HTML extraction ignores scripts, embedded content and explicit
hidden attributes, never fetches URLs, and bounds node count/depth. It does not
apply CSS. Both formats retain the default 256 KiB upload limit, configurable up
to 1 MiB.

Before upgrading to these parsers, back up storage, stop/drain API and worker
writers, apply SQLite migration 004 or PostgreSQL migration 003, and restart both
with the new build. Existing documents and IDs are preserved. An older build
rejects the new schema; rollback requires a compatible build or backup restore.

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

Create the restricted runtime login after migration:

```powershell
uv run --locked python -m atlas.deployment init-runtime
Remove-Item Env:ATLAS_POSTGRES_DSN
$env:ATLAS_POSTGRES_DSN_PATH = '.local/runtime.dsn'
```

Run the API using the README command and `uv run --locked python -m atlas.worker run`
in another terminal with that runtime DSN file and principal registry.
PostgreSQL migration 002 adds embeddings; readiness
expects schema version 2. SQLite and PostgreSQL have separate migration histories.
API and worker both support `ATLAS_POSTGRES_DSN_PATH`; do not set both DSN settings.
Keep the bootstrap administrator DSN for explicit migrations only. Runtime grants
are schema USAGE, SELECT on migration metadata and CRUD on the four app tables;
no table ownership, DDL, TRUNCATE, role administration or superuser privileges.
The shared application login still relies on server-side owner predicates, not
database row-level security. Restart API and worker on credential revocation.

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

The installed all-minilm model rejected some 800-character documentation chunks
because their token count exceeded its context. The documented development
comparison passed with `ATLAS_CHUNK_SIZE=400` and `ATLAS_CHUNK_OVERLAP=80`.
These are character limits, not a guarantee for all languages/content. Re-upload
under the desired configuration and re-index if chunk settings change. Provider
truncation remains disabled; oversized model input fails instead of silently
dropping source text. The recognized local-model context rejection returns HTTP
422 with code `embedding_context_exceeded` and actionable chunk/query guidance.
Unknown provider rejections retain a generic safe error. Existing lexical indexing
remains usable after vector failure. `uv run --locked python -m
scripts.embedding_limit_smoke` verifies the frozen 800/120 rejection and 400/80
recovery against actual local Ollama/PostgreSQL in isolated schemas.
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
uv run --locked python -m atlas.deployment init-runtime
docker compose --env-file .local/postgres.env -f compose.yaml -f compose.app.yaml up -d --wait api worker
uv run --locked python -m scripts.container_smoke
```

Open `http://127.0.0.1:8080`. The image runs as UID/GID 10001, serves the built
frontend under a self-only CSP, and uses a read-only runtime filesystem with a
bounded temporary mount. API readiness probes storage. Worker health requires a
heartbeat updated after the actual processing loop and a working database; old,
missing, invalid or future timestamps fail. The smoke explicitly
enqueues, polls, searches, resolves a source and deletes its synthetic document.

This container profile disables models. Host Ollama's loopback endpoint is not
container loopback; do not weaken the provider boundary to make this profile use
host networking. The full model path was verified with the native API and local
Ollama, not with this container profile.

Stop the app with the same Compose files and `stop api worker`; ordinary
`down` preserves the database volume. Never add `-v` as routine recovery.
Skip `init-runtime` if its files already exist; it deliberately refuses overwrite.
On Linux, private mode-0600 files must be readable by the selected non-root runtime
UID. Set `ATLAS_RUNTIME_UID=$(id -u)` and `ATLAS_RUNTIME_GID=$(id -g)` in the shell
before Compose, or provision private files for a dedicated service account. Never
make credentials world-readable. `scripts.package_checks` aligns IDs automatically
on Linux and refuses root execution there. Windows still needs appropriate ACLs.

Shared verification commands:

```powershell
uv run --locked python -m scripts.verify --database-file .local/postgres.dsn
uv run --locked python -m scripts.package_checks
uv run --locked python -m scripts.linux_permissions_smoke
```

The package check uses the current Compose project, verifies worker/HTTP lifecycle,
runs a disposable restore drill, temporarily replaces port 8080 with HTTPS on
127.0.0.1:8443, verifies trust/hostname rejection and lifecycle, then restores HTTP.
Do not run it during active local user work. `--initialize` is for fresh CI
workspaces only and refuses an existing `.local` directory. It does not erase
database volumes. No hosted run is claimed: this checkout has no Git remote.

For HTTPS separately, generate a two-day **local test certificate** with
`uv run --locked python -m scripts.tls_smoke --init-certificate`, then add
`-f compose.tls.yaml` to Compose. Compose >=2.24.4 is required for
[`!override`](https://docs.docker.com/reference/compose-file/merge/#replace-value);
the observed local version is 5.6.0. Clients trust the certificate explicitly.
No machine/browser trust store is modified. Certificate generation refuses
overwrite; expire/replace local test artifacts deliberately before another trial.
A public deployment needs an operator-controlled hostname, trusted certificate
issuance/renewal and an appropriate identity/monitoring policy; this local profile
does not supply those external resources.

### Backup and recovery

`uv run --locked python -m scripts.backup_restore_drill` creates two new UUID-named
databases, writes synthetic versioned documents/jobs/vectors, performs actual
custom-format pg_dump/pg_restore, compares all restored rows and owner/citation
behavior, rejects a corrupt archive and removes only its disposable databases.
The dump, checksum and measured timings remain in `.local/backup-drills/`.
These timings are not a production recovery-time objective.

For retained data, quiesce writers for a coordinated application/credential backup,
use PostgreSQL custom-format dumps with an authorized backup account, and keep the
private credential registry separately under equivalent access restrictions.
Encrypt off-host copies, record checksums and migration/image versions, and choose
retention/RPO with the data owner. Restore into a new empty database with
`pg_restore --exit-on-error --no-owner --no-acl`, run explicit migrations and
provision runtime grants, then verify readiness, owner isolation and source
citations before switching the DSN. Preserve the previous database and image for
rollback. Do not restore over live data or automatically drop schema versions.
Deletion cannot erase pre-existing backups, WAL or synchronized file history;
purging those is part of the operator's retention policy.
The archive/restore model follows the
[PostgreSQL 17 backup documentation](https://www.postgresql.org/docs/17/backup-dump.html).

See [deployment evidence](engineering/deployment-evidence.md).

