# Atlas evaluation

Official benchmark: False
Dataset SHA256: 576b483d19333a6af28cb49bca72a1f0b5f63ff3d5ab885166edaf00c1e4f46a
Corpus SHA256: 4ecf25e3de9b3ea87c67116bf32dd3c1bc814095dbefa56c641687d312ea9f05
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
    "p50": 41.861,
    "p95": 55.339,
    "p99": 64.341
  }
}
```
