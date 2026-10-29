# Evaluation protocol and current implementation

**Confirmed:** Atlas requires at least 100 human-checked cases and separate retrieval,
answer, citation, abstention, latency, failure, and cost measurements.
**Discovered:** the backend supplies lexical, vector and hybrid excerpts plus
optional local generated answers. `atlas/evaluation.py` has HTTP retrieval
adapters for all three modes and optional generated-answer observations. Semantic
correctness and faithfulness still require attributed review; no automatic judge
is treated as ground truth.
**Confirmed:** the user requested AI review and critique. Atlas's own documentation
is the proposed default development corpus; 100 AI-authored drafts and source
snapshots are frozen in `evaluation/atlas-docs-v1`. Human review fields remain null.
No official benchmark results exist. See the [AI critique](engineering/evaluation-review.md)
for the limits of these development labels.

## Dataset contract

Each UTF-8 JSONL line is a strict `DatasetCase`. Unknown fields and coerced booleans
are rejected. Fields: `case_id`, `category`, `question`, `answerable`, `expected_facts`,
`relevant_passages`, `scoring_notes`, `human_reviewer`, `reviewed_at`, and optional
`synthetic` (false by default). Reviewer and timezone-aware ISO timestamp are both
null until actual review and must be supplied together. Future timestamps fail.
Never populate review fields on behalf of a person who did not review.

`relevant_passages` maps indexed passage IDs to SHA256 of the original source document
bytes (`Document.content_hash`), not excerpt text. Answerable cases require facts and
passages. Questions are capped at 512 characters, IDs are unique, and JSONL is limited
to 10 MiB. Official mode requires at least 100 cases, recorded human review on every
case, no synthetic cases, and these exact category shares:

| Category | Share | Count at 100 | Review focus |
|---|---:|---:|---|
| direct | 25% | 25 | Fact with supporting evidence |
| multi_document | 20% | 20 | Required evidence spans documents |
| unanswerable | 20% | 20 | Corpus cannot answer |
| conflicting_outdated | 15% | 15 | Dates, versions, unresolved disagreement |
| difficult | 20% | 20 | Paraphrase or difficult retrieval |

The gate proves metadata completeness, integrity, and proportions, not that a human
actually reviewed or that semantic labels are correct. Humans must verify those.
Larger sets preserve exact shares; protocol changes need documented justification.
Freeze dataset-byte SHA256 and corpus SHA256 before running. `corpus_digest(mapping)`
hashes sorted-key JSON, UTF-8, no ASCII escaping, separators comma/colon, mapping all
authorized passage IDs to document hashes. Expected passages must belong to that
snapshot and match source hashes. Use identical frozen inputs across configurations.
Reserve a human-selected holdout before tuning; record split membership separately
from this v1 schema. No quality thresholds have been invented.

## Metrics (atlas-eval-v1)

| Metric | Definition | Denominator / undefined cases |
|---|---|---|
| Recall@k | Unique relevant retrieved IDs in first k / relevant IDs | Null without relevant passages; empty retrieval otherwise zero |
| MRR@k | Reciprocal rank of first relevant ID within k; macro mean | Null without relevant passages; no hit zero; original positions preserved |
| Citation precision | Unique cited relevant IDs / unique cited IDs | Null without citations |
| Citation recall | Unique cited relevant IDs / relevant IDs | Null without relevant passages; empty citations otherwise zero |
| Abstention | Positive means should abstain; TP/FP/TN/FN, precision, recall, accuracy | Only explicit abstention observations; zero denominators null |
| Correctness / faithfulness | Separate human ratings in [0,1] | Null without actual attributed ratings; no model judge |
| Latency | Per-case wall milliseconds; nearest-rank p50/p95/p99 | All attempted cases, including failures; serial workload |
| Failures | Callback/provider/schema errors | All attempted cases |
| Tokens / estimated USD | Supplied per-observation usage/estimate | Null if unknown; no invented zero/free usage |

Each mean records scored-case count. Quality means exclude nulls and failures;
compare failures alongside scores to avoid survivorship bias. Citation overlap is
an evidence-ID proxy, not semantic claim support. Semantic citation correctness
requires human review. The retrieval-only adapters leave generated-citation, abstention,
correctness, faithfulness, model usage, and cost fields null because it does not
produce answers. Empty retrieval is not proof of answer-abstention behavior.

## Reproducible commands

From the project root with established development dependencies installed:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_evaluation.py -q
.venv/Scripts/python.exe -m atlas.evaluation --help
```

For a real dataset, set `ATLAS_EVAL_TOKEN` securely in the environment (never commit
it or place it on the command line), start the API, and supply pre-pinned hashes:

```powershell
.venv/Scripts/python.exe -m atlas.evaluation path/to/reviewed.jsonl `
  --dataset-sha256 DATASET_SHA256 --corpus-sha256 CORPUS_SHA256 `
  --mode lexical --retrieval-version postgres-simple-overlap-v1 `
  --corpus-version CORPUS_LABEL --chunking-version CHUNK_CONFIG_LABEL `
  --output evaluation-results/run-001 --official
