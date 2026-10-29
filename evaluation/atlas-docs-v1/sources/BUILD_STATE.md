# Atlas build state

Updated 2026-10-20. Initial repository: AGENTS.md only. See
docs/engineering/implementation-plan.md for milestones and exit criteria.

| Requirement | Status | Acceptance / evidence |
|---|---|---|
| Architecture and skill discovery | VERIFIED | Decision plan, verified local inventory, skill mapping and component map |
| M1 document lifecycle | VERIFIED | 30 tests + real HTTP lifecycle smoke; SQLite development scope |
| Authentication/resource ownership | VERIFIED | Two-owner list/read/write/delete/chunk/citation isolation; local tokens only |
| Upload safety/source locations | VERIFIED | MIME, size, UTF-8, exact spans; chunk amplification bounded |
| Versioning/config metadata/dedup | VERIFIED | Stable doc ID, config-aware reindex, stale citations unavailable |
| M2 lexical retrieval | VERIFIED | 45 backend tests, FTS index/backfill/rollback/ranking/isolation verified |
| M3 React UI | VERIFIED | 20 component tests, contract/build, real browser/API/Ollama at 375/768/1440; browser-evidence.md |
| M4 PostgreSQL/pgvector and worker | VERIFIED | 18 real PostgreSQL tests; postgres-evidence.md; development scope |
| PDF/HTML | NOT_STARTED | Tested parsers, limits, source locations |
| M5 local provider | VERIFIED | Real Ollama embedding and cited answer + browser journey; provider-evidence.md |
| Vector/hybrid retrieval | VERIFIED | Real PG/API tests and real-model UI flow; vector-evidence.md; bounded local scope |
| Reranking experiment | NOT_STARTED | Same frozen human-reviewed dataset, measured benefit/cost/latency before retention |
| Grounding/conflicts/abstention | IN_PROGRESS | Provenance and source invalidation verified; semantic/conflict quality needs human benchmark |
| M6 human benchmark | BLOCKED | Authorized corpus and 100 genuinely human-reviewed cases |
| Evaluation harness | IMPLEMENTED | Pinned lexical/vector/hybrid HTTP runners and reports tested; automatic answer grading pending |
| Evaluation results UI | NOT_STARTED | Real report display with validation, empty/error states and accessible metrics |
| M7 local container package | VERIFIED | Image build, static CSP/browser, API+worker lifecycle; deployment-evidence.md |
| CI/production deployment | IN_PROGRESS | Pinned CI workflow exists; hosted execution, TLS/roles/backup restore unverified |
| Observability | IN_PROGRESS | Redacted request/job IDs, timings, failures; response model/digest/token metadata; aggregated monitoring pending |
| Performance/cost | IN_PROGRESS | 100 serial synthetic lexical requests measured; representative concurrent load and compute cost unmeasured |
| Active-data retention/deletion | VERIFIED | PG/SQLite chunks, embeddings and job artifacts invalidated; no shared caches |
| Backup/WAL/forensic retention | NOT_STARTED | Deployment-specific storage policy and restoration evidence |

Docker Desktop runs successfully. Ollama has all-minilm:latest and qwen3:1.7b.
Real synthetic embedding/generation smoke passed; no quality benchmark is implied.
uv selected installed Python 3.14.7; system Python reports 3.14.8. Node 24.21.0,
npm 11.19.0, uv 0.12.19. Sandbox command startup fails; scoped escalation works.
The approval usage limit interrupted an earlier documentation write; inspection
confirmed it did not persist. Dependency sync produced uv.lock and pytest.
The one-time continue automation fired again despite COUNT=1; it was explicitly
paused on 20 October, confirmed by the app tool.

## Verification

Discovery passed. No baseline code/tests existed. Tests were written before
implementation. Actual check outcomes will be appended after execution.
No public deployment, official benchmark or portfolio-ready status is claimed.

### M1 evidence, 2026-10-19

- RED: `uv run --locked pytest tests/test_lifecycle.py -q` failed because atlas
  implementation did not yet exist. Dependencies had installed successfully.
- GREEN: `uv run --locked pytest -q --tb=short --cov=atlas --cov-report=term-missing`
  passed 30 tests, 96% statement coverage; ingestion/security/services 100%.
- `uv run --locked ruff check atlas tests`: passed after formatting fixes.
- `uv run --locked mypy`: passed, 11 source files.
- `uv run --locked python -m atlas migrate` and `... provision --owner local`:
  passed. Private credential saved in ignored .local without echoing the token.
- `uv run --locked python scripts/smoke.py`: passed actual loopback HTTP readiness,
  authentication, upload, citation and deletion; subprocess stopped afterwards.
- Failed then fixed: oversized pytest parametrization IDs exceeded Windows temp
  filename constraints; short IDs retained the same payload test. One test-edit
  placement error was repaired. Lint formatting failures repaired.
- Independent review: fixed chunk amplification, missing default INFO telemetry,
  concurrent credential registry lost updates, startup validation secret echo;
  regression tests added. Provisioning failure rollback also tested.
