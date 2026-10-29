"""Explicit deployment administration; runtime processes never provision grants."""

import argparse
import os
import re
import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

TABLES = ("documents", "chunks", "ingestion_jobs", "chunk_embeddings")


def provision_runtime(admin_dsn: str, role: str, password: str, schema: str = "public") -> str:
    if not re.fullmatch(r"atlas_runtime_[a-z0-9_]{1,40}", role) or len(password) < 32:
        raise ValueError("Use a dedicated runtime role and a generated credential")
    with psycopg.connect(admin_dsn) as db:
        db.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 24"
            ).format(sql.Identifier(role), sql.Literal(password))
        )
        db.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(role)
            )
        )
        db.execute(
            sql.SQL("GRANT SELECT ON {}.atlas_schema TO {}").format(
                sql.Identifier(schema), sql.Identifier(role)
            )
        )
        for table in TABLES:
            db.execute(
                sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(table), sql.Identifier(role)
                )
            )
    return make_conninfo(admin_dsn, user=role, password=password)


def initialize_runtime(directory: Path = Path(".local")) -> None:
    native = directory / "runtime.dsn"
    container = directory / "runtime-container.dsn"
    if native.exists() or container.exists():
        raise ValueError("Runtime credentials already exist; refusing to overwrite them")
    password = secrets.token_urlsafe(32)
    role = "atlas_runtime_" + secrets.token_hex(6)
    admin = (directory / "postgres.dsn").read_text().strip()
    dsn = provision_runtime(admin, role, password)
    container_dsn = make_conninfo(dsn, host="postgres", port="5432")
    created: list[Path] = []
    try:
        for path, value in ((native, dsn), (container, container_dsn)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        # This role was created by this invocation and cannot own application objects.
        with psycopg.connect(admin) as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        raise RuntimeError(
            "Runtime credential files could not be written; provisioning undone"
        ) from None
    print("Restricted runtime credentials written to ignored .local files.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init-runtime"])
    parser.parse_args()
    initialize_runtime()


if __name__ == "__main__":
    main()
