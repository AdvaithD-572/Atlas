"""Disposable loopback format QA server; synthetic public test credential only."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from atlas.config import Settings
from atlas.database import migrate
from atlas.main import create_app
from tests.test_formats import pdf_bytes


def main() -> None:
    directory = Path(".local")
    directory.mkdir(exist_ok=True)
    (directory / "formats-fixture.pdf").write_bytes(
        pdf_bytes("Synthetic PDF token rotation policy.")
    )
    with TemporaryDirectory(prefix="atlas-formats-qa-") as temporary:
        settings = Settings(
            database_path=Path(temporary) / "qa.db",
            token_hashes={"qa": hashlib.sha256(b"atlas-format-browser-fixture").hexdigest()},
            frontend_dir=Path("frontend/dist").resolve(),
        )
        migrate(settings.database_path)
        uvicorn.run(create_app(settings), host="127.0.0.1", port=8003, access_log=False)


if __name__ == "__main__":
    main()
