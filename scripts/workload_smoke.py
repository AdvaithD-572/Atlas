"""Small measured lexical workload; synthetic data, not an answer-quality benchmark."""

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx


def main() -> None:
    token = Path(".local/local.token").read_text().strip()
    latencies: list[float] = []
    failures = 0
    with httpx.Client(
        base_url="http://127.0.0.1:8080",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        trust_env=False,
    ) as client:
        response = client.put(
            f"/v1/documents/workload-{uuid4()}",
            headers={"Content-Type": "text/plain"},
            content=b"Synthetic Atlas workload document: connection timeout is five seconds.",
        )
        response.raise_for_status()
        identifier = response.json()["id"]
        try:
            for _ in range(100):
                started = time.perf_counter()
                try:
                    result = client.post("/v1/search", json={"question": "connection timeout"})
                    result.raise_for_status()
                    if not any(p["document_id"] == identifier for p in result.json()["passages"]):
                        failures += 1
                except (httpx.HTTPError, ValueError, KeyError):
                    failures += 1
                latencies.append((time.perf_counter() - started) * 1000)
        finally:
            deleted = client.delete(f"/v1/documents/{identifier}")
            deleted.raise_for_status()
    latencies.sort()
    report = {
        "observed_at": datetime.now(UTC).isoformat(),
        "scope": "100 serial loopback HTTP lexical queries against one synthetic document",
        "backend": "PostgreSQL via local Docker Desktop; API limited to one CPU",
        "concurrency": 1,
        "requests": 100,
        "failures": failures,
        "latency_ms": {
            f"p{p}": round(latencies[math.ceil(p / 100 * len(latencies)) - 1], 3)
            for p in (50, 95, 99)
        },
        "model_calls": 0,
        "compute_cost_usd": None,
        "limits": "Warm tiny corpus; not a scale claim, SLA, generation or quality benchmark.",
    }
    Path(".local/workload-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
