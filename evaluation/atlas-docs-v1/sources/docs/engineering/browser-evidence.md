# Live browser evidence — 2026-10-20

Executed `uv run --locked python -m scripts.browser_smoke_server`,
`npm run dev -- --strictPort` in frontend, and `node scripts/browser_smoke.cjs`
with NODE_PATH pointing to the installed Codex runtime's Playwright package.
The API used a temporary SQLite database and an explicitly public synthetic
test credential; it must never be used for real data. No account credentials
appear in saved screenshots.

The app-browser tool failed at startup with the Windows sandbox helper error.
The browser-qa skill permits direct Playwright; headless installed Edge provided
the fallback. No browser profile or production service was used.

Passed against real loopback API and Ollama:

- Authentication and empty state; text upload and indexed metadata.
- Lexical search; keyboard Enter opens a source and moves focus to its heading;
  closing restores focus to the invoking button.
- Local model selects a verbatim claim; citation button fetches the correct
  authorized source again.
- Empty retrieval abstention, version-2 replacement, confirmed deletion,
  disconnect, and zero localStorage/sessionStorage entries.
- Widths 375, 768, 1440: no horizontal overflow; axe reported zero violations
  for configured WCAG A/AA tags, including color contrast.
- Zero page errors and zero HTTP error responses in the successful journey.

Machine-readable evidence and full-page screenshots are under ignored
`.local/browser-qa/`. The parent visually inspected the 375- and 1440-pixel
screenshots. Reproduce with the checked-in scripts; screenshots are observations,
not fabricated production content.

Limitations: visual regression is inconclusive without a prior baseline.
Screen-reader behavior, full WCAG conformance, all keyboard paths, Core Web
Vitals, mobile hardware, public deployment, and representative workload
performance were not established. Component tests cover additional error/retry
states; those are not all exercised in this live journey.
# Continuation: PostgreSQL and semantic retrieval, 2026-10-20

The journey was rerun against `scripts.browser_smoke_server --postgres` using an
isolated random PostgreSQL schema and the actual local Ollama models. It passed
semantic indexing, vector and hybrid retrieval, generated answer/source access,
replacement and deletion. The resulting `.local/browser-qa/report.json` records
zero page errors/HTTP failures and zero axe violations or horizontal overflow at
375/768/1440. Screenshots were refreshed; no historical visual baseline exists.
See vector-evidence.md for limits. All fixture documents and credentials are
explicitly synthetic; these checks do not establish model quality.

