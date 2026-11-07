"""ColdGuard backend application entry point.

Endpoints:
- GET /health: liveness check.
- GET /api/devices/{device_id}/state: current device Digital Twin state (C-W05-04).
- GET /api/devices/{device_id}/telemetry: recent normalized telemetry with timing (C-W05-04, C-W05-05).

The MQTT ingestion consumer (C-W02-03) runs in this same process via ``lifespan``
when ``COLDGUARD_MQTT_INGEST`` is truthy.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from sqlalchemy import Engine, create_engine, select

from coldguard_backend.normalized_store import (
    count_telemetry,
    query_telemetry,
    telemetry,
)
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.timing import compute_timing_metrics
from coldguard_backend.twin_store import device_twin

log = logging.getLogger(__name__)

_STARTUP_RETRIES = int(os.environ.get("COLDGUARD_MQTT_STARTUP_RETRIES", "12"))
_STARTUP_RETRY_DELAY_S = float(os.environ.get("COLDGUARD_MQTT_STARTUP_RETRY_S", "5"))


def _ingest_enabled() -> bool:
    return os.environ.get("COLDGUARD_MQTT_INGEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _start_consumer():
    """Start the ingestion consumer with bounded broker-readiness retries.

    Retries cover only unreachable/unanswered brokers (Compose start
    ordering): each attempt is logged and the bound keeps a genuinely
    dead broker a loud startup failure. Refused credentials
    (ConnectionError) fail immediately — retrying those would only
    hammer the broker and hide a provisioning mistake.
    """
    import time

    from coldguard_backend.config import ColdGuardConfig
    from coldguard_backend.mqtt_consumer import MqttIngestConsumer

    config = ColdGuardConfig.load()
    consumer = MqttIngestConsumer.from_config(config)
    attempt = 0
    while True:
        attempt += 1
        try:
            consumer.start()
            return consumer
        except ConnectionError:
            raise
        except TimeoutError as exc:
            if attempt > _STARTUP_RETRIES:
                raise
            log.warning(
                "mqtt broker not ready (attempt %d/%d): %s",
                attempt,
                _STARTUP_RETRIES,
                exc,
            )
            time.sleep(_STARTUP_RETRY_DELAY_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = None
    if _ingest_enabled():
        consumer = _start_consumer()
        log.info("mqtt ingestion consumer started")
    app.state.mqtt_consumer = consumer
    try:
        yield
    finally:
        if consumer is not None:
            consumer.stop()
            log.info("mqtt ingestion consumer stopped")


app = FastAPI(title="ColdGuard Backend", lifespan=lifespan)
app.state.mqtt_consumer = None
app.state.db_engine = None


def get_db_engine(request: Request) -> Engine:
    """Retrieve database engine from application state or environment."""
    engine = getattr(request.app.state, "db_engine", None)
    if engine is not None:
        return engine

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        from coldguard_backend.config import ColdGuardConfig

        config = ColdGuardConfig.load()
        db_url = config.database_url

    cached = getattr(request.app.state, "_cached_engine", None)
    if cached is None:
        cached = create_engine(db_url)
        request.app.state._cached_engine = cached
    return cached


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/devices/{device_id}/state")
@app.get("/devices/{device_id}/state")
def get_device_state(
    device_id: str = Path(..., min_length=1, description="Device identifier"),
    engine: Engine = Depends(get_db_engine),
) -> dict[str, Any]:
    """Read current Digital Twin state for a device (C-W05-04).

    Preserves strict separation between reported, desired, and derived states.
    Returns 404 when the device is unknown.
    """
    cleaned_id = device_id.strip()
    if not cleaned_id:
        raise HTTPException(status_code=404, detail="Device not found")

    with engine.begin() as connection:
        twin_row = connection.execute(
            select(device_twin).where(device_twin.c.device_id == cleaned_id)
        ).mappings().first()

    if twin_row is None:
        raise HTTPException(status_code=404, detail=f"Device {cleaned_id!r} not found")

    return {
        "device_id": twin_row["device_id"],
        "twin_version": twin_row["twin_version"],
        "reported_state": twin_row["reported_state"],
        "desired_state": twin_row["desired_state"],
        "derived_state": twin_row["derived_state"],
        "connectivity_state": twin_row["connectivity_state"],
        "device_mode": twin_row["device_mode"],
        "last_boot_id": twin_row["last_boot_id"],
        "last_seq": twin_row["last_seq"],
        "last_reported_at": (
            twin_row["last_reported_at"].isoformat()
            if twin_row["last_reported_at"]
            else None
        ),
        "last_desired_at": (
            twin_row["last_desired_at"].isoformat()
            if twin_row["last_desired_at"]
            else None
        ),
        "last_derived_at": (
            twin_row["last_derived_at"].isoformat()
            if twin_row["last_derived_at"]
            else None
        ),
        "updated_at": (
            twin_row["updated_at"].isoformat() if twin_row["updated_at"] else None
        ),
    }


@app.get("/api/devices/{device_id}/telemetry")
@app.get("/devices/{device_id}/telemetry")
def get_device_telemetry(
    device_id: str = Path(..., min_length=1, description="Device identifier"),
    limit: int = Query(default=100, ge=1, le=1000, description="Bounded page limit"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    run_id: str | None = Query(default=None, description="Filter by experiment/run ID"),
    time_basis: Literal["received", "event"] = Query(
        default="received",
        description="Time basis for filtering ('received' for backend receipt time, 'event' for device captured time)",
    ),
    start_time: datetime | None = Query(default=None, description="Start timestamp"),
    end_time: datetime | None = Query(default=None, description="End timestamp"),
    order: Literal["asc", "desc"] = Query(default="desc", description="Stable ordering"),
    clockless_only: bool = Query(default=False, description="Filter clockless observations"),
    engine: Engine = Depends(get_db_engine),
) -> dict[str, Any]:
    """Read recent normalized telemetry for a device (C-W05-04, C-W05-05).

    Supports:
    - Bounded pagination (limit 1-1000, non-negative offset)
    - Safe filtering by run_id, time range, time_basis, and clockless flag
    - Stable ordering
    - Source provenance (serial_source, raw_id)
    - Clock-quality-aware timing metrics with fail-closed synchronization verification
    """
    cleaned_id = device_id.strip()
    if not cleaned_id:
        raise HTTPException(status_code=404, detail="Device not found")

    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=422,
            detail="start_time must be less than or equal to end_time",
        )

    with engine.begin() as connection:
        # Verify device existence in either twin or telemetry
        twin_exists = connection.execute(
            select(device_twin.c.device_id).where(device_twin.c.device_id == cleaned_id)
        ).scalar_one_or_none()

        if twin_exists is None:
            telemetry_exists = connection.execute(
                select(telemetry.c.id).where(telemetry.c.device_id == cleaned_id).limit(1)
            ).scalar_one_or_none()
            if telemetry_exists is None:
                raise HTTPException(
                    status_code=404, detail=f"Device {cleaned_id!r} not found"
                )

        rows = query_telemetry(
            connection,
            device_id=cleaned_id,
            run_id=run_id,
            time_basis=time_basis,
            start_time=start_time,
            end_time=end_time,
            clockless_only=clockless_only,
            order=order,
            limit=limit,
            offset=offset,
        )
        total_count = count_telemetry(
            connection,
            device_id=cleaned_id,
            run_id=run_id,
            time_basis=time_basis,
            start_time=start_time,
            end_time=end_time,
            clockless_only=clockless_only,
        )

        raw_ids = [r["raw_id"] for r in rows if r.get("raw_id")]
        raw_lookup: dict[int, Any] = {}
        if raw_ids:
            try:
                raw_rows_stmt = select(telemetry_raw.c.id, telemetry_raw.c.raw_json).where(
                    telemetry_raw.c.id.in_(raw_ids)
                )
                raw_lookup = {
                    row["id"]: row["raw_json"]
                    for row in connection.execute(raw_rows_stmt).mappings().all()
                }
            except Exception:
                raw_lookup = {}

    items = []
    for r in rows:
        raw_json = raw_lookup.get(r.get("raw_id"))
        is_replay = False
        if isinstance(raw_json, dict):
            is_replay = bool(raw_json.get("replay") or raw_json.get("is_replay"))
        elif r.get("is_replay"):
            is_replay = True

        timing = compute_timing_metrics(
            r["backend_received_at"],
            r["time"],
            clock_sync_verified=False,
            serial_source=r.get("serial_source"),
            is_replay=is_replay,
        )
        items.append(
            {
                "id": r["id"],
                "device_id": r["device_id"],
                "boot_id": r["boot_id"],
                "seq": r["seq"],
                "run_id": r["run_id"],
                "time": r["time"].isoformat() if r["time"] else None,
                "backend_received_at": r["backend_received_at"].isoformat(),
                "timing": timing.to_dict(),
                "measurements": {
                    "thermal": {
                        "t1_c": r["t1_c"],
                        "t2_c": r["t2_c"],
                        "t3_c": r["t3_c"],
                    },
                    "environment": {
                        "t_air_c": r["t_air_c"],
                        "rh_pct": r["rh_pct"],
                    },
                    "door_state": r["door_state"],
                    "electrical": {
                        "voltage_v": r["cooling_voltage_v"],
                        "current_a": r["cooling_current_a"],
                        "power_w": r["cooling_power_w"],
                        "energy_counter_wh": r["cooling_energy_counter_wh"],
                    },
                    "actuation": {
                        "cooling": r["applied_cooling"],
                        "duty": r["applied_duty"],
                    },
                },
                "quality": {
                    "thermal": r["thermal_quality"],
                    "environment": r["environment_quality"],
                    "electrical": r["electrical_quality"],
                    "overall": r["overall_quality"],
                    "device_mode": r["device_mode"],
                },
                "provenance": {
                    "hardware_config_id": r["hardware_config_id"],
                    "firmware_version": r["firmware_version"],
                    "calibration_id": r["calibration_id"],
                    "schema_version": r["schema_version"],
                    "raw_id": r["raw_id"],
                    "serial_source": r["serial_source"],
                },
            }
        )

    return {
        "items": items,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "device_id": cleaned_id,
    }
