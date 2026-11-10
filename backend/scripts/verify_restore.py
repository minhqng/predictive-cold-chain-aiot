"""Compare ColdGuard evidence across two disposable PostgreSQL snapshots."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TABLE_KEYS = {
    "alembic_version": "version_num",
    "experiments": "run_id",
    "experiment_transitions": "id",
    "telemetry_raw": "id",
    "telemetry": "id",
    "commands": "command_id",
    "command_attempts": "id",
    "command_acks": "id",
    "command_transitions": "id",
    "device_twin": "device_id",
    "device_twin_retired_boot": "device_id, boot_id",
    "reconciliation_boundary": "id",
    "reconciliation_legacy_audit": "raw_id",
}


def fingerprint(url) -> dict:
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True,
        ) as connection:
            connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            report = {
                "revisions": list(connection.scalars(text("SELECT version_num FROM alembic_version ORDER BY 1"))),
                "tables": {},
            }
            for table, key in TABLE_KEYS.items():
                digest = hashlib.sha256()
                count = 0
                # Table names and keys are exclusively from the static map.
                query = text(f"SELECT to_jsonb(evidence_row)::text FROM {table} evidence_row ORDER BY {key}")
                with connection.execution_options(yield_per=1000).execute(query) as result:
                    for serialized in result.scalars():
                        digest.update(serialized.encode("utf-8") + b"\n")
                        count += 1
                report["tables"][table] = {"rows": count, "sha256": digest.hexdigest()}
            return report
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
    source, restored = map(fingerprint, urls)
    identical = source == restored
    with args.output.open("x", encoding="utf-8") as output:
        json.dump({"match": identical, "source": source, "restored": restored}, output, indent=2)
        output.write("\n")
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
