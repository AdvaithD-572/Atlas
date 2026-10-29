"""Verify Compose HTTP/worker, recovery and TLS; restore HTTP after the TLS trial."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from atlas.__main__ import provision
from atlas.postgres import migrate
from atlas.worker import init_local

COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".local/postgres.env",
    "-f",
    "compose.yaml",
    "-f",
    "compose.app.yaml",
]


def run(arguments: list[str]) -> None:
    # Never stream Compose environment or connection diagnostics containing secrets.
    result = subprocess.run(arguments, capture_output=True, timeout=240, check=False)
    if result.returncode:
        raise RuntimeError("Package check failed; raw subprocess diagnostics withheld")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true", help="Fresh CI workspace only")
    args = parser.parse_args()
    if os.name == "posix":
        if os.getuid() == 0:
            parser.error("Run package checks as a non-root owner of the private credential files")
        os.environ["ATLAS_RUNTIME_UID"] = str(os.getuid())
        os.environ["ATLAS_RUNTIME_GID"] = str(os.getgid())
    if args.initialize:
        if Path(".local").exists():
            parser.error("Initialization requires a fresh workspace without .local")
        init_local()
        provision("local", Path(".local"))
        run(COMPOSE + ["up", "-d", "--wait", "--wait-timeout", "90", "postgres"])
        migrate(Path(".local/postgres.dsn").read_text().strip())
        run([sys.executable, "-m", "atlas.deployment", "init-runtime"])
    run(COMPOSE + ["config", "--quiet"])
    run(COMPOSE + ["up", "-d", "--wait", "--wait-timeout", "90", "api", "worker"])
    run([sys.executable, "-m", "scripts.container_smoke"])
    print("HTTP lifecycle and worker: passed", flush=True)
    run([sys.executable, "-m", "scripts.backup_restore_drill"])
    print("Disposable backup/restore: passed", flush=True)
    if not Path(".local/tls/server.crt").exists():
        run([sys.executable, "-m", "scripts.tls_smoke", "--init-certificate"])
    try:
        tls = COMPOSE + ["-f", "compose.tls.yaml"]
        run(tls + ["config", "--quiet"])
        run(tls + ["up", "-d", "--wait", "--wait-timeout", "90", "api"])
        run([sys.executable, "-m", "scripts.tls_smoke"])
        run(
            [
                sys.executable,
                "-m",
                "scripts.container_smoke",
                "--base-url",
                "https://127.0.0.1:8443",
                "--ca-file",
                ".local/tls/server.crt",
            ]
        )
        print("TLS trust, hostname rejection and lifecycle: passed", flush=True)
    finally:
        run(COMPOSE + ["up", "-d", "--wait", "--wait-timeout", "90", "api"])
    run([sys.executable, "-m", "scripts.container_smoke"])
    report = {
        "status": "passed",
        "checks": ["http_worker", "backup_restore", "tls_trust", "tls_lifecycle", "http_restored"],
        "public_deployment": False,
    }
    Path(".local/package-checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
