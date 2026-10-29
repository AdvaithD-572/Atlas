# Vector and hybrid integration evidence

Verified locally 2026-10-20. Synthetic fixtures verify behavior, not retrieval
quality. The 100-case human-reviewed benchmark remains incomplete.

## Implementation and acceptance

`atlas/vector_retrieval.py` integrates explicit semantic indexing, exact cosine
search and reciprocal rank fusion into the real API, answer service and React UI.
Migration `atlas/pg_migrations/002_embeddings.sql` stores owner, source chunk,
model identity/digest, dimensions and index version. Foreign keys cascade on
replacement/deletion. Publication rechecks the complete source snapshot after
embedding; provider work occurs outside the write transaction.

| Requirement | Actual verification |
|---|---|
| Separate vector baseline | Real PostgreSQL cosine SQL with synthetic embedding vectors; actual local embeddings in browser flow |
| Hybrid fusion | Rank math, duplicate removal, deterministic ties, real lexical/vector combination |
| Ownership | Unauthorized indexing fails before provider call; scoped vector results exclude other owners |
| Atomic index | Failed later batch preserves prior index; source/model mutation rejects publication |
| Lifecycle | Reindex avoids duplicate rows; replacement/deletion invalidates embeddings and citations |
| Bounds | 128-chunk limit and concurrent-index rejection before inference; batches of 32; 10,000-chunk search cap |
| API/UI | Authenticated index, vector/hybrid search and answers; real browser source inspection and deletion |
| Evaluation compatibility | Pinned mode/version/model digest, complete indexed coverage required |

Vector version is `cosine-exact-v1`. Hybrid version is `rrf60-depth20-v1`:
top 20 results from each baseline, score sum `1 / (60 + rank)` with one-based
ranks. Lexical candidate collection is bounded to 200 and exposes truncation.
UI warns when that stage is truncated. Model changes exclude old vectors and
report unindexed coverage; operators explicitly reindex.

## Checks actually run

- `uv run --locked pytest -q --tb=no --cov=atlas --cov-report=term` with the
  private test DSN: **124 passed, 93% statement coverage**. One known dependency
  deprecation warning. Real database tests used isolated random schemas.
- `uv run --locked ruff check atlas tests scripts`,
  `uv run --locked ruff format --check atlas tests scripts`, and
  `uv run --locked mypy`: passed. Latest type check covered 18 source modules.
- Frontend `npm test`: **20 passed**; `npm run test:contract`: **one passed**;
  `npm run build`: passed strict TypeScript and Vite.
- `node scripts/browser_smoke.cjs` with the disposable PostgreSQL browser server:
  real local embedding index, vector/hybrid searches, local-model answer, source
  reauthorization, replacement and deletion passed. No page errors or failed
  HTTP requests; no axe violations or overflow at 375/768/1440 pixels.

The first combined vector/database run had 25 passes and one failure: a schema
corruption test could no longer drop chunks because embeddings correctly depended
on them. Its isolated test-only corruption setup was updated to include dependent
objects. The full passing suite above is the subsequent result.

## Limits

No approximate vector index, reranker, official quality comparison or automatic
background embedding stage exists. Indexing runs in a bounded API worker thread.
The schema stores one embedding identity per chunk, so a model comparison needs
controlled reindexing of the same frozen source corpus. Small synthetic browser
questions do not establish semantic relevance, conflict handling quality, or
faithfulness. Exact quotation checks establish provenance only.
