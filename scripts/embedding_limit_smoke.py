"""Real local-model context rejection and recovery using frozen project documentation."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.browser_smoke_server import TEST_TOKEN, disposable_app


def main() -> None:
    source = Path("evaluation/atlas-docs-v1/sources/docs/operations.md").read_bytes()
    observations = []
    for size, overlap in ((800, 120), (400, 80)):
        with (
            disposable_app(postgres=True, chunk_size=size, chunk_overlap=overlap) as app,
            TestClient(app, headers={"Authorization": f"Bearer {TEST_TOKEN}"}) as client,
        ):
            uploaded = client.put(
                "/v1/documents/context-probe",
                headers={"Content-Type": "text/markdown"},
                content=source,
            )
            uploaded.raise_for_status()
            document = uploaded.json()
            indexed = client.post(f"/v1/documents/{document['id']}/vector-index")
            if size == 800:
                assert indexed.status_code == 422
                error = indexed.json()["error"]
                assert error["code"] == "embedding_context_exceeded"
                assert "smaller document chunks" in error["message"]
            else:
                indexed.raise_for_status()
                assert indexed.json()["chunk_count"] == document["chunk_count"]
            lexical = client.post("/v1/search", json={"question": "documents"})
            lexical.raise_for_status()
            assert lexical.json()["passages"]
            vector = client.post("/v1/search?mode=vector", json={"question": "documents"})
            vector.raise_for_status()
            result = vector.json()
            expected = 0 if size == 800 else document["chunk_count"]
            assert result["indexed_chunks"] == expected
            assert result["unindexed_chunks"] == document["chunk_count"] - expected
            observations.append(
                {
                    "chunk_size": size,
                    "overlap": overlap,
                    "index_status": indexed.status_code,
                    "error_code": "embedding_context_exceeded" if size == 800 else None,
                    "indexed_chunks": result["indexed_chunks"],
                    "unindexed_chunks": result["unindexed_chunks"],
                    "embedding_model": result["embedding_model"],
                    "model_digest": result["model_digest"],
                    "lexical_still_available": True,
                }
            )
    report = {
        "scope": "Real Ollama/PostgreSQL with in-process API transport; not quality scoring",
        "status": "passed",
        "observations": observations,
    }
    Path(".local/embedding-limit-smoke.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
