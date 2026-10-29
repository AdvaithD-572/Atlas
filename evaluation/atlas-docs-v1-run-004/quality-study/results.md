# Automated development study

Not human calibrated; not an official benchmark.

```json
{
  "baseline_recall": {
    "value": 0.65625,
    "count": 80
  },
  "baseline_mrr": {
    "value": 0.5377083333333333,
    "count": 80
  },
  "reranked_recall": {
    "value": 0.6408450704225352,
    "count": 71
  },
  "reranked_mrr": {
    "value": 0.5197183098591549,
    "count": 71
  },
  "abstention_correct": {
    "value": 0.3382352941176471,
    "count": 68
  },
  "model_fact_coverage": {
    "value": 0.90625,
    "count": 48
  },
  "model_claim_relevance": {
    "value": 1.0,
    "count": 3
  },
  "model_status_appropriate": {
    "value": 0.6470588235294118,
    "count": 68
  },
  "attempted": 100,
  "paired_baseline_recall": {
    "value": 0.6408450704225352,
    "count": 71
  },
  "paired_baseline_mrr": {
    "value": 0.513849765258216,
    "count": 71
  },
  "reranked_recall_failures_as_zero": {
    "value": 0.56875,
    "count": 80
  },
  "reranked_mrr_failures_as_zero": {
    "value": 0.46125,
    "count": 80
  },
  "rerank_failed": 11,
  "answer_failed": 32,
  "judge_failed": 32,
  "reranking_p95_ms": 2529.5427998062223
}
```

Development retention gate passed: False. Application reranking stays disabled.
