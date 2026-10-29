import copy
import hashlib
import json
from pathlib import Path

import pytest

from atlas.ingestion import chunk_text
from atlas.schemas import Passage
from scripts.draft_evaluation import bind_case

FROZEN = Path(__file__).resolve().parents[1] / "evaluation/atlas-docs-v1"


def inputs():
    drafts = [
        json.loads(line)
        for line in (FROZEN / "drafts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads((FROZEN / "manifest.json").read_text(encoding="utf-8"))
    sources = {path: (FROZEN / "sources" / path).read_bytes() for path in manifest["sources"]}
    passages = {
        path: [
            Passage(
                id=f"fixture-{i}-{c.ordinal}",
                document_id=f"fixture-{i}",
                source_key=f"fixture-{i}",
                version=1,
                ordinal=c.ordinal,
                start=c.start,
                end=c.end,
                text=c.text,
            )
            for c in chunk_text(raw.decode("utf-8"), 400, 80)
        ]
        for i, (path, raw) in enumerate(sources.items())
    }
    return drafts, sources, passages


def test_all_100_cases_bind_to_real_chunk_locations_without_human_attestation():
    drafts, sources, passages = inputs()
    hashes = {
        p.id: hashlib.sha256(sources[path]).hexdigest()
        for path, chunks in passages.items()
        for p in chunks
    }
    for draft in drafts:
        case = bind_case(draft, sources, passages)
        assert case.human_reviewer is None and case.reviewed_at is None and case.synthetic
        assert case.answerable == bool(case.relevant_passages)
        assert all(hashes[key] == value for key, value in case.relevant_passages.items())
        for ref in draft["source_references"]:
            covered = [p for p in passages[ref["path"]] if p.id in case.relevant_passages]
            assert all(
                any(p.start <= position < p.end for p in covered)
                for position in range(ref["start"], ref["end"])
            )


@pytest.mark.parametrize("defect", ["hash", "quote", "span", "missing", "text"])
def test_inconsistent_source_or_index_is_rejected(defect):
    drafts, sources, passages = inputs()
    draft = copy.deepcopy(drafts[0])
    ref = draft["source_references"][0]
    if defect == "hash":
        ref["content_sha256"] = "0" * 64
    elif defect == "quote":
        ref["quote"] = "invented evidence"
    elif defect == "span":
        ref["start"] = -1
    elif defect == "missing":
        passages[ref["path"]] = []
    else:
        passages[ref["path"]][0].text = "modified evidence"
    with pytest.raises(ValueError):
        bind_case(draft, sources, passages)
