# PostgreSQL and durable ingestion evidence

Verified 2026-10-20. This is a local development milestone, not a production
deployment, retrieval-quality benchmark, or proof of vector retrieval.

## Implemented boundary

`atlas/postgres.py` provides `PostgresDocumentService(settings, dsn)` with the
same document, passage, citation and lexical-search contracts as the SQLite
service, plus `enqueue` and owner-scoped `job` lookup. The API integration is in
the existing app factory/routes. `atlas/worker.py` supplies `claim`, `process`,
`run_once`, and the administration/worker CLI. PostgreSQL migration 001 creates
documents, chunks, a GIN full-text index and a durable ingestion queue. pgvector
is installed and its real cosine-distance operator was tested; embeddings and
vector/hybrid ranking remain a separate milestone.

**Proposed default:** use PostgreSQL itself for the initial bounded queue instead
of adding Redis and Celery. Row claims use `FOR UPDATE SKIP LOCKED`; a unique
active-source index and transaction advisory locks prevent duplicate/stale writes.
The tradeoff is contention on the database and a deliberately small workload,
not a claim of fleet-scale throughput.

The queue stores parser/chunk configuration with each job, exposes attempts and
safe error codes, and keeps the last indexed version available until replacement
commits atomically. Leases default to 30 seconds; expiry permits recovery with a
new lease token, with at most three attempts. Transient storage failures use
bounded exponential backoff plus jitter. Permanent validation/configuration or
authorization failures stop retrying. Workers recheck owner configuration and
lease ownership before writes. Newer PUT/enqueue operations cancel older active
work. Deletion purges associated job artifacts and cascades chunks; a stale
worker cannot recreate the removed document.

Bounds: 20 active jobs per owner, 2,000 globally, 1,000 retained job records per
owner, upload limits and a shared document/staged-content quota. Terminal payloads
are cleared immediately. Terminal metadata older than seven days is cleaned on
the next enqueue for that owner. Owner document-count/content quotas are also
checked inside the commit transaction. Connections have a five-second connect
timeout, five-second lock timeout, ten-second statement timeout and fifteen-second
idle-transaction timeout. Run one worker initially; multiworker claim behavior is
tested, but representative load/performance measurement is pending.

Search uses PostgreSQL `simple` full-text token matching, then the same bounded
overlap/density ranking policy as SQLite. It authorizes passages in SQL, caps
candidates at 200, uses deterministic ties, and has no global IDF statistics that
could make another owner's corpus affect ranking. The retrieval version is
`postgres-simple-overlap-v1`; PostgreSQL and SQLite tokenization differences must
be measured on a frozen dataset before comparing retrieval quality.

## Reproducible local commands

Run from the repository root using the locked environment. Never print or commit
the generated `.local/postgres.env` or `.local/postgres.dsn` files.

```powershell
# Only once, and only when neither generated file already exists:
.venv\Scripts\python.exe -m atlas.worker init-local
docker compose --env-file .local/postgres.env config --quiet
docker compose --env-file .local/postgres.env up -d --wait
$env:ATLAS_POSTGRES_DSN = (Get-Content .local/postgres.dsn -Raw).Trim()
.venv\Scripts\python.exe -m atlas.worker migrate
.venv\Scripts\python.exe -m atlas.worker run
```

The API can use `ATLAS_POSTGRES_DSN_PATH=.local/postgres.dsn`; do not configure
both DSN and DSN-path settings. A worker needs the DSN environment variable and
the same provisioned principal configuration as the API. `once` claims at most
one available job and exits; `run` polls continuously. Restart API and worker
after changing principal configuration, including revocation. The queue does not
reload credential configuration automatically.

```powershell
$env:ATLAS_TEST_POSTGRES_DSN = (Get-Content .local/postgres.dsn -Raw).Trim()
.venv\Scripts\python.exe -m pytest tests/test_postgres.py -q --tb=no `
  --cov=atlas.postgres --cov=atlas.worker --cov-report=term-missing
