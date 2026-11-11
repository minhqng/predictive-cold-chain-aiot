"""Collect a paced software-only soak against dedicated loopback providers."""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select

from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.experiment_store import RunCreate, RunTransition, create_run, transition_run
from coldguard_backend.mqtt_consumer import MqttIngestConsumer
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.simulator import DEFAULT_DEVICE_ID, run_simulation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7201, help="1 Hz sample count")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least two")
    config = ColdGuardConfig.load()
    if config.postgres_host != "127.0.0.1" or config.mqtt_host != "127.0.0.1":
        parser.error("use explicit 127.0.0.1 endpoints for both disposable providers")
    if not config.mqtt_username or not config.mqtt_password:
        parser.error("a provisioned backend subscriber is required")
    device_user = os.environ["COLDGUARD_SOAK_DEVICE_USER"]
    device_password = os.environ["COLDGUARD_SOAK_DEVICE_PASSWORD"]
    device = os.environ.get("COLDGUARD_SOAK_DEVICE_ID", DEFAULT_DEVICE_ID)
    run_id = f"software-soak-{uuid4().hex}"
    boot_id = f"boot-{run_id}"
    consumer = MqttIngestConsumer(
        config, client_id=run_id, subscriptions=((f"coldguard/{device}/telemetry", 1),),
    )
    engine = create_engine(config.database_url)
    try:
        with engine.begin() as connection:
            create_run(connection, RunCreate(
                run_id=run_id, device_id=device, scenario_id="SOFTWARE_SOAK",
                controller_id="NO_ACTUATION", versions={"schema": 1, "generator": "fw-sim-w02"},
                notes="Synthetic telemetry from the software-only platform soak.",
            ))
            for state in ("ARMED", "RUNNING"):
                transition_run(connection, run_id, RunTransition(status=state))
        try:
            consumer.start()
            simulated = run_simulation(
                host=config.mqtt_host, port=config.mqtt_port, username=device_user,
                password=device_password, device_id=device, boot_id=boot_id,
                run_id=run_id, count=args.samples, publish_families=False, interval_s=1,
            )
            query = select(telemetry.c.seq, telemetry.c.backend_received_at).where(
                telemetry.c.device_id == device, telemetry.c.run_id == run_id,
                telemetry.c.boot_id == boot_id,
            ).order_by(telemetry.c.seq)
            deadline = time.monotonic() + 10
            while True:
                with engine.connect() as connection:
                    rows = connection.execute(query).all()
                if len(rows) >= args.samples or time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
        except Exception:
            with engine.begin() as connection:
                transition_run(connection, run_id, RunTransition(
                    status="ABORTED", reason="software soak did not complete",
                ))
            raise
        finally:
            consumer.stop()

        counts = consumer.snapshot()
        gaps = sorted(set(range(args.samples)).difference(row.seq for row in rows))
        intervals = [
            (right.backend_received_at - left.backend_received_at).total_seconds()
            for left, right in zip(rows, rows[1:])
        ]
        invalid = sum(counts[key] for key in (
            "rejected_schema", "rejected_topic_mismatch", "conflicts",
        ))
        failures = counts["errors"] + counts["normalization_failures"]
        passed = (
            not gaps and len(rows) == args.samples and counts["persisted"] >= args.samples
            and not invalid and not failures
        )
        report = {
            "evidence": "SOFTWARE_SIMULATION",
            "physical_acceptance": "PHYSICAL_NOT_AUTHORIZED",
            "result": "PASS" if passed else "FAIL",
            "run_id": run_id,
            "boot_id": boot_id,
            "device_id": device,
            "expected": args.samples,
            "broker_acknowledged": simulated["publish_acknowledged"],
            "received": counts["received"],
            "raw_persisted": counts["persisted"],
            "normalized": len(rows),
            "duplicates": counts["exact_duplicates"],
            "invalid_or_conflict": invalid,
            "database_errors": failures,
            "sequence_gaps": gaps,
            "target_hz": 1,
            "backend_receive_interval_s": {
                "min": min(intervals) if intervals else None,
                "mean": sum(intervals) / len(intervals) if intervals else None,
                "max": max(intervals) if intervals else None,
                "elapsed": sum(intervals),
            },
            "timing_basis": "backend receipt time; simulated event clock cannot prove latency",
        }
        with engine.begin() as connection:
            transition_run(connection, run_id, RunTransition(status="COMPLETED_RAW"))
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0 if passed else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
