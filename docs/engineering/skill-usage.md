# Skill discovery and usage

## Format verification and free hosting, 2026-10-29

Consulted the existing discovered-library mapping; no project-local skill was
added. Applied python-testing/python-patterns, contract-first, security-review,
database-migrations, React testing/frontend accessibility, browser-qa,
deployment-patterns, docker-patterns, github-ops and living-docs-governance to the
format slice and its checks. Instructions were read before use; execution is
manual, not automatic skill invocation. Windows/Linux gates: 181 tests each;
frontend: 28 tests plus one real serialized contract and production build.
Linux verification exposed and fixed a Windows-only typing reference. Parser
review prompted one-child concurrency, accurate normalization metadata, and
delete-during-parse/migration-preservation regressions.

Read `plugins/cache/openai-curated-remote/vercel/0.54.1/skills/create-a-backend/SKILL.md`
and `deployments-cicd/SKILL.md` under the user's `.codex` library for hosting discovery.
Read `plugins/cache/openai-curated-remote/supabase/1.0.0/skills/supabase/SKILL.md`:
checked organization/cost, created only the authorized free Atlas project, queried
its tables, and ran security advisors (no notices). Changelog markdown fetch was
unsupported by the web reader; no changelog review is claimed. Schema exposure,
TLS and runtime integration still require verification before deployment.

GitHub CLI is absent; Git Credential Manager is installed and lists the intended
account. Source audit plus connected GitHub metadata substitute for CLI inspection.
A separate read-only review checked publication and hosting risks. Vercel returned
a missing team grant, and its supported consent-link tool was used; no alternate
account or permission bypass was attempted. Details: formats-and-hosting.md.

Browser-qa was applied to a disposable server with a public test-only token:
actual PDF/HTML upload, keyboard source focus, inert scripts, deletion and logout
passed at 375/768/1440 widths. No visual baseline/full accessibility claim.
Container worker lifecycle also passed; migration preserved existing rows after
a private local backup. Approval review subsequently blocked public GitHub
publication because the initial repository request was private. No commit/push
occurred and a specific visibility decision was requested; no workaround used.

## Formats and hosting, 2026-10-25

Discovery re-run: 336 skill files in `.codex/skills`, 26 in `.agents/skills`,
2 bundled, 85 curated-remote, 6 primary-runtime plugin skill files. The repository
contains only root AGENTS.md and no project-local SKILL.md. Tool discovery found
GitHub and Vercel connectors; authenticated read-only resource checks performed.

Mapping consulted: python-patterns/python-testing for typed parsers and regression
tests; security-review for untrusted uploads, limits and safe errors;
database-migrations for nullable additive columns; contract-first for passage
locations and MIME changes; github-ops/deployment-patterns for hosted verification.
Read PDF skill for applicability: its layout/authoring workflow is not applicable
to an application parser or programmatic test fixtures; no PDF artifact authoring
workflow is claimed. Skills are followed manually. GitHub skill requires gh, which
is absent; use the connected GitHub tool as the available alternative, retaining
its untrusted-content and actual-CI-evidence requirements.

Baseline: 30 ingestion/lifecycle/integrity tests passed. Exact subsequent usage
and acceptance evidence is recorded in formats-and-hosting.md. pypdf official
extraction/security/configuration docs checked before adding version 6.21.2.

## Nonhuman acceptance work, 2026-10-25

Rechecked the existing 336 installed, 26 agent-library and 93 plugin-cache skill
locations and project inventory; no new library installation was needed. Consulted
the existing mapping before each implementation/check/documentation phase. The
following skills were read and followed manually; no automatic invocation is claimed.

