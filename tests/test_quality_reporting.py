from scripts.quality_study import summarize


def test_quality_report_keeps_failures_in_overall_denominator_and_splits_skips():
    shared = {
        "answerable": True,
        "baseline_recall": 1.0,
        "baseline_mrr": 1.0,
        "rerank_attempted": True,
        "answer_attempted": True,
        "judge_attempted": False,
        "rerank_failed": True,
        "answer_failed": True,
        "judge_failed": True,
        "reranking_ms": 50,
        "answer_ms": 60,
    }
    success = shared | {
        "reranked_recall": 0.5,
        "reranked_mrr": 0.5,
        "rerank_failed": False,
        "answer_failed": False,
        "judge_attempted": True,
        "judge_failed": False,
        "judge_ms": 100,
        "abstention_correct": 1.0,
        "judge_contradiction": True,
    }
    summary, gate = summarize([shared, success])
    assert summary["reranked_recall"] == {"value": 0.5, "count": 1}
    assert summary["paired_baseline_recall"] == {"value": 1.0, "count": 1}
    assert summary["reranked_recall_failures_as_zero"] == {"value": 0.25, "count": 2}
    assert summary["abstention_correct_failures_as_zero"] == {"value": 0.5, "count": 2}
    assert summary["judge_attempted"] == 1 and summary["judge_skipped"] == 1
    assert summary["judge_failed"] == 0 and summary["judge_contradictions"] == 1
    assert summary["answer_p95_ms"] == 60 and summary["judge_p95_ms"] == 100
    assert not gate
    candidate_failure = shared | {
        "baseline_recall": None,
        "baseline_mrr": None,
        "rerank_attempted": False,
        "answer_attempted": False,
    }
    otherwise_good = success | {
        "baseline_recall": 0,
        "baseline_mrr": 0,
        "reranked_recall": 1,
        "reranked_mrr": 1,
    }
    summary, gate = summarize([candidate_failure, otherwise_good])
    assert summary["rerank_skipped"] == 1 and not gate
    assert summary["reranked_recall_failures_as_zero"] == {"value": 0.5, "count": 2}
