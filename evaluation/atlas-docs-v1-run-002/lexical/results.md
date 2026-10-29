# Atlas evaluation

Official benchmark: False
Dataset SHA256: 5cd963ee3af16835ed38b17b3e005f733a42efea60c596c53f0fd578f5a35f11
Corpus SHA256: d2cce2b7518ec1bae1fc92f9eac1d89aa69f5c53c145c0a98279e4a0bd79e812
Evaluator: atlas-eval-v1
Failures: 0/100

Metric values exclude nulls; counts disclose scored cases. Failed cases remain failures.
Citation scores measure passage-ID overlap, not semantic claim support.

```json
{
  "retrieval_recall_at_k": {
    "value": 0.46875,
    "count": 80
  },
  "retrieval_mrr": {
    "value": 0.42312500000000003,
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
    "p50": 44.604,
    "p95": 61.442,
    "p99": 72.939
  }
}
```
