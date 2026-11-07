"""Command-line runner for database-backed telemetry reconciliation (C-W05-03).

Usage:
    python -m scripts.reconcile [--device-id DEVICE] [--run-id RUN_ID]
"""

import argparse
import json
import os
import sys

from sqlalchemy import create_engine

from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.reconciliation import reconcile_telemetry


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile raw and normalized telemetry.")
    parser.add_argument("--device-id", default=None, help="Filter by device ID")
    parser.add_argument("--run-id", default=None, help="Filter by run ID")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        try:
            config = ColdGuardConfig.load()
            db_url = config.database_url
        except Exception as exc:
            print(f"Error resolving database URL: {exc}", file=sys.stderr)
            return 2

    engine = create_engine(db_url)
    try:
        report = reconcile_telemetry(engine, device_id=args.device_id, run_id=args.run_id)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print("=" * 60)
            print("ColdGuard Raw/Normalized Reconciliation Report")
            print("=" * 60)
            print(f"Status:                      {'PASSED' if report.is_reconciled else 'FAILED'}")
            print(f"Total Raw Deliveries:        {report.raw_total}")
            print(f"Total Normalized Samples:    {report.normalized_total}")
            print(f"Unique Identities:           {report.unique_identities}")
            print("-" * 60)
            print(f"Unique Normalized Deliveries:{report.unique_normalized_deliveries}")
            print(f"Exact Duplicates:            {report.exact_duplicates}")
            print(f"Conflicting Duplicates:      {report.conflicting_duplicates}")
            print(f"Normalization Failures:      {report.normalization_failures}")
            print(f"Historical Raw (Pre-norm):   {report.historical_raw_unnormalized}")
            print("-" * 60)
            print(f"Rejected (Invalid Schema):   {report.rejected_invalid_schema}")
            print(f"Rejected (Malformed JSON):   {report.rejected_malformed_json}")
            print(f"Rejected (Topic Mismatch):   {report.rejected_topic_mismatch}")
            print(f"Observed (Non-Telemetry):    {report.observed_non_telemetry}")
            print(f"Unknown Ingest Statuses:     {report.unknown_status_count}")
            print("-" * 60)
            print(f"Provenance Mismatches:       {report.provenance.provenance_mismatch_count}")
            print(f"Cross-Run Collisions:        {report.provenance.cross_run_collision_count}")
            print(f"Unrecorded Calibrations:     {report.provenance.unrecorded_calibration_count}")
            print("-" * 60)
            print(f"Discrepancy:                 {report.discrepancy}")
            print("=" * 60)
        return 0 if report.is_reconciled else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
