# Atlas implementation plan

Inspection: 2026-10-19 (Asia/Kolkata). The initial repository contains only
AGENTS.md and Git metadata. No code, manifests, tests, or nested instructions exist.
Python 3.14.8, Node 24.21.0, npm 11.19.0, uv 0.12.19, Docker CLI 29.8.2,
Compose 5.6.0 and Ollama are installed. Docker engine was unavailable and Ollama's
model list was empty. Sandboxed command startup fails; scoped escalated commands
are required. No Atlas-specific memory entry was found.

## Milestones and dependencies

1. **M1: local authenticated document lifecycle.** FastAPI/Pydantic, explicit
   SQLite migrations, operator-provisioned bearer credentials, typed API, bounded
   UTF-8 text/Markdown upload, exact source spans, transactional replacement,
   deduplication, pagination, deletion and health/readiness. Exit: lifecycle,
   isolation, rollback, invalid input and restart tests pass; lint/type checks pass.
   No LLM or cloud account required. SQLite is a development backend, not proof
   of PostgreSQL compatibility. Synchronous bounded ingestion is explicit.
2. **M2: lexical evidence path.** Depends on M1. Indexed lexical search, owner
   filtering, version-bound citations and no-evidence state. Exit: ranking,
   source-resolution, deletion/replacement invalidation and injection-isolation
   tests pass. Retrieved excerpts must not be labelled generated answers.
3. **M3: usable local UI.** Depends on M2. React/strict TypeScript document,
   search and source-inspection views. Exit: type/build, real API flow and browser
   checks at desktop/narrow sizes, accessible loading/empty/error/retry states.
4. **M4: production database and background ingestion.** Depends on M1; needs
   working PostgreSQL/pgvector runtime. Versioned migrations, durable bounded jobs,
   retries/leases/recovery, staging and atomic publish. Exit: real DB integration,
   concurrent update/delete/retry isolation and Compose clean-start tests.
5. **M5: local provider and retrieval experiments.** Depends on M4, verified
   local embedding/generation models and sufficient hardware. Vector baseline,
   then tested RRF hybrid; structured generation, citation validation, abstention,
   conflicts and provider failures. Exit: actual provider E2E and adversarial tests.
6. **M6: reproducible evaluation.** Depends on M5 and authorized source corpus.
   Frozen 100+ human-reviewed cases (25/20/20/15/20 categories), metric unit tests,
   separate retrieval/answer/citation/faithfulness/abstention/latency/failure/cost
   reporting. Reranking is a separate measured experiment. Exit: human sign-off
   and reproducible JSON/CSV/report. Agent-written tests are not benchmark cases.
7. **M7: release verification.** Depends on prior milestones. CI, deployment
   artifacts, retention, rate/concurrency limits, telemetry and operational smoke
   tests. Exit: clean install/start, workload evidence, security regression suite,
   UI checks and requirements-to-test audit. No cloud publication is implied.

## Evaluation continuation, 2026-10-24

Confirmed user decision: perform AI review and critique. This authorizes development
review, not invented human attribution. Proposed default corpus: Atlas's own docs.
The original official human-review gate remains distinct from this work.

1. Report viewer and answer observations: depends on existing API/report contracts.
   Exit met: 26 UI tests, actual serialization, strict build, pinned provider metadata,
   real two-case answer CLI smoke; semantic ratings remain null.
2. Frozen AI drafts and critique: depends on documentation snapshots. Exit met: 100
   source-bound drafts in planned proportions, exact-byte hashes, no human labels,
   specific critique, overwrite protection and regression checks.
3. Real development comparison: depends on local PostgreSQL/Ollama and frozen drafts.
   Exit met: real passage binding, three modes on identical inputs, 300 attempted
   queries with zero request failures, JSON/CSV/Markdown reports and disclosed limits.
   The first index attempt failed; 400/80 chunks replaced incompatible 800/120 before
   scoring, with no silent truncation. See evaluation-review.md.
4. Refresh packaged integration evidence: depends on passing suites and rebuilt UI/API.
   Exit met 2026-10-25: rebuilt container startup, lifecycle/worker and actual report
   browser checks at three widths. Follow-up context-limit diagnostics passed 146
   backend tests and real-model rejection/recovery verification; see BUILD_STATE.md.
5. Improve evaluation validity: replace weak conflict/conjunction cases, broaden the
   corpus and relevance labels, establish a fact-grouped holdout, assess real answer
   quality and then run a separate reranking comparison. Original human acceptance
   remains pending; no quality threshold or reviewer is invented.

2026-10-25 scope decision: the user requested completion of the listed work that
does not need human review/interaction. [Nonhuman completion](nonhuman-completion.md)
tracks the separate automated quality/reranker experiments and deployment controls.
Runtime grants, worker health, TLS, restore and local CI-equivalent checks now have
actual evidence. Dataset expansion/holdout and public account/identity decisions
remain outside this continuation; existing frozen labels were preserved.

## Decisions and boundaries

- Confirmed: work in this repository, no paid services, no invented benchmark or
  deployment claims, maintain acceptance evidence and skill records.
- Proposed default: modular application, standard-library SQLite for first local
  slice; PostgreSQL/pgvector remains the target. Avoid an ORM/queue dependency
  until the persistent worker and production database slice justify it.
- Proposed default: pre-provisioned high-entropy bearer tokens; only token hashes
  stored. No public registration, default password, or browser token persistence.
- Proposed default: small text/Markdown inputs first. PDF/HTML rejected until
  parser tests and resource controls are implemented.
- Unknown/blocker: corpus permission and actual human benchmark review. Model
  suitability and Docker engine readiness require direct verification.

Security priorities: prevent cross-owner retrieval/citations/deletion; bound
payload and chunk work; never execute uploads; parameterize SQL; do not log
documents/queries/secrets; invalidate old citation IDs after replacement/deletion.

## Evaluation viewer increment, 2026-10-20

Depends on the existing `atlas.evaluation.run_experiment` JSON output and the
authenticated React workspace. Proposed default: explicitly selected local
`results.json`, read only in browser memory, with no server upload or stored
report library. This avoids adding report ownership/storage before needed.

Exit criteria: validate the v1 exported shape and internal count consistency;
show retrieval and answer metrics separately with measured-case denominators;
preserve missing ratings/cost as unknown; label declared official status without
attesting human review; handle loading/empty/error/clear states; reject oversized
files; drop pending reads on clear/logout; verify real Python serialization,
component accessibility, strict build and browser layouts. Report contents are
untrusted text. Viewing a report does not verify its provenance or benchmark truth.

Answer-observation increment depends on the same frozen dataset and the existing
`/v1/answers` contract. Exit: explicit opt-in and pinned generation model/digest/
prompt; retrieval metrics remain separate; record cited passage IDs, explicit
abstention and available token usage; leave semantic ratings and unmeasured
compute cost null; provider/config failures stay failures; generated content
is excluded from ordinary reports; verify actual CLI/API and local-model smoke.
