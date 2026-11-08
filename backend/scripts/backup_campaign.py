"""Create an evidence archive, or restore and compare it in a separate empty local DB."""

import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine

from coldguard_backend.evidence_backup import backup_campaign, local_database_url, restore_backup
from coldguard_backend.experiment_evidence import encode_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--campaign")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "backup":
        if not args.campaign:
            parser.error("backup requires --campaign")
        engine = create_engine(local_database_url(os.environ["DATABASE_URL"]), connect_args={"connect_timeout": 5})
        try:
            report = backup_campaign(engine, args.campaign, args.directory, pg_dump=os.environ.get("COLDGUARD_PG_DUMP", "pg_dump"))
        finally:
            engine.dispose()
    else:
        report = restore_backup(args.directory, os.environ["COLDGUARD_BACKUP_RESTORE_URL"],
                                pg_restore=os.environ.get("COLDGUARD_PG_RESTORE", "pg_restore"))
    with args.report.open("xb") as output:
        output.write(encode_evidence(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
