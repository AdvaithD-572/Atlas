# AI review and development evaluation — 2026-10-24

**Confirmed:** the user asked Codex to review and critique the cases itself.
**Proposed default:** use Atlas's existing documentation, with no external corpus,
paid judge or invented human attribution. **Discovered:** the frozen artifact has
100 distinct questions in the requested 25/20/20/15/20 distribution, with exact
source spans and hashes for answerable cases. Human review count is zero.

## Review findings

This is useful development material, but it is not a representative quality benchmark.
The same AI authored and reviewed every question. Source checks prove location and
integrity; they do not independently establish the labels' semantic adequacy.

| Cases | Finding | Consequence and correction |
|---|---|---|
| 001–025 | Short documentation anchors and lexical wording | Easy factual smoke coverage; add realistic support questions in a later corpus |
| 026–045 | Two facts joined into one question | Files are distinct, but this does not prove multi-hop reasoning; replace with genuine dependencies |
| 040 | Original wording asked when a lease becomes recoverable, but anchor only stated duration | Corrected before freezing to ask for the default lease duration |
| 046–065 | Negatives concentrate on absent production deployments, measurements and human scores | Useful hallucination checks, narrow negative distribution; add plausible near-miss domain questions |
| 066–080 | Questions strongly cue historical/scope reconciliation | Easy answer direction; does not measure neutral conflict discovery |
| 072 | Pending semantic answer quality and an implemented observation runner can both be true | Treat as a scope distinction; never infer that the runner proves quality |
| 073–074 | Ownership of browser checks and local-vs-public deployment are scope distinctions | Weak conflict proxies beyond the three already flagged in per-case notes |
| 078–080 | Native/container settings, synthetic/human evidence and audit/security scope | Explicit weak proxies; replace before claiming representative conflict coverage |
| 081–100 | Paraphrase the first 20 facts | Difficulty is unmeasured; keep related facts in one split to prevent leakage |
| All | Minimal canonical passage covers omit alternative valid evidence | Recall/MRR can undercount useful retrieval; obtain exhaustive relevance judgments before official scoring |

Each JSONL draft records its AI review and scoring notes. The global findings above
supplement those notes; a `development_only` review status is not an approval for
official benchmarking. The original source snapshots intentionally retain historical
statements and test counts; current documentation lives outside the snapshot.

## Implementation and verification

- `scripts/review_drafts.py` validates anchors before writing, saves exact source
  bytes, hashes the exact JSONL bytes, and refuses to overwrite an existing set.
- `scripts/draft_evaluation.py` verifies source hashes, binds actual API passage
  IDs using source spans, and compares the three modes on one bound snapshot.
- Nine new provenance/binding tests cover all 100 cases, hash consistency,
  overwrite refusal, changed anchors, missing spans and corrupted indexed text.
- Failed then fixed: Windows newline translation changed the saved JSONL hash;
  exact-byte writes now preserve it. A test fixture used the platform encoding;
  explicit UTF-8 fixed its Unicode quote mismatch.
- First real corpus indexing failed: Ollama returned HTTP 400, input exceeded
  context length, surfaced as safe API 502. The 800/120 attempt produced no scores.
  The next development run uses explicit 400/80 chunks, with truncation still off.
- Full backend checks: 141 tests passed with real PostgreSQL, 93% statement
  coverage; lint, format (41 files) and strict mypy (18 modules) passed.
- Frontend: 26 tests, one real Python serialization contract test, and strict
  production build passed. The contract includes retrieval and answer reports.
- Real local qwen3 CLI smoke passed on two labeled synthetic cases: a cited answer
  and empty-evidence abstention. It is integration evidence, not semantic scoring.

## Measured retrieval comparison

`evaluation/atlas-docs-v1-run-002` completed all three modes: 12 source documents,
226 passages, 100 serial questions per mode. Recall/MRR use the 80 answerable cases;
20 unanswerable cases have no relevant-passage denominator. All modes share dataset
hash `5cd963ee3af16835ed38b17b3e005f733a42efea60c596c53f0fd578f5a35f11`
and corpus hash `d2cce2b7518ec1bae1fc92f9eac1d89aa69f5c53c145c0a98279e4a0bd79e812`.

| Mode | Recall@5 | MRR@5 | Failures / 100 | p50 / p95 / p99 ms | Truncated cases |
|---|---:|---:|---:|---|---:|
| Lexical | 0.46875 | 0.423125 | 0 | 44.604 / 61.442 / 72.939 | 32 |
| Vector | 0.60625 | 0.526875 | 0 | 379.696 / 466.675 / 4011.958 | 0 |
| Hybrid | 0.63750 | 0.532917 | 0 | 392.500 / 499.651 / 566.728 | 32 |

Hybrid had the highest aggregate canonical-span recall, but did not improve every
category: conflicting/outdated recall was 0.4000 versus vector's 0.4333. Direct
recall was 0.76 hybrid, 0.72 vector, 0.52 lexical. These observations do not justify
a general quality claim or choosing a reranker. No parameters were tuned against
these scores. Chunk size changed before scoring only because indexing failed.

The lexical candidate cap truncated 32 queries; hybrid inherited that flag.
This affects interpretation and remains a disclosed baseline limitation. Vector's
4-second p99 outlier has no verified causal explanation. Timings are a single
fixed-order local run on a shared Windows host, not isolated load testing or a
production SLA. Full regression checks ran during setup; unrelated local services
also remained running. There is no repeated-run confidence interval.

Generation was disabled for this retrieval comparison. Correctness, faithfulness,
citations, answer abstention and compute cost remain unmeasured/null. The separate
two-case real-model smoke proves observation plumbing only. Machine-readable JSON,
CSV and Markdown reports retain failures, denominators, truncation and model identity.

## Self-evaluation of this draft deliverable

Follow-up, 2026-10-25: the actual hybrid report passed packaged browser checks at
375/768/1440, including the 32-case truncation disclosure and unknown ratings.
Screenshot review found and fixed awkward wrapping of “Not measured.” The model
context failure now produces an actionable 422 response. A real-model/API check
verified zero partial vectors for 800/120 and complete 29-chunk indexing for 400/80,
with lexical availability preserved. The current backend suite is 146 passing
tests, 93% coverage. These repairs do not change the frozen development scores.

These are AI self-assessment scores, not Atlas answer-quality metrics.

| Axis | Score / 5 | Evidence and improvement |
|---|---:|---|
| Accuracy | 3 | All references resolve, but relevance labels are incomplete and conflict proxies weak; improve the labels |
| Completeness | 3 | All 100 drafts and categories exist; independent review, representative conflict cases and holdout are missing |
| Clarity | 4 | Explicit AI attribution and unknown metrics; per-case notes are less specific than this global critique |
| Actionability | 4 | Reproducible generator, binding, real runner and tests; requires preinstalled local models and PostgreSQL |
| Conciseness | 3 | Repeated facts and generic per-category review notes add redundancy; improve diversity rather than case count |

Overall: **3.4/5**. Deliver as a development set with these limits. Higher-priority
user instructions authorize continuing without asking whether to redo the set;
the self-evaluation template's optional approval prompt is not used.

Highest-impact next improvements: replace weak conflict/conjunction questions,
establish exhaustive relevance labels and fact-grouped holdout, then validate
semantic correctness and abstention on a broader authorized corpus. User agreement
with this assessment has not been observed; the gaps are concrete and reviewable.
