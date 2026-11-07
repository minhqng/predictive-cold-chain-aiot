"""ColdGuard backend application entry point.

Endpoints:
- GET /health: liveness check.
- GET /api/devices/{device_id}/state: current device Digital Twin state (C-W05-04).
- GET /api/devices/{device_id}/telemetry: recent normalized telemetry with timing (C-W05-04, C-W05-05).

The MQTT ingestion consumer (C-W02-03) runs in this same process via ``lifespan``
when ``COLDGUARD_MQTT_INGEST`` is truthy.

Authentication limitation (W05): these read-only endpoints are unauthenticated
in the local/dev profile and rely on network-level isolation (Compose binds the
backend to 127.0.0.1). They expose no command mutation path. Production
authorization (backend authn/authz, protected command endpoints) is a later
security slice (W15); until then do not expose this service beyond a trusted
local network.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from sqlalchemy import Engine, create_engine, select

from coldguard_backend import experiment_store as runs
from coldguard_backend.command_store import CommandNotFound
from coldguard_backend.command_timing import command_timing
from coldguard_backend.dataset_export import run_integrity
from coldguard_backend.event_timeline import s2_timeline_page
from coldguard_backend.experiment_evidence import (
    encode_evidence, export_run, run_commands, run_observations, run_samples, run_timeline,
)
from coldguard_backend.normalized_store import (
    count_telemetry,
    query_telemetry,
    telemetry,
)
from coldguard_backend.observability import runtime_metrics
from coldguard_backend.prediction_store import (
    current_prediction, derived_prediction_view, prediction_details, prediction_history,
)
from coldguard_backend.recovery import device_recovery_snapshot, reconcile_command_history
from coldguard_backend.shadow_trace import shadow_trace
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
    ack_consumer = None
    try:
        app.state.command_recovery = None
        if os.environ.get("COLDGUARD_RECONCILE_COMMANDS", "").strip().lower() in ("1", "true", "yes"):
            app.state.command_recovery = _recover_startup(app)
        if _ingest_enabled():
            consumer = _start_consumer()
            log.info("mqtt ingestion consumer started")
        app.state.mqtt_consumer = consumer
        if os.environ.get("COLDGUARD_MQTT_ACK_INGEST", "").strip().lower() in ("1", "true", "yes"):
            from coldguard_backend.ack_consumer import AckConsumer
            from coldguard_backend.config import ColdGuardConfig

            ack_consumer = AckConsumer.from_config(ColdGuardConfig.load())
            ack_consumer.start()
            log.info("mqtt ACK consumer subscribed")
        app.state.ack_consumer = ack_consumer
        yield
    finally:
        try:
            if ack_consumer is not None:
                ack_consumer.stop()
        finally:
            try:
                if consumer is not None:
                    consumer.stop()
                    log.info("mqtt ingestion consumer stopped")
            finally:
                cached = getattr(app.state, "_cached_engine", None)
                if cached is not None:
                    cached.dispose()
                    app.state._cached_engine = None


app = FastAPI(title="ColdGuard Backend", lifespan=lifespan)
app.state.mqtt_consumer = None
app.state.ack_consumer = None
app.state.db_engine = None
app.state.command_recovery = None


def _database_url() -> str:
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    from coldguard_backend.config import ColdGuardConfig

    return ColdGuardConfig.load().database_url


def _recover_startup(app: FastAPI) -> dict:
    injected = app.state.db_engine
    engine = injected if injected is not None else create_engine(
        _database_url(), connect_args={"connect_timeout": 5},
    )
    try:
        report = reconcile_command_history(engine)
        log.info(
            "reconciled command history: uncertain=%d expired=%d",
            len(report["uncertain_commands"]), len(report["expired_commands"]),
        )
        return report
    finally:
        if injected is None:
            engine.dispose()


def get_db_engine(request: Request) -> Engine:
    """Retrieve database engine from application state or environment."""
    engine = getattr(request.app.state, "db_engine", None)
    if engine is not None:
        return engine

    cached = getattr(request.app.state, "_cached_engine", None)
    if cached is None:
        cached = create_engine(_database_url())
        request.app.state._cached_engine = cached
    return cached


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/metrics")
def read_runtime_metrics() -> dict:
    return runtime_metrics.snapshot()


@app.get("/api/runtime/readiness")
def read_runtime_readiness(request: Request) -> dict:
    ingest_consumer = request.app.state.mqtt_consumer
    ack_consumer = request.app.state.ack_consumer
    telemetry_readiness = ingest_consumer.snapshot() if ingest_consumer else {}
    return {
        "telemetry_broker_connected": telemetry_readiness.get("broker_connected", False),
        "telemetry_subscribed": telemetry_readiness.get("subscribed", False),
        "ack_subscribed": ack_consumer.snapshot()["subscribed"] if ack_consumer else False,
        "startup_reconciliation": request.app.state.command_recovery is not None,
    }


@app.get("/api/devices/{device_id}/recovery")
def read_device_recovery(device_id: str, engine: Engine = Depends(get_db_engine)) -> dict:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        return device_recovery_snapshot(connection, device_id)


@app.get("/api/commands/{command_id}/timing")
def read_command_timing(command_id: str, engine: Engine = Depends(get_db_engine)) -> dict:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            return command_timing(connection, command_id)
    except CommandNotFound as exc:
        raise HTTPException(status_code=404, detail="Command not found") from exc


@app.post("/api/runs", status_code=201)
def register_run(run: runs.RunCreate, engine: Engine = Depends(get_db_engine)) -> dict:
    try:
        with engine.begin() as connection:
            return runs.create_run(connection, run)
    except runs.RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/transitions")
def change_run(
    run_id: str, change: runs.RunTransition, engine: Engine = Depends(get_db_engine),
) -> dict:
    try:
        with engine.begin() as connection:
            return runs.transition_run(connection, run_id, change)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except runs.RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}")
def read_run(run_id: str, engine: Engine = Depends(get_db_engine)) -> dict:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            run = runs.get_run(connection, run_id)
            return {"run": run, "history": runs.run_history(connection, run_id)}
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/export")
def read_run_export(run_id: str, engine: Engine = Depends(get_db_engine)) -> Response:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            content = export_run(connection, runs.get_run(connection, run_id))
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return Response(content, media_type="application/json")


@app.get("/api/runs/{run_id}/timeline")
def read_run_timeline(run_id: str, engine: Engine = Depends(get_db_engine)) -> dict:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            run = runs.get_run(connection, run_id)
            return {"run_id": run_id, "items": run_timeline(connection, run)}
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/integrity")
def read_run_integrity(run_id: str, engine: Engine = Depends(get_db_engine)) -> dict:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            run = runs.get_run(connection, run_id)
            return {"run_id": run_id, **run_integrity(connection, run, run_samples(connection, run))}
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/s2-timeline")
def read_s2_timeline(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None, max_length=1024),
    download: bool = False,
    engine: Engine = Depends(get_db_engine),
) -> Response:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            run = runs.get_run(connection, run_id)
            content = encode_evidence(s2_timeline_page(connection, run, limit=limit, cursor=cursor))
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    headers = {"Content-Disposition": 'attachment; filename="s2-timeline.json"'} if download else None
    return Response(content, media_type="application/json", headers=headers)


@app.get("/api/runs/{run_id}/shadow-trace")
def read_shadow_trace(
    run_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
    engine: Engine = Depends(get_db_engine),
) -> dict:
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            return shadow_trace(connection, runs.get_run(connection, run_id), limit=limit, offset=offset)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/{kind}")
def read_run_page(
    run_id: str,
    kind: Literal["telemetry", "events", "commands"],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
    engine: Engine = Depends(get_db_engine),
) -> dict:
    query = {"telemetry": run_samples, "events": run_observations, "commands": run_commands}[kind]
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            run = runs.get_run(connection, run_id)
            rows = [dict(row) for row in query(connection, run, limit=limit + 1, offset=offset)]
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    next_offset = offset + limit
    return {
        "run_id": run_id, "device_id": run["device_id"], "items": rows[:limit],
        "limit": limit, "offset": offset,
        "next_offset": next_offset if len(rows) > limit and next_offset <= 100_000 else None,
    }


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
        "derived_state": derived_prediction_view(twin_row["derived_state"], datetime.now(timezone.utc)),
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


@app.get("/api/devices/{device_id}/predictions/current")
def read_current_prediction(
    device_id: str, run_id: str | None = None, engine: Engine = Depends(get_db_engine),
) -> dict:
    with engine.connect() as connection:
        return current_prediction(connection, device_id, run_id)


@app.get("/api/devices/{device_id}/predictions")
def read_prediction_history(
    device_id: str,
    run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    engine: Engine = Depends(get_db_engine),
) -> dict:
    with engine.connect() as connection:
        items = prediction_history(connection, device_id, run_id, limit, offset)
    return {"device_id": device_id, "run_id": run_id, "items": items, "limit": limit, "offset": offset}


@app.get("/api/devices/{device_id}/predictions/{prediction_id}")
def read_prediction_details(
    device_id: str, prediction_id: str, engine: Engine = Depends(get_db_engine),
) -> dict:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        item = prediction_details(connection, device_id, prediction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return item


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

    # Validate user-supplied time bounds before any comparison. A naive
    # timestamp must never reach an aware/naive subtraction (which would
    # raise TypeError and surface as HTTP 500). Invalid input is always 422.
    if start_time is not None and start_time.tzinfo is None:
        raise HTTPException(
            status_code=422, detail="start_time must be timezone-aware"
        )
    if end_time is not None and end_time.tzinfo is None:
        raise HTTPException(
            status_code=422, detail="end_time must be timezone-aware"
        )
    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=422,
            detail="start_time must be less than or equal to end_time",
        )
    # Event basis filters on device event time and excludes clockless rows
    # (time IS NULL) by definition; combining it with clockless_only is a
    # contradiction (time IS NULL AND time IS NOT NULL). Reject explicitly
    # rather than silently returning an empty page.
    if clockless_only and time_basis == "event":
        raise HTTPException(
            status_code=422,
            detail="clockless_only=true is incompatible with time_basis=event; "
            "clockless observations have no event time (use time_basis=received)",
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
            # Do not swallow database errors here: a failed raw lookup must
            # remain observable (propagates as a server error) rather than
            # silently reclassifying provenance/replay flags as absent.
            raw_rows_stmt = select(telemetry_raw.c.id, telemetry_raw.c.raw_json).where(
                telemetry_raw.c.id.in_(raw_ids)
            )
            raw_lookup = {
                row["id"]: row["raw_json"]
                for row in connection.execute(raw_rows_stmt).mappings().all()
            }

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
