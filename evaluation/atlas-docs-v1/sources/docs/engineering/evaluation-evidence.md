# Evaluation foundation evidence — 2026-10-19

Owned files: `atlas/evaluation.py`, `tests/test_evaluation.py`, `docs/evaluation.md`,
and this record. No benchmark data files created. Synthetic fixtures exist only
inside test code and isolated pytest temporary directories.

## Skill mapping and actual usage

Read full skills from `C:/Users/advai/.codex/skills/<name>/SKILL.md` after inspecting
AGENTS.md, pyproject.toml, retrieval/API contracts and existing tests. Root library
inventory is recorded in `skill-usage.md`. No nested instruction files appeared in
the enumerated source/docs/test tree.

| Skill | Mapping | Actual use / limits |
|---|---|---|
| eval-harness | Behavior definitions and deterministic evaluation | Tests before module; official gates, hashes, failure reports. Followed manually; Claude slash commands unavailable. Candidate-containment utilities not used or claimed. |
| python-testing | Isolated regression tests | Parametrized schema failures, denominator boundaries, temporary artifacts, real application/index integration, red/green evidence below. |
| benchmark | Timing and repeatable reports | Per-case serial timing, p50/p95/p99, JSON/CSV/Markdown. Concurrent 100-request workload is pending; no performance baseline or SLA claim. |
| benchmark-methodology | Applicability inspection | Read; not applied because it benchmarks competitor branding/positioning, not retrieval. |

AGENTS overrides generic skill target scores; no paid judge; artifacts use native
Atlas docs rather than unrelated Claude folders. Parent integrates this record
into shared skill mapping; delegate does not edit shared files.

## Executed checks

- RED: `.venv/Scripts/python.exe -m pytest tests/test_evaluation.py -q` before module:
  failed collection with `ModuleNotFoundError: atlas.evaluation`.
- Initial GREEN: same command passed 14 tests. Initial Ruff formatting/import errors
  and mypy Counter-key annotation failure were fixed, not suppressed.
- `.venv/Scripts/python.exe -m pytest tests/test_evaluation.py -q
  --cov=atlas.evaluation --cov-report=term-missing`: 20 passed; 92% statement coverage
  (244 statements, 19 missed); Python 3.14.7. Existing Starlette/httpx deprecation
  warning retained.
- Fresh run after usage reset: scoped pytest 20 passed in 0.45 seconds; scoped Ruff
  passed; scoped mypy passed (one source file).
- Commands: `.venv/Scripts/python.exe -m ruff check atlas/evaluation.py
  tests/test_evaluation.py`; `.venv/Scripts/python.exe -m mypy atlas/evaluation.py`.

Real FastAPI application, authenticated synthetic owner, SQLite ingestion/index,
lexical retrieval and artifact writer run through TestClient. CLI integration
substitutes HTTP transport only, not retrieval results. This does not verify a live
network deployment or external model provider.

Passed: strict validation, metric edge cases, duplicate IDs, source/dataset/corpus
integrity rejection, in-memory mutation rejection, synthetic/unreviewed/category
gates, unavailable-mode rejection, error redaction, unknown values null, rating
attribution, overwrite refusal and API/CLI artifact integration.
Failed outstanding: none in scoped checks. Skipped: live network CLI and load test.
Blocked: real human-checked benchmark, vector/hybrid/reranking, generated answer
quality and production performance. Documentation write was temporarily rejected
because automatic approval review hit its usage limit; no unsafe-action verdict
was issued. The same write completed after the user resumed following reset.
