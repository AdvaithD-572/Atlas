"""Verify provenance and honest review labels, not subjective benchmark quality."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.review_drafts import build_drafts, write_drafts

ROOT = Path(__file__).resolve().parents[1] / "evaluation/atlas-docs-v1/sources"


def test_all_drafts_resolve_real_source_spans_and_never_attest_human_review():
    cases, sources = build_drafts(ROOT)
    assert len(cases) == len({case["case_id"] for case in cases}) == 100
    assert Counter(case["category"] for case in cases) == {
        "direct": 25,
        "multi_document": 20,
        "unanswerable": 20,
        "conflicting_outdated": 15,
        "difficult": 20,
    }
    for case in cases:
        assert case["human_reviewer"] is None and case["reviewed_at"] is None
        assert case["ai_review"]["kind"] == "AI" and case["synthetic"] is True
        assert len(case["question"]) <= 512
        for reference in case["source_references"]:
            raw = sources[reference["path"]]
            assert reference["content_sha256"] == hashlib.sha256(raw).hexdigest()
            assert raw.decode("utf-8")[reference["start"] : reference["end"]] == reference["quote"]
        if case["category"] == "multi_document":
            assert len({ref["path"] for ref in case["source_references"]}) >= 2
        if case["category"] == "unanswerable":
            assert not case["source_references"] and not case["answerable"]


def test_snapshot_writer_is_reproducible_and_refuses_overwrite(tmp_path):
    output = tmp_path / "review"
    write_drafts(ROOT, output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["official"] is False
    assert (output / "drafts.jsonl").read_bytes() == (ROOT.parent / "drafts.jsonl").read_bytes()
    assert (
        hashlib.sha256((output / "drafts.jsonl").read_bytes()).hexdigest()
        == manifest["drafts_sha256"]
    )
    for path, digest in manifest["sources"].items():
        assert hashlib.sha256((output / "sources" / path).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        write_drafts(ROOT, output)


def test_changed_source_anchor_fails_before_writing_artifacts(tmp_path, monkeypatch):
    from scripts import review_drafts

    monkeypatch.setattr(
        review_drafts,
        "FACTS",
        [("ops", "This deliberately missing source sentence must fail.", "Question?")],
    )
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="evidence anchor"):
        write_drafts(ROOT, output)
    assert not output.exists()
