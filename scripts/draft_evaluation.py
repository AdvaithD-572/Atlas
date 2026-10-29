"""Bind frozen AI drafts to a disposable real API and compare retrieval baselines."""

import argparse
import hashlib
import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from atlas.evaluation import (
    DatasetCase,
    ExperimentConfig,
    corpus_digest,
    lexical_http_observer,
    load_dataset,
    run_experiment,
    write_report,
)
from atlas.schemas import Document, Passage
from scripts.browser_smoke_server import TEST_TOKEN, disposable_app


def bind_case(
    draft: dict[str, Any],
    sources: Mapping[str, bytes],
    passages: Mapping[str, list[Passage]],
) -> DatasetCase:
    """Select a deterministic minimal cover of each exact source span.

    These are canonical labels, not exhaustive semantic relevance judgments.
    Overlapping alternative passages can be useful but receive no metric credit.
    """
    relevant: dict[str, str] = {}
    for ref in draft["source_references"]:
        raw = sources[ref["path"]]
        text = raw.decode("utf-8")
        start, end = ref["start"], ref["end"]
        digest = hashlib.sha256(raw).hexdigest()
        if (
            digest != ref["content_sha256"]
            or not 0 <= start < end <= len(text)
            or text[start:end] != ref["quote"]
        ):
            raise ValueError("Draft source reference is inconsistent")
        candidates = passages[ref["path"]]
        for passage in candidates:
            if (
                not 0 <= passage.start < passage.end <= len(text)
                or text[passage.start : passage.end] != passage.text
            ):
                raise ValueError("Indexed passage does not match the frozen source")
        position = start
        while position < end:
            covering = [p for p in candidates if p.start <= position < p.end]
            if not covering:
                raise ValueError("Indexed passages do not cover the expected source span")
            chosen = max(covering, key=lambda p: (p.end, p.start, p.id))
            relevant[chosen.id] = digest
            position = chosen.end
    fields = {
        key: draft[key]
        for key in ("case_id", "category", "question", "answerable", "expected_facts")
    }
    return DatasetCase.model_validate(
        {
            **fields,
            "relevant_passages": relevant,
            "scoring_notes": draft["scoring_notes"]
            + " Canonical span-cover labels are not exhaustive relevance judgments.",
            "synthetic": True,
            "human_reviewer": None,
            "reviewed_at": None,
        }
    )


