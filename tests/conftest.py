import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlas.config import Settings
from atlas.database import migrate
from atlas.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "atlas.db",
        token_hashes={
            name: hashlib.sha256((name * 16).encode()).hexdigest() for name in ("alice", "bob")
        },
        chunk_size=80,
        chunk_overlap=10,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    migrate(settings.database_path)
    with TestClient(create_app(settings)) as value:
        yield value
