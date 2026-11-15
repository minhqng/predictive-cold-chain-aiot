"""Observe device telemetry and record Member D door-aware shadow decisions."""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "control" / "src"))
sys.path.insert(0, str(REPO_ROOT / "backend" / "integration"))

from coldguard_control.config import PolicyConfig  # noqa: E402
from coldguard_control.policy import (  # noqa: E402
    PolicyInput, ThermalView, RemotePathView, PredictionView, evaluate_policy,
)
from coldguard_control.types import (  # noqa: E402
    CoolingState, DeviceMode, ModelHealth, PolicyState, QualityState,
)
from leader_door_policy import (  # noqa: E402
    DOOR_POLICY_VERSION, DoorControlInput, DoorObservation, DoorPolicyConfig,
    step,
)

BACKEND = os.environ.get("CG_BACKEND_URL", "http://127.0.0.1:8000")
DASHBOARD = os.environ.get("CG_DASHBOARD_URL", "http://127.0.0.1:8090")
DEVICE = os.environ.get("CG_DEVICE_ID", "coldguard-001")

MODE = "shadow"
RESUME_DWELL_S = float(os.environ.get("CG_DOOR_RESUME_DWELL_S", "2.0"))
UPPER_ON_C = float(os.environ.get("CG_POLICY_UPPER_ON_C", "24.0"))
LOWER_OFF_C = float(os.environ.get("CG_POLICY_LOWER_OFF_C", "22.0"))
THERMAL_MAX_AGE_S = float(os.environ.get("CG_POLICY_THERMAL_MAX_AGE_S", "15.0"))
SETPOINT_FILE = Path(os.environ.get("CG_SETPOINT_FILE",
                                    str(REPO_ROOT / "runtime" / "leader" / "setpoint-desired.json")))
HYSTERESIS_C = float(os.environ.get("CG_POLICY_HYSTERESIS_C", "2.0"))
SETPOINT_MIN_C = 5.0
SETPOINT_MAX_C = 40.0
EVENTS = Path(os.environ.get("CG_EVENTS_FILE",
                             str(REPO_ROOT / "runtime/leader/door-events.jsonl")))

POLICY_CFG = PolicyConfig(
    policy_version="leader-door-demo-policy-1",
    representative_source="CHAMBER_MEAN_T1_T3_T4",
    upper_on_c=UPPER_ON_C,
    lower_off_c=LOWER_OFF_C,
    thermal_max_age_s=THERMAL_MAX_AGE_S,
    command_max_future_skew_s=5.0,
    broker_offline_grace_s=30.0,
    backend_state_max_age_s=10.0,
    safe_local_exit_min_stable_s=60.0,
    predictive_enabled=False,  # predictive thresholds are not characterized;
    #                             the branch stays OFF rather than inheriting
    #                             invented numbers. Prediction stays visible.
)
DOOR_CFG = DoorPolicyConfig(enabled=True,
                            resume_dwell_s=RESUME_DWELL_S)


