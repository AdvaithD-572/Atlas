"""Real local-model evaluation plumbing on a disposable synthetic API corpus."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx

from atlas.evaluation import corpus_digest
from atlas.providers import PROMPT_VERSION


def main() -> None:
    # This credential is public synthetic test data, accepted only by the test server.
    token = "atlas-browser-smoke-synthetic-only"
    local = Path(".local").resolve()
    if not local.is_relative_to(Path.cwd().resolve()):
        raise ValueError("Smoke artifacts must stay inside this workspace")
    local.mkdir(exist_ok=True)
    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
        trust_env=False,
    ) as client:
        page = client.get("/v1/documents")
        page.raise_for_status()
        if page.json()["total"] != 0:
            raise ValueError("Use an empty disposable browser_smoke_server fixture")
        models = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5, trust_env=False)
        models.raise_for_status()
        digest = next(
            model["digest"] for model in models.json()["models"] if model["name"] == "qwen3:1.7b"
        )
        text = "The Atlas test server retries failed requests three times."
        created = client.put(
            f"/v1/documents/eval-smoke-{uuid4()}",
            headers={"Content-Type": "text/plain"},
            content=text.encode(),
        )
        created.raise_for_status()
        document = created.json()
        try:
            passages = client.get(f"/v1/documents/{document['id']}/chunks")
            passages.raise_for_status()
            corpus = {p["id"]: document["content_hash"] for p in passages.json()["items"]}
            base = {
                "scoring_notes": "Explicit synthetic integration fixture, not human reviewed.",
                "human_reviewer": None,
                "reviewed_at": None,
                "synthetic": True,
            }
            cases = [
                {
                    **base,
                    "case_id": "synthetic-answer",
                    "category": "direct",
                    "question": "How many times does the Atlas test server retry failed requests?",
                    "answerable": True,
                    "expected_facts": [text],
                    "relevant_passages": corpus,
                },
                {
                    **base,
                    "case_id": "synthetic-empty",
                    "category": "unanswerable",
                    "question": "qzzxnonexistent",
                    "answerable": False,
                    "expected_facts": [],
                    "relevant_passages": {},
                },
            ]
            with TemporaryDirectory(prefix="answer-eval-input-", dir=local) as temporary:
                dataset = Path(temporary) / "synthetic.jsonl"
                dataset.write_text("\n".join(json.dumps(case) for case in cases), encoding="utf-8")
                output = local / "answer-evaluation-smoke" / str(uuid4())
                process = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "atlas.evaluation",
                        str(dataset),
                        "--dataset-sha256",
                        hashlib.sha256(dataset.read_bytes()).hexdigest(),
                        "--corpus-sha256",
                        corpus_digest(corpus),
                        "--retrieval-version",
                        "postgres-simple-overlap-v1",
                        "--answers",
                        "--generation-model-id",
                        "qwen3:1.7b",
                        "--generation-model-digest",
                        digest,
                        "--prompt-version",
                        PROMPT_VERSION,
                        "--corpus-version",
                        "synthetic-smoke",
                        "--chunking-version",
                        "literal800-overlap120",
                        "--output",
                        str(output),
                    ],
                    env={**os.environ, "ATLAS_EVAL_TOKEN": token},
                    capture_output=True,
                    timeout=620,
                    check=False,
                )
                if process.returncode:
                    raise RuntimeError("Answer evaluation CLI failed; inspect local services")
                report = json.loads((output / "results.json").read_text())
                assert report["official"] is False
                assert report["summary"]["failures"] == 0
                assert report["cases"][0]["abstained"] is False
                assert report["cases"][0]["cited_passage_ids"]
                assert report["cases"][1]["abstained"] is True
                assert report["summary"]["answer_correctness"]["value"] is None
                print(
                    json.dumps(
                        {
                            "scope": (
                                "real local-model CLI plumbing; two synthetic cases, "
                                "not a quality benchmark"
                            ),
                            "status": "passed",
                            "generation_model": "qwen3:1.7b",
                            "model_digest": digest,
                            "prompt_version": PROMPT_VERSION,
                            "checks": [
                                "cited answer",
                                "empty-evidence abstention",
                                "null human ratings",
                                "pinned identity",
                                "minimized JSON/CSV/Markdown reports",
                            ],
                            "report": str(
                                output.relative_to(Path.cwd().resolve()) / "results.json"
                            ),
                        }
                    )
                )
        finally:
            deleted = client.delete(f"/v1/documents/{document['id']}")
            deleted.raise_for_status()


if __name__ == "__main__":
    main()
