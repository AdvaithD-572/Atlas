import argparse
import hashlib
import json
import os
import re
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from atlas.database import migrate


@contextmanager
def credential_lock(directory: Path) -> Iterator[None]:
    lock = directory / ".credentials.lock"
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError("Credential provisioning is busy. Retry later.") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink()


def provision(owner: str, directory: Path) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", owner):
        raise ValueError("Owner must be a short alphanumeric identifier.")
    directory.mkdir(parents=True, exist_ok=True)
    with credential_lock(directory):
        _provision_locked(owner, directory)


def _provision_locked(owner: str, directory: Path) -> None:
    credentials_path = directory / "credentials.json"
    credentials = json.loads(credentials_path.read_text()) if credentials_path.exists() else {}
    if owner in credentials:
        raise ValueError("Owner already exists. Explicitly revoke before rotating credentials.")
    token = secrets.token_urlsafe(32)
    token_path = directory / f"{owner}.token"
    # Exclusive creation preserves existing user credentials. Never echo the token.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    temporary = directory / f"credentials-{secrets.token_hex(8)}.tmp"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token)
        credentials[owner] = hashlib.sha256(token.encode()).hexdigest()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(credentials, handle)
        temporary.replace(credentials_path)
    except BaseException:
        # Roll back only this call's newly created files; preserve previous credentials.
        token_path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise
    print(f"Credential saved locally in {token_path}. Keep this file private.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas local administration")
    sub = parser.add_subparsers(dest="command", required=True)
    migration = sub.add_parser("migrate")
    migration.add_argument("--database", type=Path, default=Path(".local/atlas.db"))
    credentials = sub.add_parser("provision")
    credentials.add_argument("--owner", required=True)
    credentials.add_argument("--directory", type=Path, default=Path(".local"))
    args = parser.parse_args()
    if args.command == "migrate":
        migrate(args.database)
        print("Schema migrated successfully.")
    else:
        provision(args.owner, args.directory)


if __name__ == "__main__":
    main()