| Task | Applicable skills | Actual application/evidence |
|---|---|---|
| Paired reranker and answer diagnostics | benchmark, eval-harness | Frozen within-run candidates, pinned models/prompts, predeclared retention gate, latency/failure denominators; run-003/004 failures preserved and run-005 final accounting |
| Model output and reporting tests | python-patterns, python-testing, security-review | Exact permutation/count validation, bounded local-only transport, no labels to ranker, no human scores; quality tests and failure accounting tests |
| Runtime identity and grants | postgres-patterns, database-migrations, security-review | Explicit admin provisioning, restricted CRUD role, denied DDL/TRUNCATE, file-write rollback and private Linux UID regression |
| Recovery/TLS/CI | deployment-patterns, docker-patterns | Actual dump/restore, negative TLS trust/hostname checks, worker progress health, pinned Linux image, non-root/read-only full tests and CI smoke commands |
| Evidence and critique | living-docs-governance, agent-self-evaluation | Corrected authoritative operations/status docs; preserved failed study artifacts, recorded uncalibrated judge contradictions and external-only blockers |

Bounded read-only evaluation and deployment delegates found unequal denominators,
skipped-stage accounting, missing failure timings, unchecked retrieval version,
Linux private-file ownership and partial credential provisioning issues. Parent
implemented and tested the corrections. The Windows-only smoke had masked POSIX
permissions; the new Linux-volume test proves both denied and allowed UIDs.

The broad Docker skill's Kubernetes/fleet suggestions do not override Atlas's
minimal local architecture. No cloud service, paid judge, global CA installation,
new skill package, unavailable Strix execution, or human-review substitute was used.
Official Docker merge and PostgreSQL restore documentation was consulted for the
runbook. Dependency audit found certifi PYSEC-2026-4320; only that transitive package
was upgraded, with a clean subsequent audit. Relevant commands and limits are in
BUILD_STATE.md and nonhuman-completion.md.

## Provider recovery and browser completion, 2026-10-25

Refreshed discovery: 336 skill files in `.codex/skills`, 26 in `.agents/skills`,
93 in plugin cache; no project-local skill or nested AGENTS.md. Newly listed
media/Hyperframes skills do not apply to this provider/CSS work and were not invoked.
Consulted the existing mapping and previously read instructions. `python-testing`,
`python-patterns` and `security-review` informed the bounded error-body read,
constant safe message, no retry/truncation behavior, failing-then-passing regression
and actual local-model recovery check. `browser-qa`, `frontend-a11y`, `accessibility`
and the existing computer-use fallback informed three-width browser checks and
manual screenshot inspection. `docker-patterns`/`deployment-patterns` covered the
rebuilt local image; `living-docs-governance` separates today's repair from the
immutable earlier benchmark evidence. No new dependency, external service, skill
installation, automatic invocation or model-judged quality rating was introduced.

Evidence: BUILD_STATE.md's dated 146-test pass; tests/test_provider.py;
scripts/embedding_limit_smoke.py; `.local/embedding-limit-smoke.json`;
`.local/evaluation-browser-qa/report.json` and screenshots. The earlier approval
usage-limit interruption is recorded; work resumed only after ordinary tool
approval succeeded. No approval mechanism was bypassed.

## Evaluation continuation, 2026-10-24

Read the complete AGENTS.md and consulted this mapping before continuing. A fresh
read-only scan found 336 skill files in `.codex/skills`, 22 in `.agents/skills`,
and 93 in `.codex/plugins/cache`; these are files including cached versions, not
distinct active capabilities. No nested AGENTS.md or project-local SKILL.md exists.
Session tool metadata and existing delegates were inspected; no new delegation or
external service was needed. Actual mechanisms were local Python/Node, PostgreSQL,
Ollama, Docker and bundled Playwright/Edge. No automatic skill invocation is claimed.

| Task | Applicable skills read and manually followed | Actual evidence |
|---|---|---|
| Answer observation and frozen drafts | eval-harness, benchmark, python-patterns, python-testing, security-review | Explicit pass criteria, null unknown ratings, pinned identities, exact-byte hashes and spans; 141 backend tests |
| AI critique | agent-self-evaluation and its report template | Five-axis evidence-backed critique in evaluation-review.md; no human review fabricated |
| Local report viewer | react-patterns, react-testing, frontend-patterns, frontend-a11y, accessibility, contract-first | 26 component tests, real Python report serialization, strict build, bounded memory-only file handling |
| Provider-backed comparison | benchmark, cost-aware-llm-pipeline, postgres-patterns | 100 queries per mode, same frozen snapshot, measured latency/failures, recorded chunk compatibility failure; no paid model/judge |
| Packaging/browser verification | docker-patterns, deployment-patterns, browser-qa, computer-use | Rebuilt image; browser fallback and container checks recorded with actual outcomes |
| Current status/protocol | living-docs-governance | Updated README, BUILD_STATE, evaluation protocol and evidence; frozen historical sources stay immutable |

