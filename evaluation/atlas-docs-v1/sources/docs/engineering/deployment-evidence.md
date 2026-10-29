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

## Remaining limits

- Models are disabled in this container profile; native API/Ollama integration
  is separately verified. Container loopback does not reach host Ollama.
- Hosted CI, public deployment, TLS, least-privilege database roles, backup restore
  and representative concurrency/load remain unverified.
- The local database role is an administrator. Secret injection protects source
  control, not access by the machine/Docker administrator.
- Human evaluation and reranking experiments are not completed by packaging.
- Dependency audits passed at their execution time; they do not guarantee absence
  of vulnerabilities. One Starlette TestClient/httpx deprecation warning remains.
