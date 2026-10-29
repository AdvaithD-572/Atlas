# Frontend implementation and evidence

Recorded 2026-10-19. Scope: M3 local document/retrieval UI in `frontend/`.

## Discovery and decisions

- **Discovered:** the repository had no frontend manifest or UI when this work
  began. The root AGENTS.md was read completely; no nested AGENTS.md was found.
  Existing `docs/engineering/skill-usage.md` library scan and mappings were read.
- **Discovered:** Node 24.21.0 and npm 11.19.0 were available. Exact dependency
  versions are in `frontend/package.json` and its generated npm lockfile.
- **Confirmed:** React with strict TypeScript; real API data; no fabricated
  answers, metrics or production data; server-side authorization is authoritative.
- **Proposed default:** Vite, native fetch, Zod runtime parsing, component-local
  state, and Vitest/Testing Library. No router, global store, caching library,
  UI framework, external font, analytics, paid API or hosting service.
- **Proposed default:** all content is displayed as escaped text. Markdown is
  accepted by the ingestion API but never rendered as executable HTML in the UI.

## Skill mapping and actual usage

All locations below are under `C:/Users/advai/.codex/skills/<name>/SKILL.md`.
These were read before applying the corresponding work. An oversized combined
read truncated; smaller reads completed the applicable instruction content.

| Skill | Application | Evidence |
|---|---|---|
| react-patterns | Local state, pure render, semantic composition, session lifetime cleanup | App.tsx; previous-owner late-response test |
| frontend-patterns | Controlled forms, bounded lists, error/retry state, responsive columns | App.tsx/styles.css; lifecycle/paging tests |
| frontend-a11y | Connected labels, native controls, live regions, source focus/restore | App.tsx; accessible role-based tests |
| accessibility | Focus outlines, 44px controls, reflow rules and no motion | styles.css; axe structural checks; real viewport verification pending |
| react-testing | Vitest, userEvent, behavior assertions, explicit mocked HTTP fixtures, axe | App.test.tsx/api.test.ts |
| contract-first | Provider-owned Pydantic contract, runtime validation, actual API response interoperability | api.ts; provider.contract.ts and scripts/provider_contract.py |
| security-review | Memory-only token, no cookies/cache, safe error strings, bounded uploads, escaped text | api.ts; authentication-header, logout, race, markup and denial tests |

Skills were followed manually; no skill invocation mechanism was required.
The existing library scan found no project-local skills. Browser automation and
its skills are owned by the parent implementation task and are not claimed here.

Conflicts/choices: native fetch is limited to a small uncached local application;
requests serialize while an operation runs, disconnect aborts requests and mounts
a fresh workspace for a new token. This explicitly addresses the race/cache
concerns in the React skill without adding a server-state dependency. The security
skill's cookie example is not adopted because the existing local API uses bearer
tokens: no token enters localStorage/sessionStorage, URLs or logs, and cookies
are omitted. Provider schema is authoritative; the consumer validators are
handwritten and checked against real provider output instead of introducing a
schema generator for six small response shapes. This is not a claim of exhaustive
OpenAPI compatibility. Component HTTP mocks use strict unexpected-request failure
instead of an additional MSW dependency. No generated test fixture is benchmark data.

## Implemented acceptance checks

- Memory-only bearer-token connection, disconnect, fresh session isolation.
- Upload text/Markdown files or pasted text; stable key replacement and version
  display; safe file type/UTF-8/size checks and API error handling.
- Document list with bounded pagination; passage listing and independent paging.
- Explicit delete confirmation; clear stale local evidence after mutations.
- Lexical question submission, excerpts labelled as excerpts, insufficient
  evidence and truncated-candidate states; exact citation re-fetch and source
  character spans, including Unicode code points.
- Safe response validation, 20-second request timeout, cancellation, no redirects
  carrying credentials, manual retry, loading/empty/success/error states.
- Loopback Vite proxy to `127.0.0.1:8000`; strict TypeScript and production bundle.

## Checks actually run

- `npm install --save-exact react react-dom zod` and scoped dev dependencies:
  **PASSED**, lockfile written; initial audit reported zero vulnerabilities.
- Initial `npm test`: **FAILED as expected (RED)** because `./api` did not exist.
- API implementation `npm test`: **PASSED**, five boundary tests.
- First full component run: **PASSED**, 15 tests. Its following `npm run
  typecheck` **FAILED** on unsupported Testing Library `exact` option; replaced
  that test query with an anchored accessible-name expression.
- Final `npm test`: **PASSED**, 15 tests across two files.
- `npm run test:contract`: **PASSED**, one test. A temporary migrated SQLite
  FastAPI app handled upload, document list, passage list, citation read, matched
  search and empty search; real serialized responses passed frontend validators.
  TestClient emitted a Starlette/httpx deprecation warning; no warning was hidden.
- Final `npm run build`: **PASSED**, strict TypeScript and Vite bundle (112
  modules transformed; main JS 319.80 kB / 97.30 kB gzip).
- Final `npm audit`: **PASSED**, zero reported vulnerabilities. This is a
  registry advisory check, not proof of dependency safety.

## Remaining limits

- Parent task owns browser/live-server, narrow viewport, keyboard and visual
  contrast checks. JSDOM axe checks exclude color contrast because it has no
  layout engine; they do not establish WCAG conformance.
- PostgreSQL retrieval-version identifier is accepted by the UI at the provider
  owner's request, but this contract test currently verifies only SQLite.
- No generation, vector search, benchmark results or public deployment are
  claimed by this milestone. Static hosting needs same-origin API routing and
  appropriate UI security headers; Vite is development-only.
- The automatic approval service initially failed with an account usage-limit
  error. That interrupted patch was not applied; after the user resumed, files
  were checked and the patch and verification commands were run successfully.

## Additive answer UI, 2026-10-20

The parent task implemented `/v1/capabilities` and `/v1/answers`; their source
contracts in `atlas/api.py`, `atlas/questions.py`, and `atlas/providers.py` were
read before this increment. Existing skill mapping was consulted. Additionally,
`C:/Users/advai/.codex/skills/error-handling/SKILL.md` was read fully and applied
to safe unavailable/malformed-response states, manual retries, bounded request
timeouts and an actionable source-changed (409) message. Its full-context logging
examples remain overridden by AGENTS privacy requirements.

Implemented capability-gated response mode, local model-selected verbatim claims,
exact source inspection, abstention and explicit conflict state, optional run
metadata, provider fee vs unmeasured compute cost, and 130-second answer request
timeout. Runtime parsing checks status/claims consistency, verbatim claim and
quote containment, citation mapping, and at least two citation IDs for conflict.
The UI never treats a match as proof of factual correctness or relevance.

Fresh checks: `npm test` **PASSED**, 20 tests across three files. Added tests cover
capability gating, answer source navigation and focus restoration, abstention,
conflicts, malformed/unsupported claims, and answer controls' axe structure.
`npm run test:contract` **PASSED**, one test now also checks real capabilities and
answer/abstention API serialization. Its model HTTP transport is explicitly
mocked; this is not real-model verification. Existing TestClient deprecation
warning remains visible. `npm run build` **PASSED**, strict TypeScript and Vite
bundle (113 modules; main JS 324.48 kB / 98.60 kB gzip).

This increment supersedes M3's statement that generation UI was absent. Public
deployment, model-quality evaluation, and real browser verification remain
outside this delegate's evidence. No new dependencies were added.