def run_comparison(
    frozen: Path, output: Path, client: httpx.Client, *, quality_study: bool = False
) -> None:
    manifest = json.loads((frozen / "manifest.json").read_text(encoding="utf-8"))
    raw_drafts = (frozen / "drafts.jsonl").read_bytes()
    if hashlib.sha256(raw_drafts).hexdigest() != manifest["drafts_sha256"]:
        raise ValueError("Draft snapshot hash mismatch")
    sources: dict[str, bytes] = {}
    for path, digest in manifest["sources"].items():
        target = (frozen / "sources" / path).resolve()
        if not target.is_relative_to((frozen / "sources").resolve()):
            raise ValueError("Source path leaves the frozen snapshot")
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Source snapshot hash mismatch")
        sources[path] = raw
    drafts = [json.loads(line) for line in raw_drafts.decode("utf-8").splitlines()]
    output.mkdir(parents=True, exist_ok=False)
    passages: dict[str, list[Passage]] = {}
    corpus: dict[str, str] = {}
    documents: list[Document] = []
    identities: set[tuple[str, str]] = set()
    for index, (path, raw) in enumerate(sources.items()):
        response = client.put(
            f"/v1/documents/draft-source-{index}",
            content=raw,
            headers={"Content-Type": "text/markdown"},
        )
        response.raise_for_status()
        document = Document.model_validate(response.json())
        if document.content_hash != hashlib.sha256(raw).hexdigest():
            raise ValueError("Uploaded source hash mismatch")
        documents.append(document)
        response = client.get(f"/v1/documents/{document.id}/chunks", params={"limit": 100})
        response.raise_for_status()
        page = response.json()
        if page["total"] != len(page["items"]):
            raise ValueError("Development source exceeds this runner's 100-chunk bound")
        passages[path] = [Passage.model_validate(item) for item in page["items"]]
        corpus.update({p.id: document.content_hash for p in passages[path]})
        response = client.post(f"/v1/documents/{document.id}/vector-index")
        response.raise_for_status()
        result = response.json()
        identities.add((result["embedding_model"], result["model_digest"]))
        print(json.dumps({"indexed_source": index + 1, "chunks": len(passages[path])}), flush=True)
    if len(identities) != 1:
        raise ValueError("Embedding identity changed during corpus setup")
    model_id, model_digest = identities.pop()
    bound = [bind_case(draft, sources, passages) for draft in drafts]
    payload = ("\n".join(case.model_dump_json() for case in bound) + "\n").encode("utf-8")
    dataset_path = output / "bound-dataset.jsonl"
    dataset_path.write_bytes(payload)
    dataset = load_dataset(
        dataset_path,
        expected_dataset_hash=hashlib.sha256(payload).hexdigest(),
        expected_corpus_hash=corpus_digest(corpus),
        corpus=corpus,
    )
    (output / "binding.json").write_text(
        json.dumps(
            {
                "drafts_sha256": manifest["drafts_sha256"],
                "corpus": corpus,
                "documents": [d.model_dump() for d in documents],
                "protocol": "Serial localhost HTTP; isolated test limit 1000 requests/minute",
                "labels": "Canonical minimal source-span covers; not exhaustive relevance",
                "official": False,
                "holdout": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    versions = {
        "lexical": "postgres-simple-overlap-v1",
        "vector": "cosine-exact-v1",
        "hybrid": "rrf60-depth20-v1",
    }
    for mode, version in versions.items():
        config = ExperimentConfig.model_validate(
            {
                "mode": mode,
                "retrieval_version": version,
                "model_id": None if mode == "lexical" else model_id,
                "model_digest": None if mode == "lexical" else model_digest,
                "experiment_id": f"draft-{mode}",
                "corpus_version": "atlas-docs-v1",
                "chunking_version": "utf8-literal-v1-400-80",
            }
        )
        result = run_experiment(dataset, config, lexical_http_observer(client, {}))
        # Check all source versions again before publishing this run.
        for document in documents:
            response = client.get(f"/v1/documents/{document.id}")
            response.raise_for_status()
            if response.json() != document.model_dump():
                raise ValueError("Corpus changed during the development comparison")
        write_report(result, output / mode)
        print(json.dumps({"mode": mode, "summary": result["summary"]}), flush=True)
    if quality_study:
        from scripts.quality_study import run_study

        run_study(client, dataset, output / "quality-study", model_id, model_digest)
        verification = output / "quality-study" / "verification.json"
        try:
            for document in documents:
                response = client.get(f"/v1/documents/{document.id}")
                response.raise_for_status()
                if response.json() != document.model_dump():
                    raise ValueError("Corpus changed during quality study")
        except Exception:
            verification.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
            raise
        verification.write_text(
            json.dumps({"status": "passed", "documents_checked": len(documents)}), encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, default=Path("evaluation/atlas-docs-v1"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quality-study", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; existing evidence is never overwritten")
    # This higher quota is confined to a new disposable schema and public fixture
    # identity. Application defaults and the user's running service stay unchanged.
    with disposable_app(
        postgres=True, requests_per_minute=1000, chunk_size=400, chunk_overlap=80
    ) as app:
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=8001, access_log=False, log_level="error")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError("Disposable API could not start")
                time.sleep(0.1)
            if not server.started:
                raise RuntimeError("Disposable API startup timed out")
            with httpx.Client(
                base_url="http://127.0.0.1:8001",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                timeout=130,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                run_comparison(args.frozen, args.output, client, quality_study=args.quality_study)
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            if thread.is_alive():
                raise RuntimeError("Disposable server did not shut down cleanly")


if __name__ == "__main__":
    main()