- Dependency audit first invocation failed on unsupported flag combination;
  corrected `uv run --locked pip-audit --progress-spinner off` running.
- Known warning: installed Starlette TestClient deprecates httpx in favor of
  httpx2; tests currently pass. No test warning suppression added.
- Skipped: no original suite existed. Blocked: genuine human benchmark review.

### M2 evidence, 2026-10-19

- RED: 11 retrieval tests failed with missing /v1/search (404), before implementation.
- GREEN: `uv run --locked pytest -q --tb=short --cov=atlas --cov-report=term-missing`:
  45 passed, 96% statement coverage; retrieval/security/ingestion/services 100%.
- `uv run --locked ruff check atlas tests scripts` and `uv run --locked mypy`: passed.
- Explicit migrations and existing lifecycle HTTP smoke passed after schema upgrade.
- `uv run --locked pip-audit --progress-spinner off`: no known vulnerabilities found.
- Verified old-schema backfill, FTS integrity, index deletion/replacement/rollback,
  owner-independent ranking, malicious query syntax, bounded payload/candidates.
- No semantic quality benchmark or generation result implied. FTS5 match/token
  normalization differs from Python ranking tokenization for some Unicode input.

### Resumption evidence, 2026-10-20

- Re-read complete AGENTS.md, inspected current source/manifests/evidence and
  preserved the working tree. The mandatory skill instructions are already present.
- Provider security RED: 8 independently written adversarial tests failed.
  GREEN after fixes: 22 provider tests; six question/API tests passed. Strict
  mypy passed on all 18 current modules. Broader checks are being rerun after
  vector integration; do not treat earlier counts as the final suite.
- Real provider smoke first timed out, then incorrectly abstained on synthetic
  answerable text. Versioned explicit-format examples fixed this smoke.
  Actual successful report: 384 dimensions, 122.57 ms embedding, 569.83 ms
  generation, 349 input/42 output tokens. One warm synthetic run only.
- Frontend: 20 tests, real serialized API contract check and production build
  passed. Actual Edge/API/Ollama journey passed, zero page errors/HTTP failures,
  zero axe violations or horizontal overflow at 375/768/1440 pixels.
- PostgreSQL/worker: 18 real tests and scoped strict types/lint passed, reported
  97% combined module coverage. Details and operational limits in postgres-evidence.md.
- Full-suite collection temporarily failed while the vector delegate's tests
  existed before implementation. Delegate hit account usage limit; parent took
  over and implemented the missing module. First vector/PG run: 25 passed,
  one schema-drift test failure from the new FK; isolated corruption test
  updated to drop its dependent test-only constraint. The final full run below
  passed; the new FK remains enforced in the real schema.
- The app-browser tool could not initialize because the Windows sandbox helper
  failed. Bundled Playwright with headless Edge was used for actual local QA.
  No security controls or sandbox settings were disabled.

### Integrated verification and local package, 2026-10-20

- **Passed:** `uv run --locked pytest -q --tb=no --cov=atlas --cov-report=term`
  with the private PostgreSQL test DSN: **124 passed, 93% statement coverage**.
  Real database/vector tests used isolated schemas, not simulated storage.
- **Passed:** Ruff check and format across atlas/tests/scripts (35 files),
  strict mypy (18 modules), Python dependency audit with no known vulnerabilities
  at execution time. One known Starlette TestClient/httpx warning remains.
- **Passed:** frontend `npm test` (20), API serialization contract (one),
  strict `npm run build`; full Edge/native API/PostgreSQL/Ollama flow at
  375/768/1440 with no axe violations, overflow, page errors or HTTP failures.
- **Passed:** final Docker image build and Compose API/worker recreation;
  `node scripts/container_browser.cjs` rendered React under the real CSP without
  console errors. `uv run --locked python -m scripts.container_smoke` passed
  actual queued ingestion, continuous-worker completion, retrieval, citation
  and document/job cleanup.
- **Failed then fixed:** initial packaged browser check found a missing favicon
  (404). Added local SVG and rebuilt; the same check now passes.
- **Measured:** 100 serial warm synthetic lexical queries, zero failures,
  p50 10.453 ms / p95 11.880 ms / p99 13.346 ms. One-CPU API container,
  concurrency one, no model calls, compute cost unknown. Not a scale claim.
- **Skipped/unverified:** hosted CI, external deployment, full model path inside
  containers, production identity/TLS/roles, backup restoration, representative
  load and semantic quality. Model path is verified on the native API.
- **Blocked:** official benchmark needs an authorized frozen corpus and 100
  actual human reviews. The user's “okay” acknowledges the request but does not
  identify a corpus/reviewer or attest that any case has been reviewed.

Next milestone: complete M6 review preparation, answer-evaluation integration
and real results UI; then freeze the human-reviewed corpus for separate retrieval
and reranking experiments. M7 release acceptance remains open until M6 and the
outstanding operational/security requirements are verified.
