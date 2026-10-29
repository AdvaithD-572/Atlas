# Nonhuman acceptance work — 2026-10-25

Confirmed: finish the remaining semantic evaluation, reranking, CI and deployment
controls that do not require human review or interaction. Existing 100 cases are
development data already exposed to evaluation; they are not an untouched holdout.
Do not fill human ratings or create a public deployment/account/domain implicitly.

| Milestone | Dependencies | Exit criteria | Status |
|---|---|---|---|
| Separate reranker experiment | Frozen source binding, local qwen3 | Same authorized top-20 pool; strict permutation validation; 100 paired trials; stage latency/tokens/failures; explicit retention decision | VERIFIED experiment; retention gate FAILED, stage stays disabled |
| Semantic diagnostics | Fixed hybrid generator, same 100 cases | Actual answers; separately labeled model judge; expected-fact/claim/status diagnostics; all failures retained; no human ratings | VERIFIED measurement; model quality and judge reliability demonstrably weak |
| Runtime controls | Local PostgreSQL, existing containers | Non-admin runtime role; DDL denied and lifecycle passes; fresh worker progress and dependency health required | VERIFIED |
| Recovery and TLS | Disposable resources | Real custom-format backup/restore; integrity/isolation checks; verified TLS and negative trust/hostname checks; no global CA installation | VERIFIED locally; public certificate operations excluded |
| CI integration | Prior controls | Shared reproducible checks, image/worker smoke in workflow, actual local Linux checks | VERIFIED locally; hosted run remains separate |
| Hosted CI | Repository destination | Observed remote workflow run | BLOCKED: no Git remote; account/destination decision excluded from this request |

Proposed default before reranker scoring: retain only if Recall@5 improves by at
least .02, MRR does not regress, no additional failures occur, and p95 added latency
is at most 2000 ms. These are engineering tradeoffs, not predicted quality scores.
Even if these development gates pass, the experimental stage remains opt-in until
representative evaluation supports enabling it in application queries. Never tune
the prompt to case-specific failures. Model judge and generator share qwen3;
correlated errors and absence of human calibration must remain explicit.

Skill mapping: benchmark/eval-harness/agent-self-evaluation for separate metrics,
python-testing/security-review for strict bounded outputs and regressions,
postgres-patterns/database-migrations for runtime grants, deployment-patterns and
docker-patterns for health/TLS/recovery, living-docs-governance for evidence.
Read-only independent evaluation/deployment reviews informed these acceptance tests.

## Implementation and verification record

- `atlas/deployment.py`: explicit limited runtime login, private DSN files and
  rollback of only newly provisioned files/login on write failure. Tests deny
  table creation/alteration/truncation, role creation and migration metadata writes.
- `atlas/worker.py`: runtime DSN-file support and heartbeat tied to processing;
  health also checks live storage. Tests reject stale/future/invalid heartbeats.
- `compose.tls.yaml`, `scripts/package_checks.py`: actual HTTP/worker lifecycle,
  disposable restore, HTTPS lifecycle, unknown-CA/wrong-host rejection and HTTP
  restoration passed. Global trust was unchanged; retained data was preserved.
- `scripts/linux_permissions_smoke.py`: actual Linux volume files mode 0600,
  wrong UID 10001 denied, owner UID 1001 generated its certificate and passed
  HTTPS lifecycle against the restricted database login. Temporary containers and
  their private volume were removed after the check.
- Recovery drill measured a synthetic database backup at 1631.7 ms and restore at
  925.8 ms in its first successful run. All-row fingerprint, versions, citations,
  jobs, vectors and owner isolation matched; corrupt archive rejected. These are
  local fixture timings, not production RTO/RPO evidence.
- `.github/workflows/ci.yml` now calls shared backend checks and packaged recovery/
  TLS/permissions checks, with cleanup preserving volumes. No remote execution is
  claimed. `git remote -v` returned no destination.
- Native `scripts.verify --database-file .local/postgres.dsn`: 160 passed, 93%
  statement coverage, Ruff and strict mypy passed. UI: 26 tests, one real API/report
  contract, strict build, npm audit zero findings. Known Starlette/httpx warning.
- Audit initially failed on certifi 2026.10.18 (PYSEC-2026-4320). A targeted lock
  update selected 2026.10.23; `pip-audit` then reported no known vulnerabilities.
- First Linux full suite failed on the old bookworm SQLite secure-delete migration.
  The Python base was changed to a digest-pinned trixie image; no migration or
  secure-delete requirement was weakened. Final Linux checks passed all 160 tests,
  93% coverage, Ruff and mypy in a non-root container with read-only source. The
  shipped image reports SQLite 3.46.1 and certifi 2026.10.23. Linux frontend build
  also ran and passed all 26 component tests. Rebuilt package checks passed again.

