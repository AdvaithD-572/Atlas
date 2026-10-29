# Atlas evaluation

Official benchmark: False
Dataset SHA256: 7e0fc1dc099d318633f6adba51a4dc8b5b656624a27a5586f3c467efaa901999
Corpus SHA256: 76900a7928c9f2f1fcd7d046eeb1b042ee11ff7ba3f66393d814a0303a19c02f
Evaluator: atlas-eval-v1
Failures: 0/100

Metric values exclude nulls; counts disclose scored cases. Failed cases remain failures.
Citation scores measure passage-ID overlap, not semantic claim support.

```json
{
  "retrieval_recall_at_k": {
    "value": 0.64375,
    "count": 80
  },
  "retrieval_mrr": {
    "value": 0.5410416666666666,
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
    "p50": 360.293,
    "p95": 435.181,
    "p99": 478.791
  }
}
```
