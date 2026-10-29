# Atlas build state

Updated 2026-10-29. Initial repository: AGENTS.md only. See
docs/engineering/implementation-plan.md for milestones and exit criteria.

| Requirement | Status | Acceptance / evidence |
|---|---|---|
| Architecture and skill discovery | VERIFIED | Decision plan, verified local inventory, skill mapping and component map |
| M1 document lifecycle | VERIFIED | 30 tests + real HTTP lifecycle smoke; SQLite development scope |
| Authentication/resource ownership | VERIFIED | Two-owner list/read/write/delete/chunk/citation isolation; local tokens only |
| Upload safety/source locations | VERIFIED | MIME, size, UTF-8, exact spans; chunk amplification bounded |
| Versioning/config metadata/dedup | VERIFIED | Stable doc ID, config-aware reindex, stale citations unavailable |
| M2 lexical retrieval | VERIFIED | 45 backend tests, FTS index/backfill/rollback/ranking/isolation verified |
| M3 React UI | VERIFIED | 26 component tests, contract/build, real browser/API/Ollama at 375/768/1440; browser-evidence.md |
| M4 PostgreSQL/pgvector and worker | VERIFIED | 18 real PostgreSQL tests; postgres-evidence.md; development scope |
| PDF/HTML | VERIFIED | 181-test Windows/Linux gates, 28 UI tests and contract/build; real container worker and browser file/citation/delete journeys at three widths; formats-and-hosting.md |
| M5 local provider | VERIFIED | Real Ollama embedding and cited answer + browser journey; provider-evidence.md |
| Vector/hybrid retrieval | VERIFIED | Real PG/API tests and real-model UI flow; vector-evidence.md; bounded local scope |
| Reranking experiment | VERIFIED | Run005: 100 trials, 8 failures, no paired Recall gain, 4945 ms p95; retention gate failed, application stage disabled |
| Grounding/conflicts/abstention | IN_PROGRESS | Provenance and source invalidation verified; semantic/conflict quality needs human benchmark |
| M6 human benchmark | BLOCKED | Original human-review gate remains unmet; user authorized AI critique for development |
| M6 AI-reviewed development set | VERIFIED | 100 frozen AI drafts; 300 real baseline queries, zero request failures; evaluation-review.md documents weak labels/truncation |
| Evaluation harness | VERIFIED | Frozen baselines plus separate local model diagnostics; 35 answer failures and 43 judge contradictions recorded; human ratings null |
| Evaluation results UI | VERIFIED | Local validated reports, unknown metrics, clear/logout isolation, 26 UI tests and serialization contract |
| M7 local container package | VERIFIED | Image build, static CSP/browser, API+worker lifecycle; deployment-evidence.md |
| Local deployment controls | VERIFIED | Restricted runtime role, worker health, actual restore, TLS and Linux private-file lifecycle checks |
| CI/production deployment | IN_PROGRESS | Shared workflow gates verified locally on Windows/Linux; hosted run and public deployment require external destination/operations |
| Observability | IN_PROGRESS | Redacted request/job IDs, timings, failures; response model/digest/token metadata; aggregated monitoring pending |
| Performance/cost | IN_PROGRESS | 100 serial synthetic lexical requests measured; representative concurrent load and compute cost unmeasured |
| Active-data retention/deletion | VERIFIED | PG/SQLite chunks, embeddings and job artifacts invalidated; no shared caches |
| Backup restoration | VERIFIED | Real disposable pg_dump/restore, all-row integrity, vectors/jobs/citations and owner isolation |
| Backup/WAL/forensic retention | BLOCKED | Deployment-specific off-host storage, retention and RPO require owner/operator choices |

Docker Desktop runs successfully. Ollama has all-minilm:latest and qwen3:1.7b.
Real synthetic embedding/generation smoke passed; no quality benchmark is implied.
uv selected installed Python 3.14.7; system Python reports 3.14.8. Node 24.21.0,
npm 11.19.0, uv 0.12.19. Sandbox command startup fails; scoped escalation works.
The approval usage limit interrupted an earlier documentation write; inspection
confirmed it did not persist. Dependency sync produced uv.lock and pytest.
The one-time continue automation fired again despite COUNT=1; it was explicitly
paused on 20 October, confirmed by the app tool.

## Verification

### Operational controls and cross-platform gates, 2026-10-25

- Implemented restricted runtime DB provisioning with private files and failure
  rollback, worker DSN-file support and actual-loop heartbeat health, explicit TLS
  Compose profile, disposable restore drill, shared CI/package checks and Linux
  private-file ownership smoke. See nonhuman-completion.md and operations.md.
