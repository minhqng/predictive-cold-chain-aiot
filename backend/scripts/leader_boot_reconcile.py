"""Reconcile the Digital Twin to an observed device boot without starting a controller."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request

from sqlalchemy import create_engine, text
from coldguard_backend.twin_store import TwinBootConflict, reconcile_reported_boot


def promote_twin(engine, device_id: str, live: dict) -> dict:
    telemetry = live.get("telemetry") or {}
    boot = telemetry.get("boot_id")
    if (live.get("fresh") is not True or live.get("device") != device_id
            or not isinstance(boot, str) or not re.fullmatch(r"[a-f0-9]{8}", boot)):
        return {"verdict": "FRESH_DEVICE_BOOT_REQUIRED"}
    with engine.begin() as conn:
        current = conn.execute(
            text("SELECT last_boot_id FROM device_twin WHERE device_id = :device"),
            {"device": device_id},
        ).scalar_one_or_none()
        if current is None:
            return {"verdict": "INITIAL_TWIN_NOT_INGESTED"}
        if current == boot:
            return {"verdict": "ALREADY_CURRENT", "boot": boot}
        newest = conn.execute(
            text("SELECT boot_id FROM telemetry WHERE device_id = :device AND twin_eligible "
                 "ORDER BY id DESC LIMIT 1"), {"device": device_id},
        ).scalar_one_or_none()
        if newest != boot:
            return {"verdict": "BOOT_NOT_INGESTED"}
        version = reconcile_reported_boot(
            conn, device_id=device_id, expected_boot_id=current, new_boot_id=boot)
        return {"verdict": "PROMOTED", "boot": boot, "twin_version": version}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8090")
    parser.add_argument("--device-id", default="coldguard-001")
    args = parser.parse_args(argv)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    engine = create_engine(database_url, connect_args={"connect_timeout": 5})
    try:
        with urllib.request.urlopen(args.dashboard_url.rstrip("/") + "/api/leader/live",
                                    timeout=5) as response:
            live = json.load(response)
        result = promote_twin(engine, args.device_id, live)
    except TwinBootConflict:
        result = {"verdict": "BOOT_CONFLICT"}
    finally:
        engine.dispose()
    print(json.dumps(result))
    return 0 if result["verdict"] in ("ALREADY_CURRENT", "PROMOTED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
