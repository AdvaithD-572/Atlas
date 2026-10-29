"""Start a real loopback server, verify the lifecycle, and always stop it."""

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main() -> None:
    token = Path(".local/local.token").read_text(encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryFile() as logs:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "atlas.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
                "--limit-concurrency",
                "16",
                "--timeout-keep-alive",
                "5",
            ],
            stdout=logs,
            stderr=logs,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        if client.get("/health/ready").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline or server.poll() is not None:
                        raise RuntimeError("Loopback API did not become ready.")
                    time.sleep(0.2)
                assert client.get("/v1/documents").status_code == 401
                client.headers["Authorization"] = f"Bearer {token}"
                key = f"smoke-{uuid4()}"
                text = "Explicit synthetic smoke document. Atlas preserves exact source spans."
                result = client.put(
                    f"/v1/documents/{key}",
                    content=text.encode(),
                    headers={"Content-Type": "text/plain"},
                )
                assert result.status_code == 201
                doc = result.json()
                try:
                    chunks = client.get(f"/v1/documents/{doc['id']}/chunks").json()["items"]
                    passage = client.get(f"/v1/citations/{chunks[0]['id']}").json()
                    assert passage["text"] == text[passage["start"] : passage["end"]]
                    search = client.post("/v1/search", json={"question": "exact source spans"})
                    assert search.status_code == 200
                    assert any(
                        item["document_id"] == doc["id"] for item in search.json()["passages"]
                    )
                finally:
                    assert client.delete(f"/v1/documents/{doc['id']}").status_code == 204
                assert client.get(f"/v1/citations/{chunks[0]['id']}").status_code == 404
                print(
                    json.dumps(
                        {
                            "smoke": "passed",
                            "transport": "real loopback HTTP",
                            "checks": ["ready", "auth", "upload", "search", "source", "delete"],
                        }
                    )
                )
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
