"""Verify local TLS with explicit certificate trust; never change system trust."""

import argparse
import json
import os
import socket
import ssl
import subprocess
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-certificate", action="store_true")
    args = parser.parse_args()
    directory = Path(".local/tls").resolve()
    certificate, key = directory / "server.crt", directory / "server.key"
    if args.init_certificate:
        if certificate.exists() or key.exists():
            parser.error("Certificates already exist; refusing to overwrite them")
        directory.mkdir(parents=True, exist_ok=True)
        generated = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                (f"{os.getuid()}:{os.getgid()}" if os.name == "posix" else "10001:10001"),
                "--mount",
                f"type=bind,src={directory},dst=/certs",
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
                "/certs/server.key",
                "-out",
                "/certs/server.crt",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if generated.returncode:
            raise RuntimeError("Local certificate generation failed; output withheld")
        print("Two-day local certificate created. No system trust store was changed.")
        return
    trusted = ssl.create_default_context(cafile=str(certificate))
    with httpx.Client(
        base_url="https://127.0.0.1:8443", verify=trusted, trust_env=False, timeout=10
    ) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/v1/documents").status_code == 401
        client.headers["Authorization"] = "Bearer " + Path(".local/local.token").read_text().strip()
        assert client.get("/v1/documents").status_code == 200
    for context, hostname in (
        (ssl.create_default_context(), "localhost"),
        (trusted, "wrong.invalid"),
    ):
        try:
            with socket.create_connection(("127.0.0.1", 8443), timeout=5) as stream:
                with context.wrap_socket(stream, server_hostname=hostname):
                    pass
        except ssl.SSLCertVerificationError:
            pass
        else:
            raise AssertionError("Untrusted certificate or wrong hostname was accepted")
    report = {
        "status": "passed",
        "checks": [
            "explicit CA trust",
            "readiness",
            "authentication",
            "untrusted CA rejected",
            "wrong hostname rejected",
        ],
        "global_trust_changed": False,
        "public_tls_deployment": False,
    }
    Path(".local/tls/results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
