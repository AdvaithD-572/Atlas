# Atlas

A technical-document knowledge platform under active development. The verified
local application supports authenticated text/Markdown/HTML/PDF ingestion, versioning,
deduplication, PostgreSQL background ingestion, lexical/vector/hybrid retrieval,
local Ollama answers with checked source excerpts, and a React document workspace.
Source access and deletion enforce owner scope.

The latest backend suite passed **181 tests with 91% statement coverage on Windows
and Linux**. The frontend
passed 28 component tests, a real API/report serialization contract check, and its
strict production build. Browser journeys exercised real PostgreSQL and local
models at three viewport sizes. These are engineering checks, **not evidence of
answer quality or a completed human benchmark**.

## Local setup

### Run this already-configured checkout with local models

The verified full application is at **http://127.0.0.1:8002**. Keep Docker Desktop
and Ollama running. This machine already has the required all-minilm:latest and
qwen3:1.7b models, private credentials, migrated database and built frontend.
The separate container preview at port 8080 has inference disabled.

To restart the full app later, open PowerShell in this project folder and run:

```powershell
docker compose --env-file .local/postgres.env -f compose.yaml -f compose.app.yaml up -d --wait postgres worker
Remove-Item Env:ATLAS_POSTGRES_DSN -ErrorAction SilentlyContinue
$env:ATLAS_POSTGRES_DSN_PATH = '.local/runtime.dsn'
$env:ATLAS_GENERATION_ENABLED = 'true'
$env:ATLAS_VECTOR_ENABLED = 'true'
$env:ATLAS_FRONTEND_DIR = 'frontend/dist'
$env:ATLAS_CHUNK_SIZE = '400'
$env:ATLAS_CHUNK_OVERLAP = '80'
uv run --locked uvicorn atlas.main:create_app --factory --host 127.0.0.1 --port 8002 --no-access-log --limit-concurrency 16 --timeout-keep-alive 5
```

Do not start a second server if port 8002 is already serving Atlas. The foreground
command stops with Ctrl+C. The agent-started instance currently runs in a hidden
process recorded in `.local/native-api.pid`; its logs are `.local/native-api.*.log`.
No automatic login/start-at-boot task was installed.

Copy your existing sign-in token privately from a second PowerShell terminal:

```powershell
Set-Clipboard -Value ((Get-Content .local/local.token -Raw).Trim())
```

Paste into **Access token** and click **Connect**. Add a text/Markdown document,
index it for semantic search, then select hybrid retrieval and ask a question.
Tokens stay in page memory. Model answers can be wrong or abstain; inspect citations.
Do not rerun credential initialization on this existing checkout.

### First setup on another checkout

Python 3.13 or 3.14 and [uv](https://docs.astral.sh/uv/guides/projects/) are required.
The SQLite profile requires SQLite >=3.42 with FTS5 for its secure-delete migration;
the pinned Docker Python image includes a verified compatible version.
From this directory:

```powershell
uv sync --locked
uv run python -m atlas migrate
uv run python -m atlas provision --owner local
uv run uvicorn atlas.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log --limit-concurrency 16 --timeout-keep-alive 5
```

Provisioning saves a random token to `.local/local.token` without printing it.
Protect `.local` using your OS account permissions; never commit or share it.
Do not expose this development server to a network. See [operations](docs/operations.md)
for configuration, API usage, migration and retention details.

For the frontend in a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the displayed loopback URL and use your privately provisioned token.
The default SQLite profile provides lexical search. Follow
[operations](docs/operations.md) for PostgreSQL, the worker, local models and the
Docker packaging profile. Local Docker API/worker HTTP and HTTPS checks have passed;
cloud deployment and remotely executed CI have not been verified.

```powershell
uv run --locked pytest -q --tb=no --cov=atlas --cov-report=term
uv run --locked ruff check atlas tests scripts
uv run --locked ruff format --check atlas tests scripts
uv run --locked mypy
uv run --locked pip-audit --progress-spinner off
```

Real PostgreSQL tests require `ATLAS_TEST_POSTGRES_DSN`; otherwise they are
explicitly skipped. See the operations runbook for secure setup.

The evaluation viewer opens exported reports locally, preserves unknown metrics,
and clears the report on disconnect. The runner can optionally measure actual
generated-answer citations, abstention and token usage with pinned model metadata.

An [AI review of 100 development cases](docs/engineering/evaluation-review.md)
records source provenance and weaknesses. These drafts are not human-reviewed
benchmark evidence; their frozen source snapshots remain separate from live docs.

Automated answer diagnostics and a separate reranking experiment use the 100-case
development set. The ranker remains disabled; model ratings are not calibrated
quality scores. See the [results and critique](docs/engineering/nonhuman-completion.md).
Restricted database roles, worker health, actual backup restoration, local TLS and
Linux private-file permissions have verified operational checks.

Remaining acceptance work includes 100 genuinely human-reviewed benchmark cases,
representative semantic-quality acceptance, hosted CI and operator-specific public
identity/certificate/backup operations. PDF extraction supports text layers and page
locations; encrypted and image-only PDFs are rejected (no OCR). HTML extraction
keeps headings and ignores active content; it does not compute CSS visibility.
See [format limits and evidence](docs/engineering/formats-and-hosting.md).
Local model extraction validates provenance, not truth or relevance.

See [BUILD_STATE](BUILD_STATE.md) for actual check outcomes and incomplete work,
[milestones](docs/engineering/implementation-plan.md),
[architecture](docs/architecture.md), [security](docs/security.md) and
[skill evidence](docs/engineering/skill-usage.md).

