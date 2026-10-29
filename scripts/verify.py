"""Run the same backend verification gates on native and Linux CI runtimes."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from psycopg.conninfo import make_conninfo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-file", type=Path)
    parser.add_argument("--database-host")
    args = parser.parse_args()
    environment = os.environ.copy()
    if args.database_file:
        dsn = args.database_file.read_text().strip()
        if args.database_host:
            dsn = make_conninfo(dsn, host=args.database_host, port="5432")
        environment["ATLAS_TEST_POSTGRES_DSN"] = dsn
    if not environment.get("ATLAS_TEST_POSTGRES_DSN"):
        parser.error("A disposable test PostgreSQL connection is required; no silent skips.")
    for command in (
        ["ruff", "check", "atlas", "tests", "scripts"],
        ["ruff", "format", "--check", "atlas", "tests", "scripts"],
        ["mypy"],
        ["pytest", "-q", "--tb=no", "--cov=atlas", "--cov-report=term"],
    ):
        print("Running " + " ".join(command), flush=True)
        subprocess.run([sys.executable, "-m", *command], env=environment, check=True)


if __name__ == "__main__":
    main()