Study runs 003 and 004 are preserved as development history. Run003 had a judge
array-count defect (66 attempted failures, 34 skipped after answer failures).
The v2 schema constrains exact counts without accepting malformed outputs. Run004
obtained model ratings but exposed missing failed-call timing and skipped-stage
accounting. Run005 records these explicitly, plus contradictions such as a judge
calling an expected fact supported despite the generator abstaining with no claims.
These are general contract/reporting repairs, not question-specific prompt tuning.

## Final development study: run 005

Command: `uv run --locked python -m scripts.draft_evaluation --quality-study
--output evaluation/atlas-docs-v1-run-005`. Process exited successfully; final
`quality-study/verification.json` confirms all 12 source versions remained unchanged.
100 cases per mode, 226 passages, frozen AI draft labels, no untouched holdout.

| Baseline | Recall@5 (80 answerable cases) | MRR@5 | Request failures /100 | p95 ms |
|---|---:|---:|---:|---:|
| Lexical | .46875 | .423125 | 0 | 63.303 |
| Vector | .60625 | .526875 | 0 | 389.032 |
| Hybrid | .63750 | .534167 | 0 | 435.999 |

Paired reranking: 100 attempted, **8 invalid rankings**, zero skipped. On the same
72 successfully reranked answerable cases, baseline and reranked Recall@5 were
both **.618056**; MRR changed .525926 to .539815. Across all 80 answerable cases,
counting failed reranks as zero, Recall@5 fell from .6375 to **.55625** and MRR to
.485833. Added reranker p95 was **4945.095 ms**, exceeding the declared 2000 ms
budget. There was no recall gain and added failures; **do not enable this reranker**.
Latency was measured on a shared host alongside verification/build work, not a
dedicated performance benchmark; reliability and recall independently fail the gate.

Answers: **35 failed requests, 62 abstentions, 3 answers**. Abstention decisions
matched draft answerability on 22/65 successful responses (.338462), or **22/100**
attempts with failures unsuccessful. Answer p95 including failed calls was
6248.127 ms. An answered status is not proof of a correct or useful answer.

Judge: **65 attempted, zero schema failures, 35 skipped** after answer failures.
It contradicted empty/abstained answers on **43 cases** by rating an unstated fact
supported or partial. Raw model fact coverage .918478 (46 rated cases), claim
relevance 1.0 (only three cases) and status appropriateness .707692 (65 cases)
therefore **must not be interpreted as validated quality**. Judge p95 was
4754.091 ms. Exact schema compliance did not produce a trustworthy evaluator.
Example contradiction IDs: atlas-docs-001, 007, 014, 015 and 018; full per-case
flags and original ratings remain in `quality-study/cases.jsonl`.

| Category | Cases | Rerank failures | Answer failures | Judge contradictions | Correct abstention decisions / all attempts |
|---|---:|---:|---:|---:|---:|
| Direct | 25 | 5 | 17 | 7 | 1/25 |
| Multi-document | 20 | 1 | 7 | 12 | 1/20 |
| Unanswerable | 20 | 0 | 1 | 0 | 19/20 |
| Conflicting/outdated | 15 | 0 | 4 | 10 | 1/15 |
| Difficult | 20 | 2 | 6 | 14 | 0/20 |

The critical weakness is answer usefulness/reliability, not a missing JSON schema.
Source-extraction checks reject malformed/unsupported output, but successful
provenance checks do not establish relevance. The model judge cannot validate its
own generator here. Human correctness and faithfulness fields remain null, human
review count remains zero, provider service fee is zero, and compute cost is unknown.
The automated experiment requirement is complete; semantic acceptance is not passed.

## Final scope and next milestone

PASSED: implementation tests, local operational controls, reproducible experiment
execution and evidence preservation. FAILED: reranker retention and semantic judge
reliability. SKIPPED: human calibration, external deployment and containerized
model inference. BLOCKED on external decisions: GitHub-hosted run (no Git remote),
public hostname/identity/certificate lifecycle and off-host retention policy.
No new approval is requested for work excluded by the user.

Next quality milestone: use a broader independently labeled corpus and a validated
evaluator before promoting generation/reranking. Human benchmark acceptance stays
separate. Do not tune these already-exposed cases and call them a holdout.

Self-review (agent assessment, not benchmark scoring): accuracy 4/5 (claims tied to
tests and raw artifacts; semantic scores remain unreliable), completeness 4/5
(all local listed experiments/controls executed; external acceptance excluded),
clarity 4/5 (denominators and failures explicit; detailed history is lengthy),
actionability 4/5 (shared commands and working native startup; installed models
required), conciseness 3/5 (long evidence history, concise README/final report used
as entry points). Overall 3.8/5. Highest-value improvement is independently valid
semantic evaluation. A user should agree that tests passing is not semantic success.
