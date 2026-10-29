"""Verify the running loopback Compose app/worker with a unique synthetic document."""

import argparse
import json
import ssl
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--ca-file", type=Path)
    args = parser.parse_args()
    verify = ssl.create_default_context(cafile=str(args.ca_file)) if args.ca_file else True
    token = Path(".local/local.token").read_text().strip()
    document_id = None
    with httpx.Client(base_url=args.base_url, verify=verify, timeout=10, trust_env=False) as client:
        assert client.get("/health/ready").status_code == 200
        root = client.get("/")
        assert root.status_code == 200 and "Atlas" in root.text
        assert "default-src 'self'" in root.headers["content-security-policy"]
        assert client.get("/v1/documents").status_code == 401
        client.headers["Authorization"] = f"Bearer {token}"
        key = f"package-smoke-{uuid4()}"
        job = client.post(
            f"/v1/ingestions/{key}",
            headers={"Content-Type": "text/plain"},
            content=b"Explicit synthetic packaging smoke: Atlas retains exact source spans.",
        )
        assert job.status_code == 202
        job_id = job.json()["id"]
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                status = client.get(f"/v1/jobs/{job_id}").json()
                assert status["status"] not in {"failed", "cancelled"}
                if status["status"] == "succeeded":
                    document_id = status["document_id"]
                    break
                time.sleep(0.2)
            assert document_id is not None, "Real worker did not finish within the smoke deadline."
            document = client.get(f"/v1/documents/{document_id}")
            assert document.status_code == 200
            search = client.post("/v1/search", json={"question": "packaging smoke"})
            assert search.status_code == 200
            passage = next(p for p in search.json()["passages"] if p["document_id"] == document_id)
            assert client.get(f"/v1/citations/{passage['id']}").json() == passage
        finally:
            if document_id:
                assert client.delete(f"/v1/documents/{document_id}").status_code == 204
        assert client.get(f"/v1/jobs/{job_id}").status_code == 404
        print(
            json.dumps(
                {
                    "scope": "real local container API, PostgreSQL and continuous worker",
                    "checks": [
                        "static frontend and CSP",
                        "readiness",
                        "authentication",
                        "queued ingestion",
                        "real worker completion",
                        "lexical search",
                        "source citation",
                        "document and job deletion",
                    ],
                    "status": "passed",
                }
            )
        )


if __name__ == "__main__":
    main()
