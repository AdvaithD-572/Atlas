"""Disposable loopback test server. Public test token; never use for real data."""

import argparse
import hashlib
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import uvicorn
from fastapi import FastAPI
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from atlas.config import Settings
from atlas.database import migrate
from atlas.main import create_app
from atlas.postgres import migrate as pg_migrate

TEST_TOKEN = "atlas-browser-smoke-synthetic-only"


@contextmanager
def disposable_app(
    *,
    postgres: bool,
    requests_per_minute: int = 120,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> Iterator[FastAPI]:
    """Isolated test data and schema; limits are explicit per test workload."""
    with ExitStack() as stack:
        directory = stack.enter_context(tempfile.TemporaryDirectory(prefix="atlas-browser-"))
        scoped = None
        if postgres:
            dsn = Path(".local/postgres.dsn").read_text().strip()
            schema = "atlas_browser_" + uuid4().hex
            with psycopg.connect(dsn, autocommit=True) as db:
                db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

            def cleanup() -> None:
                with psycopg.connect(dsn, autocommit=True) as db:
                    db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

            stack.callback(cleanup)
            scoped = SecretStr(make_conninfo(dsn, options=f"-c search_path={schema}"))
            pg_migrate(scoped.get_secret_value())
        settings = Settings(
            database_path=Path(directory) / "test.db",
            token_hashes={"browser-test": hashlib.sha256(TEST_TOKEN.encode()).hexdigest()},
            generation_enabled=True,
            vector_enabled=postgres,
            postgres_dsn=scoped,
            requests_per_minute=requests_per_minute,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        migrate(settings.database_path)
        yield create_app(settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    with disposable_app(postgres=args.postgres) as app:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            access_log=False,
            limit_concurrency=16,
        )


if __name__ == "__main__":
    main()