Newly read self-evaluation instructions supplement the existing engineering checks.
Its template suggests asking whether to redo weak work; the user's explicit request
to proceed and ask only when blocked takes precedence. The critique is delivered
with specific limitations and independently executable checks. The benchmark skill's
load/concurrency targets are not claimed: this was a serial development comparison.
Claude-specific eval-harness commands are unavailable here; its test/evidence
workflow was followed manually. Existing application report paths take precedence
over generic skill suggestions to introduce a second benchmark artifact hierarchy.
Computer-use initialization remained unavailable; bundled Playwright/Edge is the
documented fallback. No external security scanner, human reviewer or model judge ran.

Detailed evidence: `evaluation-review.md`, `evaluation/atlas-docs-v1-run-002/`,
the actual commands in BUILD_STATE.md, and the regression test files. The 800/120
embedding failure and Windows hashing/encoding failures are recorded, not omitted.

Inspected 2026-10-19. Read-only discovery found 336 SKILL.md files under
`C:/Users/advai/.codex/skills`, 22 under `C:/Users/advai/.agents/skills`, and 92
under `C:/Users/advai/.codex/plugins/cache`. Counts include cached versions, not
450 distinct active skills. No Atlas-local skills exist. Session tools/catalog
were also inspected. One independent read-only skill audit delegate was used.

Short names below resolve to `C:/Users/advai/.codex/skills/<name>/SKILL.md`.

| Task | Skills read | Actual use / evidence |
|---|---|---|
| Discovery | codebase-onboarding, repo-scan | Git/files/runtime inventory. repo-scan is only an external installer pointer; ordinary rg/PowerShell used, no scan claimed. |
| Architecture/documentation | architecture-decision-records, living-docs-governance | Decision labels/alternatives and canonical status; maintain-phase governance not activated. |
| API | fastapi-patterns, api-design | App factory, explicit schemas, thin routes, versioned resources and bounded pagination. |
| Python | python-patterns, error-handling | Typed interfaces, context-managed connections, domain errors and safe HTTP errors. |
| Storage | database-migrations, content-hash-cache-pattern | Explicit versioned migration; owner/key/content/parser/chunk-config dedup, no shared content-only cache. |
| Tests | python-testing, tdd-workflow, verification-loop | Behavior-first lifecycle contracts, actual RED/GREEN, isolated DBs, adversarial inputs, lint/type/coverage checks. Results in BUILD_STATE.md. |
| Security | security-review | Hash-only credentials, owner predicates, payload bounds, no secret/document logging, invalidation tests. |
| Future PostgreSQL | postgres-patterns | Read; application and real database verification pending. |

Primary read FastAPI, Python patterns/testing and security-review fully. Delegate
read API, migrations, errors, content-hash, ADR, onboarding, PostgreSQL, testing,
TDD and verification instructions fully. Oversized initial reads were truncated;
subsequent smaller reads/delegate review completed them. A read alone does not
prove application; named tests and commands are the verification evidence.

Strix-specific API/application-security skills were inspected; Strix is absent.
Local adversarial pytest and manual review are available alternatives, not a
penetration-test result. Claude hooks, delivery-gate memory writes, paid skill
compliance audits, library-maintenance skills, unrelated languages, media and
external-app workflows are not applicable. No skill library was modified.
Frontend/accessibility/browser and contract-first skills will be read when the
UI milestone begins. Re-scan as scope changes.

Conflicts: AGENTS privacy rules override full-context logging/secret-printing
examples; explicit migrations override startup create-table examples. FastAPI
uses TestClient/httpx, not Flask-like app.test_client examples. User authorization
already covers project documentation; no extra ADR approval ceremony is needed.