def _get(url: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _quality(value: object) -> QualityState:
    return QualityState.VALID if value == "VALID" else QualityState.UNKNOWN


def _desired_setpoint() -> float | None:
    """Operator desired cooling target — desired state, not an actuation grant.

    When present and valid it becomes the policy target so Member D's evaluation
    consumes the operator's setpoint; absent/invalid => the environment band.
    Reading it never dispatches a command (this orchestrator is shadow-only).
    """
    try:
        value = float(json.loads(SETPOINT_FILE.read_text(encoding="utf-8"))["setpoint_c"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not math.isfinite(value) or not SETPOINT_MIN_C <= value <= SETPOINT_MAX_C:
        return None
    return value


class DoorWatcher:
    """Tracks door state transitions locally to compute closed_since_s."""

    def __init__(self) -> None:
        self.prev: str | None = None
        self.closed_at: float | None = None
        self.opened_at: float | None = None

    def observe(self, state: str | None, now: float) -> tuple[float | None, float | None]:
        if state != self.prev:
            if state == "CLOSED":
                self.closed_at = now
            elif state == "OPEN":
                self.opened_at = now
            self.prev = state
        closed_since = None if self.closed_at is None else max(0.0, now - self.closed_at)
        open_since = None if self.opened_at is None else max(0.0, now - self.opened_at)
        return closed_since, open_since


def build_policy_input(live: dict, prediction: dict | None,
                       last_state: PolicyState) -> tuple[PolicyInput | None, str]:
    """Map the Leader evidence view onto Member D's PolicyInput.

    Returns (input, "") when the inputs are qualified for a real evaluation,
    or (None, reason) when they are not - the caller then uses HOLD semantics
    (no decision available -> change nothing) instead of inventing inputs.
    """
    telemetry = live.get("telemetry") or {}
    if not live.get("fresh") or not telemetry:
        return None, "DEVICE_FRAME_STALE"
    quality = telemetry.get("quality") or {}
    if quality.get("overall") != "VALID":
        return None, f"QUALITY_{quality.get('overall', 'UNKNOWN')}"

    t1, t3, t4 = telemetry.get("t1_c"), telemetry.get("t3_c"), telemetry.get("t4_c")
    if None in (t1, t3, t4):
        return None, "CHAMBER_PROBES_INCOMPLETE"
    chamber_mean = (t1 + t3 + t4) / 3.0

    actuation = telemetry.get("actuation") or {}
    applied = str(actuation.get("cooling") or "").upper()
    if applied not in ("ON", "OFF"):
        return None, "APPLIED_STATE_UNKNOWN"
    door = live.get("door") or {}
    door_state = door.get("state") if door.get("attested_this_boot") else "UNKNOWN"
    if door_state not in ("OPEN", "CLOSED"):
        door_state = "UNKNOWN"

    clock = live.get("clock") or {}
    anchored = clock.get("state") == "ANCHORED"

    prediction_view = None
    if prediction and prediction.get("status") == "FRESH":
        p = prediction.get("prediction") or {}
        prediction_view = PredictionView(
            health=ModelHealth.READY,
            model_version=str(p.get("model_version", "unknown")),
            feature_version=str(p.get("feature_version", "unknown")),
            risk_score=p.get("risk_score"),
            age_s=None,
            horizon_s=None,
            above_preemptive_s=None,
        )

    pi = PolicyInput(
        device_mode=DeviceMode.ONLINE_NORMAL if anchored else DeviceMode.ONLINE_DEGRADED,
        thermal=ThermalView(quality=QualityState.VALID, t_representative_c=chamber_mean,
                            age_s=float(live.get("frame_age_s") or 0.0)),
        applied_cooling=CoolingState.OFF if applied != "ON" else CoolingState.ON,
        remote=RemotePathView(
            broker_connected=True,            # evidence flows => broker path up
            broker_offline_s=0.0,
            backend_state_synced=True,        # hypothetical command path for the shadow policy
            backend_state_age_s=0.0,
            state_sync_trusted=bool(anchored),
            remote_command_path_trusted=True,  # hypothetical command path for the shadow policy
            network_stable_s=120.0,
            stale_command_pending=False,
        ),
        current_state=last_state,
        fan_available=None,                    # as-built fan is not observable
        electrical_quality=_quality(quality.get("electrical")),
        door_state=door_state,
        prediction=prediction_view,
    )
    return pi, ""


def main() -> int:
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    watcher = DoorWatcher()
    state = "IDLE"
    last_state = PolicyState.NORMAL
    last_issued_at = 0.0
    last_boot = None
    cooldown_s = float(os.environ.get("CG_DOOR_COMMAND_COOLDOWN_S", "8.0"))
    print(f"door orchestrator: mode={MODE} policy={POLICY_CFG.policy_version} "
          f"upper_on={UPPER_ON_C} lower_off={LOWER_OFF_C} dwell={RESUME_DWELL_S}s "
          f"cooldown={cooldown_s}s events={EVENTS}", flush=True)
    while True:
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        live = _get(f"{DASHBOARD}/api/leader/live")
        prediction = _get(f"{BACKEND}/api/devices/{DEVICE}/predictions/current")
        setpoint = _desired_setpoint()
        if setpoint is not None and HYSTERESIS_C > 0:
            cfg = replace(POLICY_CFG, lower_off_c=setpoint, upper_on_c=setpoint + HYSTERESIS_C)
        else:
            cfg = POLICY_CFG
        record: dict = {"ts": now_iso, "mode": MODE, "target_c": cfg.lower_off_c,
                        "source": "SHADOW_DECISION",
                        "door_policy_version": DOOR_POLICY_VERSION}
        if live is None or live.get("device") != DEVICE:
            record.update({"event": "OBSERVER_UNREACHABLE",
                           "detail": "dashboard evidence view unreachable"})
        else:
            telemetry = live.get("telemetry") or {}
            boot = telemetry.get("boot_id")
            if boot != last_boot:
                watcher = DoorWatcher()
                state, last_state, last_issued_at = "IDLE", PolicyState.NORMAL, 0.0
                last_boot = boot
            door = live.get("door") or {}
            state_name = door.get("state")
            attested = bool(door.get("attested_this_boot"))
            fresh = bool(live.get("fresh"))
            door_state_val = state_name if (attested and state_name in ("OPEN", "CLOSED")) else None
            closed_since, _ = watcher.observe(door_state_val, now)
            pi, skip = build_policy_input(live, prediction, last_state)
            if pi is None:
                intent, policy_state_name, reason = "HOLD", last_state.value, skip
            else:
                try:
                    decision = evaluate_policy(pi, cfg)
                    intent = decision.actuation_intent.value
                    policy_state_name = decision.state.value
                    reason = decision.reason_detail
                    last_state = PolicyState[decision.state.value]
                except Exception as exc:  # noqa: BLE001 - member validation
                    intent, policy_state_name, reason = "HOLD", last_state.value, \
                        f"POLICY_EVALUATION_ERROR: {exc}"

            decision = step(state, DoorControlInput(
                door=DoorObservation(
                    attested=attested, state=door_state_val, fresh=fresh and pi is not None,
                    transitions=int(door.get("transitions") or 0),
                    closed_since_s=closed_since),
                applied_cooling=str((telemetry.get("actuation") or {}).get("cooling") or "OFF").upper(),
                policy_intent=intent, policy_state=policy_state_name,
                cooldown_active=(now - last_issued_at) < cooldown_s,
                now_s=now,
            ), DOOR_CFG)
            state = decision.state
            record.update({
                "event": "DOOR_TICK",
                "device_id": DEVICE,
                "door_state": door_state_val, "door_attested": attested,
                "door_transitions": door.get("transitions"),
                "applied_cooling": (telemetry.get("actuation") or {}).get("cooling"),
                "seq": telemetry.get("seq"), "boot_id": telemetry.get("boot_id"),
                "t1_c": telemetry.get("t1_c"), "t3_c": telemetry.get("t3_c"),
                "t4_c": telemetry.get("t4_c"),
                "chamber_mean_c": (
                    round((telemetry["t1_c"] + telemetry["t3_c"] + telemetry["t4_c"]) / 3.0, 3)
                    if None not in (telemetry.get("t1_c"), telemetry.get("t3_c"), telemetry.get("t4_c"))
                    else None),
                "policy_intent": intent, "policy_state": policy_state_name,
                "policy_reason": reason,
                "door_action": decision.action, "door_reason": decision.reason,
                "door_detail": decision.detail, "orchestrator_state": state,
            })
            if decision.action in ("ISSUE_OFF", "ISSUE_ON"):
                # One command per transition: the cooldown starts whether or
                # not the mode dispatches (shadow mirrors active's cadence).
                last_issued_at = now
                record["proposed"] = decision.action
        with EVENTS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        time.sleep(1.0)



if __name__ == "__main__":
    raise SystemExit(main())