.venv\Scripts\python.exe -m ruff check atlas/postgres.py atlas/worker.py tests/test_postgres.py
.venv\Scripts\python.exe -m mypy atlas/postgres.py atlas/worker.py
```

Each real-database test creates a random `atlas_test_...` schema and removes only
that schema in teardown. Test search paths do not include public fallback tables;
the extension type/operator is explicitly qualified as `public.vector` where
needed. No existing document tables are reset. Without the test DSN, real DB
tests report skipped rather than substitute mocks. Fault-injection tests simulate
storage exceptions while retaining real PostgreSQL rollback/job-state checks.
Tracebacks are suppressed in this command because pytest assertion introspection
can disclose raw connection strings.

## Executed checks and results

| Check actually run | Result |
|---|---|
| Initial contract collection before implementation | Expected RED: missing `atlas.postgres` implementation |
| `docker compose --env-file .local/postgres.env config --quiet` | Passed |
| Compose startup and health | Passed; `127.0.0.1:55432` only, named persistent volume |
| Explicit `python -m atlas.worker migrate` | Passed; idempotence also tested against isolated schemas |
| Real PostgreSQL/worker suite, final run | 18 passed, one dependency deprecation warning, 5.46 seconds |
| Module coverage from that suite | PostgreSQL 99%, worker 92%, combined 97% (276 statements) |
| Strict mypy on both implementation modules | Passed |
| Ruff check on both modules and PostgreSQL tests | Passed after formatting |
| Actual database version query | PostgreSQL 17.11, pgvector 0.8.7 |
| Authentication-rule query after hardening | Zero `trust` authentication rules |

The actual image is pinned to
`pgvector/pgvector:0.8.7-pg17-bookworm@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d`.
Fresh initialization requires SCRAM for both local sockets and TCP. The existing
development volume was updated to the same authentication policy without deleting
data. Compose limits the database to one CPU, 512 MiB memory and 100 processes.

The 18 tests cover document lifecycle/dedup/versioning; citation invalidation;
cross-owner reads/search/deletion; concurrent dedup and exclusive claims; lease
recovery and stale claims; deletion/newer-write fences; retry exhaustion and
payload cleanup; queue bounds/dedup; rollback; transient retry/permanent failure;
owner revocation; search cap and cross-tenant rank independence; real pgvector SQL;
schema drift/readiness; staging quotas; secret-free provisioning output; and real
CLI and HTTP queue/status/search/delete flows.

An additional readiness test initially failed because its test schema could fall
back to public tables. The fixture now excludes that fallback and the failure
test passes. That failed pytest diagnostic exposed the generated local database
password. It was immediately rotated, the ignored files updated, and subsequent
runs suppress tracebacks. The old credential is invalid; no credential is recorded
in this document or committed source.

## Skills and verified sources

Read and applied these installed instructions from
`C:/Users/advai/.codex/skills/<name>/SKILL.md`:

| Skill | Actual application |
|---|---|
| postgres-patterns | Owner-first predicates/indexes, GIN full-text index, bounded connections, SKIP LOCKED claims |
| database-migrations | Explicit numbered transactional migration, schema-version readiness and future-version rejection |
| docker-patterns | Loopback port, persistent volume, secret injection, immutable image digest, health/resource bounds |
| deployment-patterns | Dependency readiness, explicit migration/run commands, honest rollback and deployment limitations |
| python-testing, tdd-workflow | Executed RED, isolated real-database contracts, injected failures, executed GREEN/coverage |
| verification-loop | Actual lint/type/integration checks with results and known gaps |
| api-design, error-handling | Structured job states, stable IDs, scoped lookups and safe error codes |
| security-review, content-hash-cache-pattern | Owner/config-aware dedup, secret handling, stale-write fencing and deletion verification |

Background worker design follows the PostgreSQL concurrency guidance above; no
Celery/Redis-specific skill or runtime was introduced. No production deployment
was attempted. The relevant primary references were checked during implementation:
[PostgreSQL SELECT/row locks](https://www.postgresql.org/docs/current/sql-select.html),
[Psycopg transaction contexts](https://www.psycopg.org/psycopg3/docs/basic/transactions.html),
and [pgvector installation/image documentation](https://github.com/pgvector/pgvector).

## Remaining limits and recovery

- Database service uses a locally generated administrator credential for this
  development slice. Separate migration/runtime roles, RLS defense in depth,
  externally reachable TLS and deployment hardening are pending.
- Deletion removes active database rows and staged job payloads. PostgreSQL WAL,
  disk pages, snapshots and backups are not secure-erased; their retention policy
  must be implemented for a deployment handling sensitive documents.
- A new queued document has no indexed document ID until commit; job cancellation
  is not a public endpoint in this slice. Existing-document deletion cancels and
  removes related pending work. Queue metadata cleanup is enqueue-triggered.
- Continuous worker CLI shutdown/restart under real process termination, prolonged
  storage outage/load tests, missing-migration-file diagnostics, container restart
  durability, backup restore and production migration rollback are not yet
  verified. The real tests do verify expired-lease recovery and SQL rollback.
- No downgrade migration intentionally destroys documents. Stop clients before
  restoring a compatible database snapshot or use a forward corrective migration.
  `docker compose down` preserves the named volume; never use `down -v` to recover
  from an ordinary failure.
- The dependency warning is Starlette's TestClient/httpx deprecation. It does not
  invalidate the passing HTTP assertions but should be resolved in a controlled
  dependency update.