- PASSED `uv run --locked python -m scripts.verify --database-file
  .local/postgres.dsn`: **160 tests, 93% coverage**, Ruff check/format (53 files),
  strict mypy (20 modules). The non-root Linux `verification` image passed the
  same gates against real isolated PostgreSQL schemas, with read-only source.
- PASSED frontend `npm test` (26), `npm run test:contract` (one), `npm run build`
  and `npm audit` (zero findings). The Linux image build also ran all 26 UI tests.
- FAILED THEN FIXED: the old worker fixture did not populate the new Settings DSN;
  adapted that fixture and added actual DSN-file processing coverage. Linux file
  ownership would have blocked CI; matching non-root UID is now explicitly tested.
  First Linux suite failed on unsupported secure-delete in bookworm SQLite; the
  digest-pinned trixie image supplies SQLite 3.46.1 without weakening the migration.
- FAILED THEN FIXED: `pip-audit` flagged certifi 2026.10.18. Targeted
  `uv lock --upgrade-package certifi` selected 2026.10.23; `uv sync --locked` and
  the subsequent audit passed with no known vulnerabilities. Final image rebuilt.
- PASSED final `scripts.package_checks`: restricted API/worker lifecycle, real
  pg_dump/restore integrity/isolation, verified HTTPS lifecycle, negative trust
  and hostname checks, restoration of HTTP. PASSED `scripts.linux_permissions_smoke`
  after the final rebuild; wrong UID denied, matching non-root UID succeeds.
- PASSED `node scripts/container_browser.cjs`: packaged React/CSP, no page errors.
  Private DSN/key/credential paths verified ignored by Git. No secrets printed.
- BLOCKED/EXCLUDED: hosted workflow execution (no Git remote), public deployment
  destination/identity/certificate renewal and off-host retention choices. No paid
  service or public publication introduced. Human benchmark review remains excluded.
- SKIPPED: real model inference inside containers (native local Ollama is the
  supported model path), external public deployment and human calibration. One
  Starlette/httpx test-client deprecation warning remains. No critical test failure
  remains in this verified operational scope.

### Automated quality experiments and startup, 2026-10-25

- PASSED execution of `scripts.draft_evaluation --quality-study --output
  evaluation/atlas-docs-v1-run-005`: three 100-query baselines and 100 paired study
  cases; all 12 source versions checked after completion. Frozen AI labels only.
- FAILED retention: 8 invalid rankings, zero paired Recall@5 gain, p95 4945 ms.
  Reranking remains disabled. All-case Recall@5 with failed reranks zero: .55625
  versus baseline .6375. The shared-host timings are not a production SLA.
- Semantic weakness: 35 answer errors, 62 abstentions and three answered responses;
  22/100 correct abstention decisions versus draft labels. The 65 structurally
  valid model judgments include 43 contradictions on empty/abstained answers.
  Raw model ratings are not trustworthy correctness evidence. Human ratings null.
- Preserved run003/004 history. Repaired exact judge count constraints, paired and
  failure-zero denominators, attempted/failed/skipped counts, failed-call timings,
  retrieval-version validation, source verification marker and candidate-failure
  retention gate. Focused evaluation regressions and final full 160-test Windows
  and Linux gates passed. Details: docs/engineering/nonhuman-completion.md.
- PASSED full native startup on loopback **8002**, serving frontend/dist with
  restricted runtime DSN and real Ollama. Authenticated synthetic upload, actual
  embedding, hybrid answer, authorized citations and cleanup all passed. Capability
  response confirms PostgreSQL, lexical/vector/hybrid and generation enabled.
  Container API remains on 8080 (models disabled); its worker is healthy.

### Provider recovery and report readability, 2026-10-25

- Rechecked repository state and skill resources after automatic approval review
  previously hit a usage limit. The interrupted CSS edit had not been applied;
  tool access recovered on resumption. A newly present empty root package-lock.json
  was inspected and preserved; frontend/package-lock.json remains the UI lockfile.
- Fixed the 375-pixel report table so “Not measured” wraps between words. The
  actual 100-case hybrid report passed Edge checks at 375/768/1440, with no overflow,
  axe violations or page errors, and no upload/persistence. Screenshot inspected.
- Implemented bounded classification of the known Ollama embedding context error:
  HTTP 422 with chunk/query guidance; other errors remain generic and private.
  No provider truncation, authorization relaxation or default chunk change.
- RED: context-limit regression initially returned generic provider_rejected.
  GREEN: all five context/unknown/malformed/oversized error cases pass; permanent
  failures are not retried. One formatting failure was fixed without suppressions.