M1 verification: 30 passing tests, lint/mypy, real loopback HTTP smoke; four
independent security-review findings repaired with regressions (see BUILD_STATE).
M2 used the same API/security/migration/testing skills for bounded SQL MATCH,
owner filtering, migration backfill, trigger consistency and invalidation.
Official SQLite FTS5 documentation was consulted for external-content triggers
and secure-delete; 45 backend tests passed. No benchmark skill is claimed yet.

## Continued usage, 2026-10-20

Full AGENTS.md and current mapping were rechecked. No nested project instruction
or local skill was found in the source inventory. Installed locations remain the
roots above; newly applicable work used the following mapped skills manually.

| Work | Skills actually read/applied | Verification evidence |
|---|---|---|
| React UI/contracts | react-patterns, frontend-patterns, frontend-a11y, accessibility, react-testing, contract-first, security-review | frontend-evidence.md: 20 tests, API contract, strict build, audit |
| Browser | browser-qa, computer-use plugin skill | browser-evidence.md: real API/model journey, three widths, axe/focus/screenshot checks |
| PostgreSQL/queue | postgres-patterns, database-migrations, docker-patterns, deployment-patterns, python-testing, tdd-workflow, verification-loop, api-design, error-handling, security-review | postgres-evidence.md: 18 real tests, scope and limits |
| Evaluation foundation | eval-harness, python-testing, benchmark | evaluation-evidence.md: 20 tests, metric/report/hash/human-review gates; no official benchmark run |
| Local provider | api-connector-builder, cost-aware-llm-pipeline, python-patterns, python-testing, security-review | provider-evidence.md: eight failures repaired, 22 provider + six question tests, actual Ollama smoke |
| Vector index/fusion | postgres-patterns, database-migrations, python-testing, security-review | Atomic owner/version-scoped publish, no provider I/O in transactions; vector-evidence.md and full 124-test pass |

Provider/benchmark skill instructions were read earlier in this implementation;
the resumed primary reread connector, testing, security, PostgreSQL and
content-hash guidance before repairs. The content-hash skill's own exclusion
applies to embedding reuse: output also depends on model/config, so no
content-only embedding cache was added. Two existing connectors cannot be
inspected because Atlas had none; the first provider follows the existing
Atlas errors, settings, app factory and test patterns.

Computer-use native APIs are unavailable, and the app browser failed to
initialize. Direct bundled Playwright was used as the browser-qa fallback.
playwright-cli instructions were inspected for fallback applicability, but its
CLI was not installed/invoked; no CLI use is claimed. No global package install
or personal browser profile was needed.

The benchmark-methodology skill concerns competitor branding and was read but
not applied to retrieval. Cost-aware pipeline guidance was applied only to
bounded retries/token accounting; paid routing/judges and caching were not added.
PostgreSQL skill's generic numeric-ID advice does not override existing stable
UUID resource contracts. All generated fixtures are clearly synthetic tests.

## Packaging and final evidence, 2026-10-20

- `docker-patterns` and `deployment-patterns` were read and applied to a pinned
  multi-stage build, non-root/read-only runtime, loopback ports, dependency
  readiness, separate migrations and actual HTTP/worker smoke. See
  deployment-evidence.md. Kubernetes/fleet suggestions are outside this local
  modular scope; no cloud publication or paid service was introduced.
- `browser-qa` was applied again against the actual container-served frontend:
  initial favicon 404 failed the console check; a rebuilt image passed the same
  script. Bundled Playwright/Edge remains the supported fallback described above.
- `living-docs-governance` was reread and is now applicable because early-slice
  docs had drifted from the integrated code. Existing AGENTS/map/BUILD_STATE/
  engineering-evidence files serve constitution/map/status/history roles. Stale
  README, architecture, operations, security and evaluation claims were corrected
  against code and observed checks; no parallel governance system was created.
- `python-testing`, `react-testing`, `contract-first` and security guidance
  informed the integrated regression checks, static/API boundary test and
  private-DSN test handling. Final results: 124 backend tests, 20 UI tests, one
  API serialization contract, strict types/build, lint and local browser smoke.

CI is implemented but no hosted execution is claimed. Human review skills cannot
substitute for a human reviewer; benchmark completeness stays blocked. Skill
instructions were followed manually; no unavailable automatic invocation or
external security scanner execution is claimed.

