# Automated development study

Not human calibrated; not an official benchmark.

```json
{
  "baseline_recall": {
    "value": 0.6375,
    "count": 80
  },
  "baseline_mrr": {
    "value": 0.5341666666666667,
    "count": 80
  },
  "reranked_recall": {
    "value": 0.6180555555555556,
    "count": 72
  },
  "reranked_mrr": {
    "value": 0.5398148148148149,
    "count": 72
  },
  "abstention_correct": {
    "value": 0.3384615384615385,
    "count": 65
  },
  "model_fact_coverage": {
    "value": 0.9184782608695652,
    "count": 46
  },
  "model_claim_relevance": {
    "value": 1.0,
    "count": 3
  },
  "model_status_appropriate": {
    "value": 0.7076923076923077,
    "count": 65
  },
  "attempted": 100,
  "paired_baseline_recall": {
    "value": 0.6180555555555556,
    "count": 72
  },
  "paired_baseline_mrr": {
    "value": 0.5259259259259259,
    "count": 72
  },
  "reranked_recall_failures_as_zero": {
    "value": 0.55625,
    "count": 80
  },
  "reranked_mrr_failures_as_zero": {
    "value": 0.48583333333333334,
    "count": 80
  },
  "rerank_attempted": 100,
  "rerank_skipped": 0,
  "rerank_failed": 8,
  "answer_attempted": 100,
  "answer_skipped": 0,
  "answer_failed": 35,
  "judge_attempted": 65,
  "judge_skipped": 35,
  "judge_failed": 0,
  "judge_contradictions": 43,
  "abstention_correct_failures_as_zero": {
    "value": 0.22,
    "count": 100
  },
  "answer_p95_ms": 6248.126900056377,
  "judge_p95_ms": 4754.09090006724,
  "reranking_p95_ms": 4945.094799855724
}
```

Development retention gate passed: False. Application reranking stays disabled.
