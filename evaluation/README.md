# Development evaluation artifacts

These are AI-authored, AI-critiqued development cases and actual local retrieval
results. They are **not human-reviewed or official benchmark results**.

- `atlas-docs-v1/`: immutable source snapshots, exact-span draft labels and hashes.
  Historical claims inside snapshots describe their recorded dates; current status
  is in the root BUILD_STATE.md. Do not edit snapshots to follow current docs.
- `atlas-docs-v1-run-001/failure.json`: first indexing attempt failed before scoring.
- `atlas-docs-v1-run-002/`: actual 100-case lexical/vector/hybrid reports, the bound
  dataset and source-to-passage mapping. All modes used identical frozen inputs.

See [the review](../docs/engineering/evaluation-review.md) for findings and measured
results, and [the protocol](../docs/evaluation.md) for reproduction. Source snapshots
contain project documentation only. No tokens, provider responses containing answer
text, or private user documents are included. Passage IDs refer to a disposable
database that was removed after the experiment; the source text and binding metadata
are preserved for audit. A new run creates fresh IDs and hashes.
