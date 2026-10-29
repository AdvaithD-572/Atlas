# Atlas

A technical-document knowledge platform under active development. The verified
local application supports authenticated text/Markdown ingestion, versioning,
deduplication, PostgreSQL background ingestion, lexical/vector/hybrid retrieval,
local Ollama answers with checked source excerpts, and a React document workspace.
Source access and deletion enforce owner scope.

The backend suite passed **132 tests with 93% statement coverage**. The frontend
passed 25 component tests, a real API/report serialization contract check, and its
strict production build. Browser journeys exercised real PostgreSQL and local
models at three viewport sizes. These are engineering checks, **not evidence of
answer quality or a completed human benchmark**.

## Local setup

Python 3.13 or 3.14 and [uv](https://docs.astral.sh/uv/guides/projects/) are required.
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
Docker packaging profile. Local Docker API/worker HTTP checks have passed;
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

Remaining acceptance work includes 100 genuinely human-reviewed benchmark cases,
answer-quality and reranking experiments, and production
identity/TLS/backup verification. PDF and HTML are rejected until tested parsers
exist. Local model extraction validates provenance, not truth or relevance.

See [BUILD_STATE](BUILD_STATE.md) for actual check outcomes and incomplete work,
[milestones](docs/engineering/implementation-plan.md),
[architecture](docs/architecture.md), [security](docs/security.md) and
[skill evidence](docs/engineering/skill-usage.md).

