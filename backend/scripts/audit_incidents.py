"""Capture or verify an immutable local incident package. No migrations or dispatch."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine

from coldguard_backend.evidence_backup import local_database_url
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.incident_audit import IncidentJournal, create_incident_package, verify_incident_package

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_s1 import clean_backend_commit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root, report = args.directory.resolve(), args.report.resolve()
    if root == report or root in report.parents or args.report.exists():
        parser.error("report must be a new path outside the immutable package")
    if args.operation == "verify":
        result = verify_incident_package(args.directory, expected_manifest_sha256=args.manifest_sha256)
    else:
        if not all((args.journal, args.artifact_root, args.created_at)):
            parser.error("capture needs --journal, --artifact-root and --created-at")
        commit = clean_backend_commit(Path(__file__).resolve().parents[2])
        journal = IncidentJournal.model_validate_json(args.journal.read_bytes())
        engine = create_engine(local_database_url(os.environ["DATABASE_URL"]), connect_args={"connect_timeout": 5})
        try:
            result = create_incident_package(engine, journal, artifact_root=args.artifact_root, destination=args.directory,
                created_at=datetime.fromisoformat(args.created_at), backend_commit=commit)
        finally:
            engine.dispose()
    with args.report.open("xb") as output:
        output.write(encode_evidence(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
