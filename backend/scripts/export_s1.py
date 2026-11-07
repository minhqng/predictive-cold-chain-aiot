"""Export selected valid S1 runs from a consistent PostgreSQL snapshot."""

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine

from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.dataset_export import build_s1_export
from coldguard_backend.experiment_store import RunNotFound


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--created-at", required=True, help="timezone-aware ISO timestamp")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    git = ["git", "-C", str(repo)]
    if subprocess.run([*git, "diff", "--quiet", "HEAD", "--", "backend"]).returncode != 0:
        parser.error("commit backend changes before attributing an export to HEAD")
    commit = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    engine = create_engine(os.environ.get("DATABASE_URL") or ColdGuardConfig.load().database_url)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            try:
                bundle = build_s1_export(
                    connection, args.run_id, created_at=datetime.fromisoformat(args.created_at),
                    backend_commit=commit,
                )
            except (RunNotFound, ValueError) as exc:
                parser.error(str(exc))
        with args.output.open("xb") as output:
            output.write(bundle)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
