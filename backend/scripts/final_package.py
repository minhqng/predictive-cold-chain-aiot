"""Build or verify a frozen-source JSON package; no migration or command dispatch."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import create_engine

from coldguard_backend.campaign_freeze import Digest, FileName, get_freeze
from coldguard_backend.evidence_backup import local_database_url
from coldguard_backend.evidence_paths import portable_component
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.final_package import create_final_package, verify_final_package

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_s1 import clean_backend_commit


class IncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: FileName
    directory: Annotated[str, Field(min_length=1, max_length=2048)]
    manifest_sha256: Digest


def _portable(path: Path):
    for part in path.parts:
        if part not in {path.anchor, ".", ".."}:
            portable_component(part)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--freeze-id")
    parser.add_argument("--created-at")
    parser.add_argument("--incidents", type=Path, help="JSON list of separately anchored IncidentInput references")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.directory, args.report, args.frozen, args.incidents):
        if path is not None:
            _portable(path)
    inputs = TypeAdapter(list[IncidentInput]).validate_json(args.incidents.read_bytes()) if args.incidents else []
    if len(inputs) > 20 or len({row.name.casefold() for row in inputs}) != len(inputs):
        parser.error("incident package labels must be distinct and bounded")
    roots = [args.directory, *([args.frozen] if args.frozen else []), *(Path(row.directory) for row in inputs)]
    for root in roots:
        _portable(root)
    report = args.report.resolve()
    if args.report.exists() or any(report == root.resolve() or root.resolve() in report.parents for root in roots):
        parser.error("report must be a new path outside all immutable input/output packages")
    destination = args.directory.resolve()
    if any(destination == root.resolve() or root.resolve() in destination.parents or destination in root.resolve().parents for root in roots[1:]):
        parser.error("final output and immutable input directories must not overlap")
    if args.operation == "verify":
        result = verify_final_package(args.directory, expected_manifest_sha256=args.manifest_sha256)
    else:
        if not all((args.frozen, args.freeze_id, args.created_at)):
            parser.error("build needs --frozen, --freeze-id and --created-at")
        commit = clean_backend_commit(Path(__file__).resolve().parents[2])
        engine = create_engine(local_database_url(os.environ["DATABASE_URL"]), connect_args={"connect_timeout": 5})
        try:
            with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
                record = get_freeze(connection, args.freeze_id)
            result = create_final_package(args.frozen, record, destination=args.directory,
                created_at=datetime.fromisoformat(args.created_at), backend_commit=commit,
                incidents={row.name: (Path(row.directory), row.manifest_sha256) for row in inputs})
        finally:
            engine.dispose()
    with args.report.open("xb") as output:
        output.write(encode_evidence(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