- PASSED: `uv run --locked python -m scripts.embedding_limit_smoke`: real Ollama
  and PostgreSQL via in-process API transport. 800/120 input returns 422, zero
  indexed and 14 unindexed chunks; 400/80 returns 200, all 29 chunks indexed.
  Lexical search remains available in both profiles. Source is frozen project
  documentation; no answer-quality claim. `.local/embedding-limit-smoke.json`.
- PASSED with private ATLAS_TEST_POSTGRES_DSN set:
  `uv run --locked pytest -q --tb=no --cov=atlas --cov-report=term`:
  146 tests, 93% coverage, one existing Starlette/httpx warning, no final skips.
- PASSED: `uv run --locked ruff check atlas tests scripts`,
  `uv run --locked ruff format --check atlas tests scripts` (42 files),
  `uv run --locked mypy` (18 modules). The preliminary narrow run skipped nine
  PostgreSQL tests because that command lacked the DSN; the complete rerun included them.
- Relevant files: atlas/providers.py, tests/test_provider.py,
  scripts/embedding_limit_smoke.py, frontend/src/styles.css, operational/skill docs.
- PASSED final package: `docker compose --env-file .local/postgres.env -f
  compose.yaml -f compose.app.yaml build api` and `... up -d --wait api worker`.
  `node scripts/evaluation_browser.cjs --container --report
  evaluation/atlas-docs-v1-run-002/hybrid/results.json` passed all three widths;
  `node scripts/container_browser.cjs` passed React/CSP with no page errors;
  `uv run --locked python -m scripts.container_smoke` passed real queued worker,
  search, citation and deletion. Browser scripts used the documented bundled
  Playwright NODE_PATH. Models remain off in the container profile; the real-model
  repair check above used the native in-process API and local Ollama.
- Remaining: recognize only the verified provider error shape; unknown errors
  remain generic. Character counts do not guarantee every model's token budget.
  Official human review, representative semantic evaluation, reranking and public
  deployment controls remain unfinished. Next: improve evaluation validity and
  source relevance labels before claiming benchmark completion.

### Evaluation milestones, 2026-10-24

- Implemented local report viewer and pinned answer-observation runner, frozen AI
  drafts with source snapshots, exact-span binding, and an actual three-mode local
  retrieval comparison. Key files: frontend/src/EvaluationReport.tsx,
  atlas/evaluation.py, scripts/review_drafts.py, scripts/draft_evaluation.py,
  tests/test_answer_evaluation.py, tests/test_review_drafts.py,
  tests/test_draft_binding.py and docs/engineering/evaluation-review.md.
- PASSED: `uv run --locked pytest -q --tb=no --cov=atlas --cov-report=term`
  with private ATLAS_TEST_POSTGRES_DSN set: 141 tests, 93% statement coverage.
- PASSED: `uv run --locked ruff check atlas tests scripts`,
  `uv run --locked ruff format --check atlas tests scripts` (41 files),
  `uv run --locked mypy` (18 modules).
- PASSED in frontend: `npm test` (26 tests), `npm run test:contract` (one actual
  Python API/report serialization test), `npm run build` (strict TypeScript/Vite).
- PASSED: `uv run --locked python -m scripts.answer_evaluation_smoke`: actual
  local qwen3 cited answer and empty-evidence abstention; two synthetic cases only.
- PASSED: `uv run --locked python -m scripts.review_drafts --output
  evaluation/atlas-docs-v1`: 100 AI drafts, 0 human reviews. Frozen-copy regression
  checks compare exact output bytes and source hashes.
- PASSED: `uv run --locked python -m scripts.draft_evaluation --output
  evaluation/atlas-docs-v1-run-002`: 100 cases per mode, 12 docs, 226 passages,
  zero request failures. Recall@5: lexical .46875, vector .60625, hybrid .63750
  on 80 answerable cases. Lexical/hybrid each flagged 32 truncated queries.
- FAILED then fixed: exact-byte JSONL hash differed on Windows; test decoding
  used platform encoding; source-index response used the wrong field name before
  execution. Regression checks now pass. First real 800/120 indexing attempt
  exceeded local model context; no scores produced. Explicit 400/80 run passed.
- Remaining: official human benchmark, exhaustive relevance labels, holdout,
  semantic correctness/faithfulness and nontrivial abstention evaluation, reranking,
  representative load/cost and public deployment/hosted CI. Known Starlette/httpx
  deprecation warning remains; no checks were suppressed. No automated semantic
  judge or human review was run. No paid services or new dependencies were added.
- Next: refresh packaged browser/lifecycle evidence, then improve evaluation
  validity before claiming portfolio-level benchmark completion.

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
