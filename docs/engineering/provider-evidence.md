# Local provider and question integration — 2026-10-20

Implemented `atlas/providers.py`, `atlas/questions.py`, API/config wiring,
`tests/test_provider.py`, `tests/test_provider_adversarial.py`,
`tests/test_questions.py`, and `scripts/provider_smoke.py`.

The provider uses installed local Ollama models only. Loopback endpoints, no
redirects/proxy environment, remote-model metadata rejection, bounded two-slot
concurrency, bounded transient retries, 2 MB output limit, and an asynchronous
60-second overall HTTP deadline protect the synchronous application interface.
Each call closes its HTTP client; there is no detached timeout thread continuing
inference after the application deadline. Model availability checks have a
three-second budget per configured model. No model is downloaded implicitly.

Embeddings validate count, consistent dimensions, finite nonzero norms and model
identity. Model digests are recorded. Generation requests structured claims and
citations; each claim must occur verbatim in every cited passage, each quote must
occur in its corresponding passage, and all IDs must be supplied evidence IDs.
Blank claims, fabricated IDs/quotes and inconsistent status/claim output fail.
Empty retrieval returns explicit abstention without inference. Claims and
retrieval settings are returned separately. Source access is revalidated after
inference; concurrent replacement/deletion returns 409. A later deletion can
still make a previously returned citation unavailable.

This is extractive grounded generation: a local model selects source claims.
Exact substring validation proves provenance, not truth, relevance, adequate
coverage, absence of malicious quoted content, or correct conflict detection.
Conflicting-evidence output requires multiple sources; human semantic review
remains necessary. The trusted local Ollama operator must not mutate model
aliases during a run; tags metadata is observed before inference, not a
cryptographic attestation of execution.

## Executed results

- Original selected backend suite: 59 passed.
- Independent adversarial suite initially failed all eight tests: unsupported
  secondary citations, blank claims, two numeric-overflow cases, unbounded
  streamed duration, two remote-alias metadata cases, and model mismatch.
- After repairs: `uv run --locked pytest tests/test_provider.py
  tests/test_provider_adversarial.py -q --tb=short`: 22 passed.
- `uv run --locked pytest tests/test_questions.py -q --tb=short`: six passed,
  including real SQLite/API ownership and source invalidation with an explicit
  fake inference provider.
- `uv run --locked python -m scripts.provider_smoke`: actual local embeddings,
  generation and empty-evidence abstention passed. Earlier timeout and false
  abstention failures were retained as failures, then fixed/retested. Prompt
  `extractive-grounding-v2` includes format examples; the synthetic smoke was
  used during development and is not a holdout or benchmark.
- Observed warm run: all-minilm:latest, digest
  `1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef`,
  dimension 384, embedding 122.57 ms. qwen3:1.7b, digest
  `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`,
  generation 569.83 ms, 349 input/42 output tokens, one validated claim.
  These are single-run smoke timings, not latency distributions.
- Provider service fee is zero; local compute/electricity cost is unmeasured,
  returned as null. No paid fallback exists.
- Actual browser → API → retrieval → Ollama → citation inspection also passed;
  see browser-evidence.md.

Remaining: human answer/conflict/injection quality evaluation, representative
load and cold-start measurements, complete vector/hybrid integration, and
deployment verification. The local-only policy is not a substitute for an
operator-enforced network egress boundary.
