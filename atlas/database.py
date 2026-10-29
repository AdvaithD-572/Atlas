import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 4


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    # mode=rw prevents missing/unmounted storage from silently becoming an empty DB.
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA secure_delete=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def migrate(path: Path) -> None:
    """Apply immutable numbered migrations explicitly, never during API startup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        current = int(db.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise ValueError("Database schema is newer than this application.")
        for version in range(current + 1, SCHEMA_VERSION + 1):
            files = list(Path(__file__).with_name("migrations").glob(f"{version:03}_*.sql"))
            if len(files) != 1:
                raise ValueError("Missing or ambiguous migration.")
            statement = ""
            for line in files[0].read_text(encoding="utf-8").splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ""
            if statement.strip():
                raise ValueError("Incomplete migration statement.")
            db.execute(f"PRAGMA user_version={version}")  # internal integer, never user input
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ready(path: Path) -> bool:
    try:
        with connection(path) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                return False
            db.execute("SELECT id FROM documents LIMIT 1").fetchall()
            db.execute("SELECT id FROM chunks LIMIT 1").fetchall()
            db.execute(
                "SELECT rowid FROM chunk_search WHERE chunk_search MATCH ? LIMIT 1",
                ('"readiness"',),
            ).fetchall()
            return True
    except sqlite3.Error:
        return False
