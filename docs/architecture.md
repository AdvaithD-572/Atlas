# Architecture and decisions

## Current boundaries

`atlas/main.py`: application factory, safe errors, health and redacted telemetry.
`api.py`: HTTP contracts and bounded raw upload reading. `security.py`: principal
validation and bounded process-local rate admission. `config.py`: validated
operator configuration. `services.py`: lifecycle use cases and scoped SQL.
`ingestion.py`: typed parsing and source-preserving chunks; `pdf_parser.py` is an
isolated, resource-bounded PDF text extractor.
`database.py` and `migrations/`: connections and explicit schema upgrades.
`schemas.py`: canonical Pydantic output types. `__main__.py`: local administration.

Data flow: authenticated raw upload -> validated text or PDF/HTML extraction -> bounded chunks
-> short atomic transaction -> indexed document and passages. Every resource
lookup includes owner scope. There is no shared answer cache or filesystem upload path.
Chunk IDs are new on reindex; existing document ID stays stable and version rises.
Old content/chunks are removed, rather than retaining a historical document store.

## Decisions

- **Confirmed:** modular architecture, authorization at every data boundary,
  no paid services, separate retrieval/answer evaluation and honest status.
- **Discovered:** initial repository was empty except AGENTS.md; Python/Node/uv
  available. Docker runs; local Ollama embedding and generation models were
  installed and exercised on 2026-10-20.
- **Proposed default:** SQLite is a small, runnable development baseline while
  PostgreSQL/pgvector/worker are a distinct milestone. This avoids pretending
  local SQL tests prove PostgreSQL behavior. It incurs a migration cost; the
  services isolate SQL but do not claim a ready-made interchangeable DB adapter.
- **Proposed default:** synchronous ingestion, maximum 256 KiB by default,
  overlap no greater than half a chunk, maximum 4096 chunks, per-owner document
  and character quotas. The integrated PostgreSQL worker parses PDF/HTML outside
  database transactions and rechecks ownership and its lease before publication.
  The small SQLite development profile retains synchronous bounded ingestion.
- **Proposed default:** opaque random operator-provisioned bearer tokens hashed
  with SHA-256. These are high-entropy tokens, not passwords. No JWT/OAuth/account
  service needed for the first local slice. Revocation requires editing the
  digest registry and restarting the app; production identity remains pending.
- **Proposed default:** raw PUT body and stable source key avoid multipart and
  untrusted path handling. Same owner/key/hash/media/parser/chunk config reuses
  the current index; any change atomically replaces it. Different keys are
  distinct source identities even if content is identical.

## Integrated components (2026-10-20)

| Boundary | Implementation |
|---|---|
| PostgreSQL lifecycle and lexical search | `atlas/postgres.py`, explicit `pg_migrations/` |
| Durable ingestion | `atlas/worker.py`; database queue, leases, bounded retries |
| Vector and hybrid retrieval | `atlas/vector_retrieval.py`; owner-scoped cosine distance and RRF |
| Local inference | `atlas/providers.py`; small typed interface, bounded validated Ollama calls |
| Grounded answer orchestration | `atlas/questions.py`; retrieval, extraction, citation reauthorization |
| Evaluation | `atlas/evaluation.py`; frozen dataset/corpus, pinned modes, minimized reports |
| Browser client | `frontend/src/`; React, strict TypeScript, runtime response validation |
| Packaging | Dockerfile, Compose database/API/worker, static assets served by FastAPI |
| Deployment administration | `atlas/deployment.py`; explicit runtime grants and private DSN provisioning |
| Experimental quality study | `atlas/quality_study.py`, `scripts/quality_study.py`; strict local reranker and separately attributed model diagnostics |

**Proposed default:** PostgreSQL holds the durable queue, avoiding an additional
Redis/Celery service at this workload. API and worker share a modular codebase.
SQL row leases and owner advisory locks fence stale writes; provider calls occur
outside publication transactions.

**Proposed default:** semantic indexing is explicit per document, with a 128-chunk
limit and batches of 32. The current UI exposes this action after ingestion.
It is bounded synchronous work in an API thread, not an automatic background
embedding pipeline. Index publication rechecks source versions atomically.
Cosine search scans at most 10,000 owner chunks; there is no approximate index.
Hybrid fusion uses the first 20 results from each baseline with RRF constant 60.
These limits trade scale for a small, inspectable baseline.

**Discovered:** document replacement/deletion cascades embeddings; model identity
includes an installed digest. Old-model vectors are excluded. Semantic evaluation
rejects incomplete indexed coverage. Exact source extraction and structured
citations prevent fabricated passage references but do not establish semantic
correctness. Human evaluation is still required.

**Discovered (2026-10-25):** fixed UID containers cannot read a different Linux
owner's private credential files. Compose accepts an explicit non-root runtime
UID/GID, and the CI runner aligns these with its file owner. Local TLS uses direct
Uvicorn SSL and explicit test-CA trust, avoiding another proxy service for this
bounded check. Worker health combines a recent processing-loop heartbeat with
database readiness. Bootstrap DB privileges are not passed to API/worker.

**Proposed default:** reranking remains an offline experiment until its measured
quality/reliability/latency gate passes. The ranker sees only the question and
authorized candidates, never relevance labels. The separate judge is uncalibrated
and shares the generator model; its raw ratings and detected contradictions never
populate human correctness/faithfulness metrics. No extra provider was added.

The existing documents have distinct roles: AGENTS.md is the constitution, this
file the component/decision map, BUILD_STATE.md current acceptance status, and
dated engineering evidence the verification history. See BUILD_STATE.md for
remaining scope; a component's presence is not a completion claim.

