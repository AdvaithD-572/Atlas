# PDF/HTML ingestion and hosted verification

## Decisions and milestones (2026-10-25)

Confirmed: finish PDF/HTML ingestion and hosted CI/public deployment; user chose
Vercel. Existing private documents and credentials are not deployment fixtures.
Discovered: GitHub repository `AdvaithD-572/Atlas` exists and is public; connected
repository inventory is empty although search reports push permission.
No Git remote is configured. Vercel has two unrelated projects, neither Atlas.

Proposed default: retain the modular API, worker, PostgreSQL and React application.
Use Python's HTMLParser for inert HTML extraction and pinned pypdf in a bounded
subprocess for text-layer PDF extraction. No OCR, remote document fetching,
scripts, or embedded file execution. Keep original-byte hashes, parser versions
and character spans in extracted text. Add nullable page/heading passage fields;
chunk within pages/sections so locations are unambiguous.

| Requirement | Acceptance / exit criterion | Status |
|---|---|---|
| Architecture | Shared typed parser result; parsing outside DB transactions | VERIFIED |
| Features | PDF/HTML upload, dedup, replacement, search, citations, deletion on both stores | VERIFIED |
| Security | Malformed/encrypted/empty/oversize rejected; bounded PDF work; no scripts/network; owner isolation | VERIFIED within documented containment limits |
| Testing | Parser, API, real PostgreSQL worker/migration, frontend and contract checks pass | VERIFIED |
| Documentation | Supported formats, extraction limits and migration procedure match implementation | VERIFIED |
| Evaluation | Synthetic parser fixtures labeled; no benchmark or human-review claim | VERIFIED for this format slice only |
| Observability | Safe parser error codes; request/job timing and failure events retained | VERIFIED |
| Hosted CI | Sanitized source published; actual workflow run observed | BLOCKED pending publication/access verification |
| Public deployment | Vercel plus storage/inference resources; HTTPS authenticated lifecycle smoke | BLOCKED pending backend/account configuration |

M1: parsers + location contracts + storage/worker integration + tests. Exit:
both formats retain locations and lifecycle/security tests pass.
M2 depends on M1: browser upload/source UI + serialized contract + full regression,
container/native checks; update evidence and running local app.
M3 depends on tested source and account access: GitHub CI, Vercel deployment,
public health/auth/upload/query/citation/delete smoke. Do not call a static UI or
mock integration a deployed full platform. Paid services require user approval.

Migration policy: additive nullable chunk columns; preserve old documents and IDs.
Drain/stop writers before numbered migration and update API/worker together.
Rollback uses a compatible build or backup; older builds reject newer schemas.
No production-sized migration claim.

## Baseline evidence

`uv run --locked pytest tests/test_lifecycle.py tests/test_integrity.py -q`:
30 passed, one existing Starlette TestClient deprecation warning.

## Continuation evidence, 2026-10-29

M1 is verified: typed PDF/HTML parsing, additive source-location migrations,
worker lease revalidation, owner isolation, deletion during parsing, and existing
document preservation. M2 frontend integration, dedicated browser file-upload
verification and updating the running local instance are verified below.

Passed: `uv run --locked python -m scripts.verify --database-file
.local/postgres.dsn` (181 tests, 91% coverage, Ruff and mypy); the same gate in a
non-root read-only Linux verification container (181 tests, 91%). The first Linux
attempt found a platform-specific mypy error on Windows creation flags; an explicit
platform branch fixed it. The final Linux gate passed. The isolated parser child
is exercised by real PDF tests but is not measured by parent-process coverage.

Passed: `npm test` (28), `npm run test:contract` (1 real API serialization check),
`npm run build`. Earlier pip-audit and npm audit found no known vulnerabilities.
Synthetic PDF fixtures are test data, not benchmark cases. No OCR, CSS visibility
calculation, human quality evaluation, or public integration is claimed.

Confirmed: user selected a new free database, a strict zero-cost budget, and
Supabase organization AdvaithD-572's Org. Created Atlas project
`aspjmwkokxlkmvbefeio` in ap-south-1 after a $0/month quote; SQL access works and
security advisors returned no notices on the empty application schema. Existing
SkillChain project was not modified. Application schema/runtime connection remains
pending; do not expose app tables through Supabase's public Data API.

Vercel team access returned 403; a consent link was supplied. Public deployment is
still blocked on that grant and verified free runtime configuration. Native Python
Functions are the proposed registry-free deployment; always-on worker and Ollama
inference are not established within free monthly quotas. No paid service was added.

Publication audit: 190 nonignored UTF-8 files, no private token/DSN matches or
credential patterns in the bounded scan. A separate read-only review agreed;
this is not proof that every possible secret pattern was detected. GitHub source
publication and observed hosted CI remain pending. Automatic approval review
rejected the attempted commit/push because the original repository request was
private and the actual repository is public. No commit or push occurred; the
user was asked to choose public publication or change repository visibility.

M2 additional checks passed: rebuilt runtime image; backed up the local database
before migration; compared existing document IDs/versions/hashes and passage
IDs/text before and after (identical); API/worker healthy. Real container PDF and
HTML queued ingestion, locations, citations, deletion and citation invalidation
passed. `python -m scripts.container_smoke` passed the packaged lifecycle.

`node scripts/formats_browser.cjs` passed actual file upload, source inspection,
keyboard focus, inert HTML, deletion and disconnect on a disposable SQLite server.
Both formats had no horizontal overflow at 375/768/1440 pixels, no HTTP failures
and no page errors. Mobile PDF screenshot inspected. No prior visual baseline,
full accessibility audit, or model quality claim. Private evidence files:
`.local/formats-browser/report.json`, screenshots, `.local/formats-linux.log`,
`.local/formats-container-smoke.json`.

Reproduce browser checks after `npm --prefix frontend run build`: run
`uv run --locked python -m scripts.formats_browser_server` in one terminal, then
`node scripts/formats_browser.cjs` in another with an installed Playwright package
and Edge (set NODE_PATH if using the bundled package). Stop the disposable server
afterward. Its token is a public synthetic fixture, never a production credential.

The checked-in browser server was launched and the journey rerun successfully.
After the portability fix, native Ruff/mypy and all 16 format tests passed again.
The local full app was restarted on port 8002 using existing restricted credentials;
its readiness endpoint returned `ready`, with the two existing Ollama models
available. This is dependency readiness, not a fresh semantic-quality evaluation.
No package TLS rerun was performed for this slice; the older TLS evidence remains
historical. Hosted CI/public HTTPS checks remain blocked, not passed or skipped
silently. No known failing local format check remains.
