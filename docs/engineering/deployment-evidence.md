# Local packaging and operational evidence

Observed 2026-10-20. This is local Docker Desktop verification, not a public
deployment or an externally executed CI run.

## Implemented

The multi-stage Dockerfile builds the locked React client and Python runtime.
Base images are pinned by digest. Runtime UID/GID is 10001:10001. The Compose
overlay runs API and continuous ingestion worker against the existing PostgreSQL
service, with loopback publication, read-only runtime, dropped capabilities,
no-new-privileges, bounded resources and a read-only credential-registry mount.
Generated credentials are excluded from the build context.

The public static bundle is served after protected API routes. Tests verify CSP,
API authentication and traversal rejection. The API has a storage readiness check;
the worker has no health probe. Successful queued processing is verified separately.

`.github/workflows/ci.yml` defines locked Python/frontend checks, a real
PostgreSQL service, dependency audits and image build. GitHub action revisions
were resolved and pinned to commits. No publishing step or remote run is claimed.

## Checks actually run

| Command/check | Result |
|---|---|
| `docker build -t atlas-app:local .` | Passed initial application image build |
| Compose `config --quiet`, explicit migrate, `up -d --wait api worker` | Passed |
| `docker image inspect atlas-app:local --format '{{.Config.User}}'` | `10001:10001` |
| `uv run --locked python -m scripts.container_smoke` | Passed static/CSP/readiness/auth/queue/continuous-worker/search/source/delete checks |
| `uv run --locked python -m scripts.workload_smoke` | 100 serial lexical queries, zero failures; synthetic document deleted afterwards |
| Initial `node scripts/container_browser.cjs` | Failed: browser requested missing favicon; React did render under CSP |

The favicon was added as a local SVG; final rebuilt-image verification is recorded
in the continuation below rather than treating the code edit alone as a pass.

Final continuation: `docker build -t atlas-app:local .` and Compose
`up -d --wait api worker` passed after the favicon/warning update.
`node scripts/container_browser.cjs` then returned `react_rendered: true` with
an empty errors array. `uv run --locked python -m scripts.container_smoke`
passed all eight checks again against the rebuilt package. No outstanding
failure remains in this packaging smoke scope.

The workload was one warm synthetic document, concurrency 1, local HTTP,
PostgreSQL and a one-CPU API container. Measured p50 **10.453 ms**, p95
**11.880 ms**, p99 **13.346 ms**. Zero model calls; compute cost was not measured
and remains null. `.local/workload-smoke.json` records the machine-readable
observation. These results are not an SLA, scale test or answer-quality benchmark.

## Packaged evaluation and provider follow-up, 2026-10-25

Rebuilt the API image and recreated API/worker with the same Compose database volume.
The final image includes the report viewer, candidate-truncation warning, readable
narrow table, and bounded embedding context diagnostic. Build and startup passed.
`scripts/container_smoke.py` passed queued ingestion, actual worker completion,
lexical search, citation and document/job deletion. `scripts/container_browser.cjs`
passed real React/CSP rendering with no page errors.

`scripts/evaluation_browser.cjs --container --report
evaluation/atlas-docs-v1-run-002/hybrid/results.json` loaded the actual 100-case
development report and passed widths 375/768/1440, no horizontal overflow, no axe
violations, no report upload, no browser storage, and report clearing after
disconnect/reconnect. The 375-pixel screenshot was visually inspected; an initial
word-wrap issue was fixed and the same checks rerun. Artifacts are in
`.local/evaluation-browser-qa/`. This is not full screen-reader/WCAG certification.

Real model-context rejection/recovery was verified separately with the native
in-process API, local Ollama and isolated PostgreSQL schemas. The container profile
still has models disabled. No public deployment or hosted CI execution is implied.

## Remaining limits

- Models are disabled in this container profile; native API/Ollama integration
  is separately verified. Container loopback does not reach host Ollama.
- Hosted CI, public deployment/certificate operations and representative
  concurrency/load remain unverified. No Git remote is configured.
- Machine/Docker administrators still control local secrets and data.
- Human evaluation is not completed by packaging. Reranking is a separate
  development experiment documented in nonhuman-completion.md.
- Dependency audits passed at their execution time; they do not guarantee absence
  of vulnerabilities. One Starlette TestClient/httpx deprecation warning remains.

## Operational controls, 2026-10-25

The runtime now uses a separately provisioned non-admin PostgreSQL role; only
migration tooling receives administrator credentials. Worker health checks recent
processing-loop progress and storage readiness. File-based runtime DSNs work in
both API and worker, and partial provisioning rolls back only its new artifacts.

Actual `scripts.package_checks` passed the final rebuilt image's queued lifecycle,
source resolution/deletion, disposable backup restoration, verified HTTPS lifecycle,
unknown-CA and wrong-host rejection, then restored loopback HTTP. Global trust and
retained application data were unchanged. `scripts.linux_permissions_smoke` proves
mode-0600 file access fails for the wrong Linux UID and succeeds for the configured
non-root owner, including certificate generation and HTTPS lifecycle.

The first full Linux suite exposed unsupported SQLite secure-delete in the old
bookworm base. A digest-pinned Python trixie base supplies SQLite 3.46.1; the final
non-root/read-only-source Linux run passed 160 tests with 93% coverage, Ruff and
strict mypy. Windows passed the same 160 tests. Linux image build passed 26 React
tests and strict build. A new certifi advisory was fixed through a targeted lock
update to 2026.10.23; the subsequent Python and npm audits had no known findings.
See [the recorded advisory](https://osv.dev/vulnerability/PYSEC-2026-4320).

Shared scripts are wired into the pinned workflow, including cleanup. This is
actual local Linux verification, not a claim of GitHub-hosted execution. Commands,
synthetic restore timing and external-only boundaries are in nonhuman-completion.md.
