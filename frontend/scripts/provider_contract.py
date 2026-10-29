"""Emit real API responses from an isolated synthetic test corpus, never user data."""

import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402

from atlas.config import Settings  # noqa: E402
from atlas.database import migrate  # noqa: E402
from atlas.main import create_app  # noqa: E402
from atlas.providers import OllamaProvider, PROMPT_VERSION  # noqa: E402
from atlas.evaluation import (  # noqa: E402
    ExperimentConfig, corpus_digest, lexical_http_observer, load_dataset, run_experiment,
)


def model_transport(request: httpx.Request) -> httpx.Response:
    """Explicit fake model response; tests serialization, never real inference."""
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "qwen3:1.7b", "digest": "a" * 64}]})
    if request.url.path == "/api/chat":
        payload = json.loads(request.content)
        source = json.loads(payload["messages"][-1]["content"])["evidence"][0]
        generated = {"status": "answered", "claims": [{"text": source["text"],
            "citation_ids": [source["id"]], "quotes": [source["text"]]}]}
        return httpx.Response(200, json={"message": {"content": json.dumps(generated)}})
    raise AssertionError("Unexpected model contract request")


def main() -> None:
    with TemporaryDirectory(prefix="atlas-ui-contract-") as directory:
        # Deliberately non-secret credential valid only in this temporary test app.
        token = "isolated-ui-contract-fixture-token"
        settings = Settings(
            database_path=Path(directory) / "contract.db",
            token_hashes={"contract_test": hashlib.sha256(token.encode()).hexdigest()},
            generation_enabled=True,
        )
        migrate(settings.database_path)
        with TestClient(create_app(settings)) as client:
            client.app.state.provider = OllamaProvider(transport=httpx.MockTransport(model_transport))
            client.headers["Authorization"] = f"Bearer {token}"
            created = client.put(
                "/v1/documents/contract.md",
                content="# Contract\nAtlas preserves exact source locations. Unicode: 😀.",
                headers={"Content-Type": "text/markdown"},
            )
            assert created.status_code == 201
            document = created.json()
            chunks = client.get(f"/v1/documents/{document['id']}/chunks")
            assert chunks.status_code == 200
            chunk = chunks.json()["items"][0]
            citation = client.get(f"/v1/citations/{chunk['id']}")
            assert citation.status_code == 200
            search = client.post("/v1/search", json={"question": "source locations", "limit": 5})
            assert search.status_code == 200
            empty = client.post("/v1/search", json={"question": "qzzxnonexistent", "limit": 5})
            assert empty.status_code == 200
            listed = client.get("/v1/documents")
            assert listed.status_code == 200
            capabilities = client.get("/v1/capabilities")
            assert capabilities.status_code == 200
            answer = client.post("/v1/answers", json={"question": "source locations", "limit": 5})
            assert answer.status_code == 200
            abstention = client.post("/v1/answers", json={"question": "qzzxnonexistent", "limit": 5})
            assert abstention.status_code == 200
            dataset_path = Path(directory) / "synthetic.jsonl"
            corpus = {chunk["id"]: document["content_hash"]}
            dataset_path.write_text(json.dumps({
                "case_id": "synthetic-contract", "category": "direct",
                "question": "source locations", "answerable": True,
                "expected_facts": ["Atlas preserves exact source locations."],
                "relevant_passages": corpus, "scoring_notes": "Synthetic serialization fixture.",
                "human_reviewer": None, "reviewed_at": None, "synthetic": True,
            }), encoding="utf-8")
            frozen = load_dataset(
                dataset_path,
                expected_dataset_hash=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                expected_corpus_hash=corpus_digest(corpus), corpus=corpus,
            )
            evaluation = run_experiment(frozen, ExperimentConfig(),
                lexical_http_observer(client, client.headers))
            evaluation_answers = run_experiment(frozen, ExperimentConfig(
                generate_answers=True, generation_model_id="qwen3:1.7b",
                generation_model_digest="a" * 64, prompt_version=PROMPT_VERSION,
            ), lexical_http_observer(client, client.headers))
            html_response = client.put('/v1/documents/source.html',
                content='<h1>Rotation</h1><p>Rotate tokens.</p><script>untrusted()</script>',
                headers={'Content-Type': 'text/html'})
            assert html_response.status_code == 201
            html_document = html_response.json()
            html_passage = client.get(f"/v1/documents/{html_document['id']}/chunks").json()['items'][0]
            print(json.dumps({
                "document": document, "documents": listed.json(), "chunks": chunks.json(),
                "citation": citation.json(), "search": search.json(), "empty_search": empty.json(),
                "capabilities": capabilities.json(), "answer": answer.json(), "abstention": abstention.json(),
                "evaluation": evaluation,
                "evaluation_answers": evaluation_answers,
                "html_document": html_document, "html_passage": html_passage,
            }))


if __name__ == "__main__":
    main()
