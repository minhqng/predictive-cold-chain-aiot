"""Compare ColdGuard evidence across two disposable PostgreSQL snapshots."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from coldguard_backend.evidence_tables import EVIDENCE_ADDITIONS, TABLE_KEYS, fingerprint_connection

def fingerprint(url) -> dict:
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True,
        ) as connection:
            return fingerprint_connection(connection)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    urls = []
    for name in ("COLDGUARD_BACKUP_SOURCE_URL", "COLDGUARD_BACKUP_RESTORE_URL"):
        if not os.environ.get(name):
            parser.error(f"set {name} to a dedicated database")
        url = make_url(os.environ[name])
        if url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1" or url.query:
            parser.error(f"{name} must be a direct loopback postgresql+psycopg URL")
        urls.append(url)
    if (urls[0].port or 5432, urls[0].database) == (urls[1].port or 5432, urls[1].database):
        parser.error("source and restore must be distinct databases")
    try:
        source, restored = map(fingerprint, urls)
    except ValueError as exc:
        parser.error(str(exc))
    except SQLAlchemyError:
        parser.error("cannot read the required evidence tables for the installed schema")
    identical = source == restored
    with args.output.open("x", encoding="utf-8") as output:
        json.dump({"match": identical, "source": source, "restored": restored}, output, indent=2)
        output.write("\n")
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
