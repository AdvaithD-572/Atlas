# Automated development study

Not human calibrated; not an official benchmark.

```json
{
  "baseline_recall": {
    "value": 0.64375,
    "count": 80
  },
  "baseline_mrr": {
    "value": 0.5410416666666666,
    "count": 80
  },
  "reranked_recall": {
    "value": 0.6343283582089553,
    "count": 67
  },
  "reranked_mrr": {
    "value": 0.5808457711442786,
    "count": 67
  },
  "abstention_correct": {
    "value": 0.3333333333333333,
    "count": 66
  },
  "model_fact_coverage": {
    "value": null,
    "count": 0
  },
  "model_claim_relevance": {
    "value": null,
    "count": 0
  },
  "model_status_appropriate": {
    "value": null,
    "count": 0
  },
  "attempted": 100,
  "rerank_failed": 15,
  "answer_failed": 34,
  "judge_failed": 100,
  "reranking_p95_ms": 1939.4444001372904
}
```

Development retention gate passed: False. Application reranking stays disabled.
