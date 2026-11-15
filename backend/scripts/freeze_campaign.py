"""Freeze/verify/restore a campaign with immutable local artifact references."""

import argparse
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine

from coldguard_backend.campaign_freeze import FreezeDraft, freeze_campaign, get_freeze, verify_frozen_package, verify_frozen_restore
from coldguard_backend.evidence_backup import local_database_url
from coldguard_backend.experiment_evidence import encode_evidence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_s1 import clean_backend_commit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "verify", "restore"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--freeze-id")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    report = args.report.resolve()
    if report == root or root in report.parents:
        parser.error("operational --report must be outside the immutable package directory")
    if args.report.exists():
        parser.error("report path already exists; refuse before changing a freeze")
    engine = create_engine(local_database_url(os.environ["DATABASE_URL"]), connect_args={"connect_timeout": 5})
    try:
        if args.operation == "freeze":
            if not all((args.spec, args.artifact_root, args.backup)):
                parser.error("freeze needs --spec, --artifact-root and --backup")
            draft = FreezeDraft.model_validate_json(args.spec.read_bytes())
            if clean_backend_commit(Path(__file__).resolve().parents[2]) != draft.backend_commit:
                parser.error("freeze exporter provenance must be the current clean backend commit")
            record = freeze_campaign(engine, draft, artifact_root=args.artifact_root, backup_directory=args.backup, destination=args.directory)
            report = {key: record[key] for key in ("freeze_id", "campaign_id", "dataset_id", "manifest_sha256", "export_sha256")}
        else:
            if not args.freeze_id:
                parser.error("verify/restore needs an immutable --freeze-id from the database")
            with engine.connect() as connection:
                record = get_freeze(connection, args.freeze_id)
            report = verify_frozen_package(args.directory, expected_manifest_sha256=record["manifest_sha256"]) if args.operation == "verify" else verify_frozen_restore(
                args.directory, record, os.environ["COLDGUARD_BACKUP_RESTORE_URL"], pg_restore=os.environ.get("COLDGUARD_PG_RESTORE", "pg_restore"),
            )
        with args.report.open("xb") as output:
            output.write(encode_evidence(report))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
