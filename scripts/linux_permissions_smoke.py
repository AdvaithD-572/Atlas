"""Verify private Linux file ownership and HTTPS lifecycle in disposable containers."""

import json
import ssl
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

from scripts.package_checks import run


def main() -> None:
    identity = "atlas-permissions-" + uuid4().hex
    volume, helper, api = identity + "-data", identity + "-copy", identity + "-api"
    directory = Path(".local/linux-permissions") / identity
    directory.mkdir(parents=True)
    certificate = directory / "server.crt"
    try:
        run(["docker", "volume", "create", volume])
        mount = f"type=volume,src={volume},dst=/run/atlas"
        run(
            [
                "docker",
                "create",
                "--name",
                helper,
                "--user",
                "0:0",
                "--network",
                "none",
                "--mount",
                mount,
                "--entrypoint",
                "python",
                "atlas-app:local",
                "-c",
                "import os; from pathlib import Path; p=Path('/run/atlas'); "
                "os.chown(p,1001,1001); p.chmod(0o700); "
                "[(os.chown(f,1001,1001),f.chmod(0o600)) for f in p.iterdir()]",
            ]
        )
        for source, target in (
            (".local/runtime-container.dsn", "runtime.dsn"),
            (".local/credentials.json", "credentials.json"),
        ):
            run(["docker", "cp", source, f"{helper}:/run/atlas/{target}"])
        run(["docker", "start", "-a", helper])
        denied = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "10001:10001",
                "--network",
                "none",
                "--mount",
                mount + ",readonly",
                "--entrypoint",
                "python",
                "atlas-app:local",
                "-c",
                "open('/run/atlas/runtime.dsn').close()",
            ],
            capture_output=True,
            timeout=30,
        )
        assert denied.returncode != 0, "Mismatched UID must not read private credentials"
        run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "1001:1001",
                "--network",
                "none",
                "--mount",
                mount,
                "--entrypoint",
                "openssl",
                "atlas-app:local",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-noenc",
                "-days",
                "2",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=IP:127.0.0.1,DNS:localhost",
                "-keyout",
                "/run/atlas/server.key",
                "-out",
                "/run/atlas/server.crt",
            ]
        )
        run(["docker", "cp", f"{helper}:/run/atlas/server.crt", str(certificate)])
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                api,
                "--user",
                "1001:1001",
                "--network",
                "atlas-local_default",
                "--read-only",
                "--tmpfs",
                "/tmp:size=32m",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--pids-limit",
                "64",
                "--mount",
                mount + ",readonly",
                "-p",
                "127.0.0.1:8444:8443",
                "--env",
                "ATLAS_POSTGRES_DSN_PATH=/run/atlas/runtime.dsn",
                "--env",
                "ATLAS_CREDENTIALS_PATH=/run/atlas/credentials.json",
                "--health-cmd",
                'python -c "import ssl,urllib.request; '
                "urllib.request.urlopen('https://127.0.0.1:8443/health/ready', "
                "context=ssl.create_default_context(cafile='/run/atlas/server.crt'),timeout=7)\"",
                "atlas-app:local",
                "python",
                "-m",
                "uvicorn",
                "atlas.main:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                "8443",
                "--no-access-log",
                "--ssl-certfile",
                "/run/atlas/server.crt",
                "--ssl-keyfile",
                "/run/atlas/server.key",
            ]
        )
        with httpx.Client(
            base_url="https://127.0.0.1:8444",
            timeout=5,
            trust_env=False,
            verify=ssl.create_default_context(cafile=str(certificate)),
        ) as client:
            for _ in range(30):
                try:
                    if client.get("/health/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Linux private-file runtime did not become ready")
        run(
            [
                sys.executable,
                "-m",
                "scripts.container_smoke",
                "--base-url",
                "https://127.0.0.1:8444",
                "--ca-file",
                str(certificate),
            ]
        )
        report = {
            "status": "passed",
            "runtime_uid": 1001,
            "denied_uid": 10001,
            "checks": [
                "private Linux file ownership",
                "non-root certificate generation",
                "verified HTTPS lifecycle with restricted database role",
            ],
        }
        (directory / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        # Names are generated by this invocation; never target retained application resources.
        for name in (api, helper):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True, timeout=30)


if __name__ == "__main__":
    main()
