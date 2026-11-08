"""Revision-specific durable evidence fingerprints shared by exports and restore."""

import hashlib

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

TABLE_KEYS = {
    "alembic_version": "version_num", "experiments": "run_id", "experiment_transitions": "id",
    "telemetry_raw": "id", "telemetry": "id", "commands": "command_id", "command_attempts": "id",
    "command_acks": "id", "command_transitions": "id", "device_twin": "device_id",
    "device_twin_retired_boot": "device_id, boot_id", "reconciliation_boundary": "id",
    "reconciliation_legacy_audit": "raw_id",
}
EVIDENCE_ADDITIONS = {
    "0009": {},
    "0010": {"predictions": "prediction_id", "prediction_inputs": "prediction_id, ordinal"},
    "0011": {"shadow_decisions": "decision_id"},
    "0012": {"physical_assessments": "assessment_id", "policy_approvals": "command_id"},
    "0013": {"campaigns": "campaign_id", "campaign_runs": "run_id", "campaign_run_closures": "closure_id"},
}


def evidence_keys(revision: str) -> dict[str, str]:
    if revision not in EVIDENCE_ADDITIONS:
        raise ValueError("unsupported Alembic revision for evidence verification")
    keys = TABLE_KEYS.copy()
    for current, additions in EVIDENCE_ADDITIONS.items():
        keys.update(additions)
        if current == revision:
            break
    return keys


def fingerprint_connection(connection: Connection) -> dict:
    """Call within a repeatable-read transaction, including exported DB snapshots."""
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version ORDER BY 1")))
    if len(revisions) != 1:
        raise ValueError("exactly one installed Alembic revision is required")
    keys = evidence_keys(revisions[0])
    if set(inspect(connection).get_table_names(schema="public")) != set(keys):
        raise ValueError("installed public evidence tables differ from the reviewed revision")
    report = {"revisions": revisions, "tables": {}}
    for table, key in keys.items():
        digest, count = hashlib.sha256(), 0
        # Identifiers come only from the reviewed static revision map.
        query = text(f"SELECT to_jsonb(evidence_row)::text FROM public.{table} evidence_row ORDER BY {key}")
        with connection.execute(query.execution_options(yield_per=1000)) as result:
            for serialized in result.scalars():
                digest.update(serialized.encode("utf-8") + b"\n")
                count += 1
        report["tables"][table] = {"rows": count, "sha256": digest.hexdigest()}
    return report
