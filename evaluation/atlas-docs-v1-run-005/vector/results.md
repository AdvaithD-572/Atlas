# Atlas evaluation

Official benchmark: False
Dataset SHA256: f7945130a8bbc2b2f30662a077aa4cf05ad79a28db6c0ff470bbe16e85cbf099
Corpus SHA256: 75e0a28ad9ba71e68d71dbb08f20a95ffab46ddfaf42d7d1fee5342ea1f6a08f
Evaluator: atlas-eval-v1
Failures: 0/100

Metric values exclude nulls; counts disclose scored cases. Failed cases remain failures.
Citation scores measure passage-ID overlap, not semantic claim support.

```json
{
  "retrieval_recall_at_k": {
    "value": 0.60625,
    "count": 80
  },
  "retrieval_mrr": {
    "value": 0.526875,
    "count": 80
  },
  "citation_precision": {
    "value": null,
    "count": 0
  },
  "citation_recall": {
    "value": null,
    "count": 0
  },
  "answer_correctness": {
    "value": null,
    "count": 0
  },
  "faithfulness": {
    "value": null,
    "count": 0
  },
  "count": 100,
  "failures": 0,
  "abstention": {
    "tp": 0,
    "fp": 0,
    "tn": 0,
    "fn": 0,
    "precision": null,
    "recall": null,
    "accuracy": null,
    "count": 0
  },
  "latency_ms": {
    "p50": 314.971,
    "p95": 389.032,
    "p99": 395.553
  }
}
```