```

Remove `--official` only for explicitly nonofficial development experiments. The
runner fetches authenticated documents/passages, validates the snapshot before
queries, and checks it afterwards. Keep the corpus quiescent: HTTP snapshots are
not database snapshot isolation and a mutation restored between snapshots can evade
detection. Retrieval requests have 130-second timeouts, no redirects, and no retries. Remote
APIs require HTTPS; loopback HTTP supports local development.

Outputs: `results.json`, `results.csv`, `results.md`, containing dataset/corpus hashes,
config/hash, evaluator version, timestamp, case IDs/metrics, timings, truncation and
failures. Existing output directories are never overwritten. Questions, expected
facts, excerpt/answer text, raw errors and credentials are excluded. IDs/hashes are
still linkable; keep artifacts access-controlled and delete them when source
retention requires it. Automatic artifact purge is not implemented. Corpus/chunking
version labels default to `unspecified`; pass explicit CLI labels and
archive actual index settings for a published comparison.

For the SQLite baseline use retrieval version `fts5-overlap-v1`. For vector or
hybrid runs, set `--mode vector` / `--mode hybrid`, the corresponding version
`cosine-exact-v1` / `rrf60-depth20-v1`, and `--model-id` plus `--model-digest` to the
embedding identity returned by semantic indexing. Use the same dataset/corpus
hashes in separate output directories. The adapter rejects mode, version and
model mismatches and any unindexed owner passages; missing coverage cannot
silently improve or worsen a published comparison.

To observe generated answers, add `--answers --generation-model-id MODEL`
`--generation-model-digest SHA256 --prompt-version extractive-grounding-v2`.
Answer runs require k <= 5 and use a 300-second HTTP timeout. The adapter validates
generation identity, prompt version, citation membership and exact claim support.
It records explicit abstention, citation IDs and available token usage. Correctness,
faithfulness and unmeasured compute cost stay null. This standard observer does
not use a model judge; the experimental diagnostics below are a separate artifact.

In the authenticated frontend, select an exported `results.json` under Evaluation.
The file is validated and read only in browser memory (10 MiB maximum); no report
upload or persistence occurs. Clear/disconnect invalidates pending reads. A declared
official flag is displayed as a declaration, not verification of provenance.

## AI-reviewed development workflow

Reproduce the draft bytes from their frozen sources into a new directory:

```powershell
uv run --locked python -m scripts.review_drafts `
  --source-root evaluation/atlas-docs-v1/sources --output .local/drafts-copy
uv run --locked python -m scripts.draft_evaluation `
  --output evaluation/atlas-docs-v1-run-NEW
```

The comparison requires the existing local PostgreSQL DSN file and installed
all-minilm model. It creates an isolated database schema and loopback API on port
8001, ingests only the 12 frozen documentation files, indexes them, binds real
passage IDs, runs all three retrieval modes and removes the disposable schema on
exit. The test-only request quota is 1000/minute; application defaults stay 120.
It uses literal 400-character chunks with 80 overlap and no provider truncation.
The first attempted 800/120 run failed on the installed model's context limit.

Binding chooses a deterministic minimal cover of each exact expected source span.
Labels omit other semantically equivalent passages, so Recall/MRR are canonical
span proxies and can undercount useful retrieval. Re-created document/passages get
new IDs and hashes; compare configurations within the same bound run. No holdout
exists and no tuning against these cases should be presented as unseen quality.
All artifacts are explicitly nonofficial; no human identities or ratings are invented.

## Experiment matrix and remaining acceptance

| Configuration | Status | Evidence |
|---|---|---|
| Lexical FTS5/overlap v1 | Implemented | Synthetic unit/API integration tests; no official score |
| Vector | Implemented | Real pgvector/owner isolation tests and local-model browser flow; no official score |
| Hybrid | Implemented | Tested RRF, pinned runner and local-model browser flow; no official score |
| Reranking | Offline experimental stage | Strict local-model permutation of authenticated hybrid top-20; application default remains disabled |
| Generated answers | Application and observation runner implemented | Real local-model CLI smoke; no human quality ratings |

Official benchmark remains BLOCKED on actual human review,
quality thresholds and holdout evaluation. Deterministic tooling is independently
testable; it does not satisfy the complete project benchmark requirement.

## Automated semantic diagnostics and reranking

```powershell
uv run --locked python -m scripts.draft_evaluation --quality-study `
  --output evaluation/atlas-docs-v1-run-NEW
```

This runs the same three retrieval baselines, then 100 paired reranker trials and
actual hybrid answer requests. It requires installed local qwen3:1.7b as well as
the embedding model; no provider fee or new service is introduced. The predeclared
gate requires Recall@5 gain >=.02, no MRR regression, no added failures, and added
p95 latency <=2000 ms. Baseline first-five and reranked first-five use exactly the
same authorized candidate pool. The ranker receives no labels or expected facts;
invalid/missing/duplicate/invented references fail, without silent baseline fallback.

`quality-study/protocol.json` records dataset/corpus hashes, model digests, prompt
versions and limits before scoring. `cases.jsonl` preserves each result/failure,
tokens and stage durations without raw answers/source text. `results.json` and
`results.md` report paired successful metrics, failure-as-zero metrics across all
answerable cases, attempted/failed/skipped stages, and survivor-only versus all-case
abstention outcomes. A passed `verification.json` is required to show the source
versions were checked again after the run; pending/failed runs are not publishable.

The separate judge reports **raw model-rated** fact coverage (supported=1,
partial=.5, missing=0), claim relevance and status appropriateness. These are
conditional means with explicit rated-case denominators. Empty fact/claim arrays
are unscored. Contradictory ratings on abstained answers are flagged, not corrected
or silently discarded. The same small model generates and judges answers; it has
demonstrated semantic mistakes even when its output satisfies the schema. These
ratings are uncalibrated diagnostics, not validated correctness or faithfulness.
Human fields stay null. Local compute cost is unknown; provider service fee is zero.

The dataset has already been used repeatedly and is not an untouched holdout.
Canonical span labels omit equivalent relevant text. See the actual experiment
outcomes and critique in [nonhuman completion](engineering/nonhuman-completion.md).
