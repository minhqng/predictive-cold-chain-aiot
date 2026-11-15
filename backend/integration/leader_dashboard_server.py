"""ColdGuard live operations dashboard (Leader-owned).

Serves the single-file dashboard at http://127.0.0.1:8090/ and proxies /api/*
for selected read-only Member C backend views.

Leader-owned evidence and latency layers on top of the passthrough:

- Subscribes (read-only principal, unique client id) to the device telemetry
  topic and the leader-diag topic. Every displayed field derives from the
  device's own bytes: the raw TELEM frame (T4/spare probe, door_raw, door
  transitions/cycles, timestamp label) and the NETCMD sync exchange
  (challenge capability line + SYNC ACCEPTED anchors).
- /api/leader/live         - decoded evidence view for the dashboard
- /api/leader/history      - ring buffer of recent decoded frames
- /api/leader/door-latency - per-edge door latency measurements
- /api/leader/xgb          - read-only demo score/forecast from the selected
  frozen artifact (legacy W15 risk, or +60 s temperature regressor)
- /api/leader/stream       - SSE push: each new frame the moment MQTT
  delivers it, removing the poll-interval phase from the display path.

Door latency model (measured, per edge):
  physical motion -> GPIO sample (<=15 ms delivered poll) -> 50 ms debounce
  -> next 1 Hz TELEM frame (0-1000 ms, delivered frame rate) -> serial to
  gateway -> MQTT (~1-5 ms measured) -> proxy (SSE push, ~0 ms) -> render.
  The physical->GPIO part is not observable without a device-side timestamp;
  everything after the frame publication is measured here.

Display rules (no fabricated state anywhere):
- Polarity (recalibrated from the owner's live physical observation on
  2026-11-13; supersedes the earlier raw0=OPEN record): raw 0 = CLOSED,
  raw 1 = OPEN. Per-boot attestation never carries over boots: both raw
  levels must appear in THIS boot; before that the dashboard says
  AWAITING BOOT ATTESTATION with the owner action, never a bare UNKNOWN.
- T4 (NEAR_DOOR) is accepted only when the frame's spare ROM matches the
  owner-confirmed 283BE5C9000000A9 AND raw_spare_status=OK; otherwise the
  exact reason is shown. T4 is never presented as the T2 hot-side probe.
- Clock: ANCHORED only while a device-accepted SYNC anchor is fresh (the
  gateway emits SYNC only after its own NTP verification; the device
  validates challenge+boot). The delivered TELEM frame's honest
  timestamp_utc=UNAVAILABLE label is shown next to it, not hidden.
- Staleness: past the freshness budget every verdict degrades to STALE
  instead of reusing old data as current.
"""
from __future__ import annotations

import hmac
import json
import math
import os
import re
import threading
import time
import http.server
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = os.environ.get("CG_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
PAGE = Path(__file__).with_name("leader_dashboard.html")
PORT = int(os.environ.get("CG_DASHBOARD_PORT", "8090"))
DEVICE = os.environ.get("CG_DEVICE_ID", "coldguard-001")
DEVICE_API = f"/api/devices/{urllib.parse.quote(DEVICE, safe='')}"
# Default to the tracked, self-contained W15 artifact so a fresh release clone
# forecasts without uncommitted artifacts. The newer real-temp60 demo bundle is
# experimental and env-selectable via COLDGUARD_DEMO_MODEL_DIR.
DEFAULT_DEMO_MODEL_DIR = REPO_ROOT / "ml/reports/W15/model"
DEMO_MODEL_DIR = os.environ.get("COLDGUARD_DEMO_MODEL_DIR", str(DEFAULT_DEMO_MODEL_DIR))
DEMO_MODEL_VERSION: str | None = os.environ.get("COLDGUARD_DEMO_MODEL_VERSION")
# Operator authorization for the desired-setpoint write path. Provisioned at
# runtime via the environment, never hardcoded; unset => the write path fails
# closed. Reading the desired target and all device evidence stays open.
OPERATOR_TOKEN = os.environ.get("CG_OPERATOR_TOKEN", "")
SETPOINT_FILE = Path(os.environ.get(
    "CG_SETPOINT_FILE", str(REPO_ROOT / "runtime" / "leader" / "setpoint-desired.json")))
SETPOINT_MIN_C = 5.0
SETPOINT_MAX_C = 40.0
TOPIC_TELEM = f"coldguard/{DEVICE}/telemetry"
TOPIC_DIAG = f"coldguard/{DEVICE}/leader-diag"

# Recalibrated 2026-11-13 from the owner's live physical observation
# (door confirmed CLOSED while raw=0 held steady with zero new edges —
# three consistent reports today). Supersedes the earlier raw0=OPEN
# attestation note. Consequence, tracked honestly: the delivered
# CG_DOOR_RAW_OPEN_LEVEL=0 makes the device-side door_open (and the three
# door features) INVERTED versus physical reality until Member A's constant
# is corrected through the auditable staging build and flashed with owner GO.
DOOR_RAW_OPEN = 1
# Owner-confirmed ROM of the fourth probe (near-door position).
T4_ROM = "283BE5C9000000A9"
# Interlock display label (honesty rule): the as-built hardware has NO
# separate U6 interlock (owner design decision 2026-11-13); the dashboard
# says NOT FITTED — it never claims a fitted or closed contact. Overridable
# for a future build that carries a real loop.
INTERLOCK_LABEL = os.environ.get(
    "CG_INTERLOCK_LABEL",
    "NOT FITTED — owner design decision (supervised operation)")
# CG_LEADER_SYNC_STALE_MS (delivered constant): the device drops its anchor
# fail-closed without a fresh accepted sync inside this window.
SYNC_STALE_S = 60.0
# Freshness budget for presenting a frame as current.
FRAME_MAX_AGE_S = 15.0
# Delivered constants for the latency model (reported, not changed).
DEBOUNCE_MS = 50
POLL_MAX_GAP_MS = 15

FRAME_FIELD = re.compile(r"([a-z_0-9]+)=([^ ]+)")


def _parse_frame(frame: str) -> dict:
    return dict(FRAME_FIELD.findall(frame))


def _num(raw):
    try:
        v = float(raw)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceState:
    """Latest decoded device facts, maintained from the live MQTT stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.latest: dict | None = None
        self.retired_boots: set[str] = set()
        self.history: deque = deque(maxlen=180)
        self.last_capability: dict | None = None       # NETCMD challenge line
        self.last_sync_accepted: dict | None = None    # SYNC ACCEPTED record
        self.sync_accepted_count = 0
        self.sync_rejected_count = 0
        self.frames_seen = 0
        self.door_levels: dict[str, set] = {}          # boot_id -> raw levels seen
        self.door_edges: deque = deque(maxlen=40)      # per-edge latency records
        self._last_door_transitions: dict[str, int] = {}  # boot_id -> last seen count

    # -- stream handlers ---------------------------------------------------
    def on_telemetry(self, payload: dict, received: datetime | None = None) -> None:
        received = received or _now()
        source = payload.get("serial_source") or {}
        frame = source.get("frame")
        gateway_received = _timestamp(source.get("gateway_received_at"))
        boot = payload.get("boot_id")
        seq = payload.get("seq")
        if (payload.get("device_id") != DEVICE or payload.get("replay") is not False
                or payload.get("is_replay") or payload.get("synthetic") or not isinstance(frame, str)
                or gateway_received is None or not 0 <= (received - gateway_received).total_seconds() <= FRAME_MAX_AGE_S
                or not isinstance(boot, str) or not boot or type(seq) is not int or seq < 0):
            return
        fields = _parse_frame(frame)
        if fields.get("device_id") != DEVICE or fields.get("boot_id") != boot or _int(fields.get("seq")) != seq:
            return
        decoded = {
            "seq": seq,
            "boot_id": boot,
            "received_at": _iso(gateway_received),
            "uptime_ms": payload.get("uptime_ms"),
            "t1_c": _num((payload.get("thermal") or {}).get("t1")),
            "t2_c": _num((payload.get("thermal") or {}).get("t2")),
            "t2_role": (payload.get("thermal") or {}).get("t2_role"),
            "t3_c": _num((payload.get("thermal") or {}).get("t3")),
            "t_air_c": _num((payload.get("environment") or {}).get("t_air")),
            "rh_pct": _num((payload.get("environment") or {}).get("rh")),
            "voltage_v": _num((payload.get("electrical") or {}).get("voltage_v")),
            "current_a": _num((payload.get("electrical") or {}).get("current_a")),
            "power_w": _num((payload.get("electrical") or {}).get("power_w")),
            "energy_wh": _num((payload.get("electrical") or {}).get("energy_wh")),
            "actuation": payload.get("actuation") or {},
            "quality": payload.get("quality") or {},
            # raw-frame evidence, decoded verbatim from the device's own line
            "t4_c": _num(fields.get("raw_spare_c")),
            "t4_status": fields.get("raw_spare_status"),
            "t4_rom": fields.get("spare_rom"),
            "probes_valid": fields.get("probes_valid"),
            "probes_expected": fields.get("probes_expected"),
            "role_status": fields.get("role_status"),
            "door_raw": _int(fields.get("door_raw")),
            "door_open_firmware": _num(fields.get("door_open")),
            "door_status": fields.get("door_status"),
            "door_quality": fields.get("door_quality"),
            "door_transitions": _int(fields.get("door_transitions")),
            "door_cycles": _int(fields.get("door_cycles")),
            "fault_code": fields.get("fault_code"),
            "fault_reason": fields.get("fault_reason"),
            "tec_state": fields.get("tec_state"),
            "output_stage": fields.get("output_stage"),
            "timestamp_utc": fields.get("timestamp_utc"),
            "timestamp_utc_source": fields.get("timestamp_utc_source"),
        }
        decoded["proxy_seen_at"] = _iso(received)
        new_edge = None
        with self._lock:
            previous = self.latest
            if boot in self.retired_boots:
                return
            if previous is not None:
                if gateway_received <= datetime.fromisoformat(previous["received_at"]):
                    return
                if boot == previous["boot_id"]:
                    if seq <= previous["seq"]:
                        return
                else:
                    self.retired_boots.add(previous["boot_id"])
                    self.door_levels.clear()
                    self._last_door_transitions.clear()
                    self.last_sync_accepted = None
                    self.last_capability = None
                    self.sync_accepted_count = self.sync_rejected_count = 0
            if decoded["door_raw"] in (0, 1):
                self.door_levels.setdefault(boot, set()).add(decoded["door_raw"])
            prev_transitions = self._last_door_transitions.get(boot)
            if (decoded["door_transitions"] is not None and prev_transitions is not None
                    and decoded["door_transitions"] > prev_transitions):
                # A committed edge surfaced in THIS frame: the edge occurred
                # between the previous frame's reception and now. The wait for
                # the 1 Hz frame dominates; the transport after it is measured.
                new_edge = {
                    "boot_id": boot,
                    "detected_at": _iso(received),
                    "transitions": decoded["door_transitions"],
                    "frame_seq": decoded["seq"],
                    "frame_uptime_ms": decoded["uptime_ms"],
                    # Bound: the edge happened at most one frame period ago.
                    "frame_wait_bound_ms": 1000,
                    "raw_after": decoded["door_raw"],
                }
            self._last_door_transitions[boot] = decoded["door_transitions"] or 0
            self.latest = decoded
            self.history.append(decoded)
            self.frames_seen += 1
            if new_edge:
                # transport: this frame's gateway timestamp vs proxy receipt
                if decoded["received_at"]:
                    try:
                        gw = datetime.fromisoformat(decoded["received_at"])
                        new_edge["gateway_to_proxy_ms"] = round(
                            (received - gw).total_seconds() * 1000, 1)
                    except ValueError:
                        pass
                self.door_edges.append(new_edge)

    def on_diag(self, line: str) -> None:
        if "status=READY" in line and "challenge=" in line:
            fields = _parse_frame(line)
            record = {
                "challenge": fields.get("challenge"),
                "transport": fields.get("transport"),
                "seen_at": _iso(_now()),
            }
            with self._lock:
                self.last_capability = record
            return
        if "event=SYNC" in line:
            accepted = "result=ACCEPTED" in line
            fields = _parse_frame(line)
            host_ms = _int(fields.get("host"))
            record = {
                "host_utc": datetime.fromtimestamp(host_ms / 1000, tz=timezone.utc).isoformat()
                if host_ms is not None else None,
                "anchor_uptime_ms": _int(fields.get("anchor_uptime")),
                "seen_at": _iso(_now()),
            }
            with self._lock:
                if accepted:
                    self.last_sync_accepted = record
                    self.sync_accepted_count += 1
                else:
                    self.sync_rejected_count += 1

    # -- views ---------------------------------------------------------------
    def _door_view(self, latest: dict, levels: set) -> dict:
        device_transitions = latest.get("door_transitions") or 0
        attested = (levels == {0, 1}) or device_transitions >= 1
        device_door_ok = latest.get("door_status") == "OK"
        if latest.get("door_raw") not in (0, 1):
            state, reason = "NO_DOOR_FRAME_YET", "no door field in the stream yet"
        elif not attested or not device_door_ok:
            state = "AWAITING BOOT ATTESTATION"
            reason = (f"device reports door_status={latest.get('door_status')} with "
                      f"transitions={device_transitions}; both raw levels must appear in THIS boot")
        else:
            state = "OPEN" if latest["door_raw"] == DOOR_RAW_OPEN else "CLOSED"
            reason = "owner-verified polarity applied to the attested raw signal"
        mapping_conflict = (state in ("OPEN", "CLOSED")
                            and latest.get("door_open_firmware") is not None
                            and ((state == "OPEN") != (latest["door_open_firmware"] == 1)))
        mapping_note = ("the device door_open DISAGREES with the recalibrated "
                        "polarity (the device maps the other way); door features "
                        "stay suspended until the mapping is corrected through "
                        "the auditable staging build and flashed with owner GO"
                        ) if mapping_conflict else (
            "device door_open agrees with the recalibrated polarity "
            "(commissioning build CG_DOOR_RAW_OPEN_LEVEL=1: "
            "raw 0 = CLOSED, raw 1 = OPEN)")
        return {
            "state": state,
            "reason": reason,
            "raw": latest.get("door_raw"),
            "polarity_rule": "raw 0 = CLOSED, raw 1 = OPEN (owner live observation 2026-11-13; supersedes the earlier raw0=OPEN record)",
            "attested_this_boot": attested,
            "levels_seen_this_boot": sorted(levels),
            "device_door_status": latest.get("door_status"),
            "device_door_quality": latest.get("door_quality"),
            "transitions": latest.get("door_transitions"),
            "cycles": latest.get("door_cycles"),
            "device_mapping_conflict": mapping_conflict,
            "device_mapping_note": mapping_note,
            "owner_action_required": None if attested else
            "owner opens and closes the door exactly once in this boot so both raw levels appear",
        }

    def _clock_view(self, latest: dict, accepted: dict | None,
                    capability: dict | None, accepted_n: int, rejected_n: int) -> dict:
        verdict, age_s, detail = "UNANCHORED", None, "no SYNC ACCEPTED record yet"
        if accepted:
            seen = datetime.fromisoformat(accepted["seen_at"])
            age_s = round((_now() - seen).total_seconds(), 1)
            detail = (f"last device-accepted host stamp {accepted['host_utc']}; "
                      f"{accepted_n} accepted / {rejected_n} rejected this session")
            if age_s <= SYNC_STALE_S:
                verdict = "ANCHORED"
            else:
                verdict = f"STALE_{int(age_s)}S"
                detail += f"; device drops the anchor fail-closed after {SYNC_STALE_S:.0f}s"
        return {
            "state": verdict,
            "age_s": age_s,
            "detail": detail,
            "diagnostic_seen": bool(capability),
            "frame_timestamp_label": latest.get("timestamp_utc"),
            "frame_timestamp_source": latest.get("timestamp_utc_source"),
            "note": "delivered TELEM frames carry timestamp_utc=UNAVAILABLE (no wall-clock "
                    "field in the delivered producer); command expiry instead uses this "
                    "anchor, and ACKs independently report device time_sync_state",
        }

    def live(self) -> dict:
        with self._lock:
            latest = dict(self.latest) if self.latest else None
            levels = set(self.door_levels.get((latest or {}).get("boot_id") or "", set()))
            capability = dict(self.last_capability) if self.last_capability else None
            accepted = dict(self.last_sync_accepted) if self.last_sync_accepted else None
            accepted_n, rejected_n = self.sync_accepted_count, self.sync_rejected_count
            frames_seen = self.frames_seen

        if latest is None:
            return {
                "device": DEVICE,
                "telemetry": None,
                "fresh": False,
                "t4": {"role": "NEAR_DOOR", "qualified": False,
                       "reason": "NO_DEVICE_FRAME_YET"},
                "door": {"state": "NO_DEVICE_FRAME_YET",
                         "owner_action_required": "no frame has arrived; check the gateway"},
                "clock": {"state": "UNANCHORED", "reason": "no sync evidence yet"},
            }

        age = (_now() - datetime.fromisoformat(latest["received_at"])).total_seconds()
        fresh = 0 <= age <= FRAME_MAX_AGE_S

        # T4: the spare probe; owner-confirmed near-door role and ROM.
        rom = latest.get("t4_rom")
        rom_match = rom == T4_ROM
        status_ok = latest.get("t4_status") == "OK"
        value = latest.get("t4_c")
        t4_ok = bool(rom_match and status_ok and value is not None)
        live = {
            "device": DEVICE,
            "source": "REAL_SERIAL",
            "evidence_source": "mqtt device stream + leader-diag (device's own bytes)",
            "interlock": INTERLOCK_LABEL,
            "fresh": fresh,
            "frame_age_s": round(age, 1),
            "stale_note": None if fresh else
            f"last frame {age:.0f}s ago (> {FRAME_MAX_AGE_S:.0f}s): values are last-known, not live",
            "frames_seen_this_session": frames_seen,
            "telemetry": latest,
            "t4": {
                "role": "NEAR_DOOR",
                "rom": rom,
                "rom_expected": T4_ROM,
                "qualified": t4_ok,
                "value_c": value if t4_ok else None,
                "reason": None if t4_ok else (
                    f"ROM MISMATCH: device reports {rom}, expected {T4_ROM}" if not rom_match
                    else f"frame marks raw_spare_status={latest.get('t4_status')}"),
            },
            "door": self._door_view(latest, levels),
            "clock": self._clock_view(latest, accepted, capability, accepted_n, rejected_n),
        }
        return live

    def history_view(self, n: int) -> dict:
        with self._lock:
            items = list(self.history)[-n:]
        return {"items": items}

    def door_latency(self) -> dict:
        with self._lock:
            edges = [dict(e) for e in self.door_edges]
        # Enrich with the delivered API's own persistence timing (Member C
        # backend_received_at per seq) via the passthrough - no member change.
        api_rows = {}
        try:
            request = urllib.request.Request(
                f"{BACKEND}{DEVICE_API}/telemetry?limit=120",
                headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=8) as response:
                for item in json.loads(response.read()).get("items", []):
                    api_rows[(item["boot_id"], item["seq"])] = item.get("backend_received_at")
        except Exception:  # noqa: BLE001 - enrichment is best-effort
            pass
        for e in edges:
            persisted = api_rows.get((e.get("boot_id"), e.get("frame_seq")))
            if persisted and e.get("detected_at"):
                try:
                    delta = (datetime.fromisoformat(persisted)
                             - datetime.fromisoformat(e["detected_at"])).total_seconds()
                    e["api_persist_delta_ms"] = round(delta * 1000, 1)
                except ValueError:
                    pass
        return {
            "model": (
                "edge -> GPIO sample <=%dms -> debounce %dms (symmetric) -> next 1 Hz frame "
                "(0-1000 ms, delivered rate) -> serial -> MQTT -> proxy (SSE ~0 ms) -> render. "
                "The physical->GPIO leg is bounded, not measured: the device frame carries no "
                "per-edge timestamp (delivered firmware; no new event channel added)."
            ) % (POLL_MAX_GAP_MS, DEBOUNCE_MS),
            "edges": edges,
            "note": "frame_wait_bound_ms bounds how long the edge may have waited for the "
                    "1 Hz frame; gateway_to_proxy_ms and api_persist_delta_ms are measured "
                    "after it (negative persist delta = the backend persisted before this "
                    "proxy's MQTT delivery - QoS ordering, both sub-second).",
        }



STATE = EvidenceState()


def start_subscriber():
    import paho.mqtt.client as mqtt  # noqa: PLC0415

    def on_connect(client, _userdata, _flags, reason_code, _properties):
        if reason_code == 0:
            client.subscribe([(TOPIC_TELEM, 1), (TOPIC_DIAG, 1)])

    def on_message(_client, _userdata, msg):
        if msg.retain:
            return
        try:
            if msg.topic == TOPIC_TELEM:
                STATE.on_telemetry(json.loads(msg.payload))
            elif msg.topic == TOPIC_DIAG:
                STATE.on_diag(msg.payload.decode("ascii", "replace"))
        except (AttributeError, TypeError, ValueError):
            return

    host = os.environ.get("MQTT_HOST", "127.0.0.1")
    port = int(os.environ.get("MQTT_PORT", "18830"))
    username = os.environ.get("CG_DASHBOARD_MQTT_USERNAME")
    password = os.environ.get("CG_DASHBOARD_MQTT_PASSWORD")
    if password and not username:
        raise ValueError("CG_DASHBOARD_MQTT_PASSWORD requires CG_DASHBOARD_MQTT_USERNAME")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"leader-dashboard-proxy-{os.getpid()}")
    if username:
        client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(host, port, keepalive=30)
    client.loop_start()
    return client


STATE_PATH = REPO_ROOT / "runtime" / "leader"
DOOR_EVENTS_FILE = Path(os.environ.get("CG_EVENTS_FILE", STATE_PATH / "door-events.jsonl"))
SHADOW_MAX_AGE_S = 10.0


def _db_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg", "postgresql") if url else None


def series_view(minutes: int) -> dict:
    """Real historical series for the thermal chart, Leader-corrected.

    Decoded values come from the delivered backend API (no member change),
    paged with start_time/order=asc to cover the whole window. The door raw
    level and the T4 spare probe are re-derived from each frame's OWN text
    (the device's bytes), so the chart's door markers use the recalibrated
    polarity and per-boot attestation - never the device's inverted
    door_open mapping, and never T2 as a chamber value. Events are computed
    at full resolution; the plot points are stride-sampled only when the
    window exceeds the API page cap, always keeping transition frames.
    """
    minutes = max(1, min(120, minutes))
    now = _now()
    start = (now - timedelta(minutes=minutes)).isoformat()
    end = now.isoformat()
    items: list[dict] = []
    offset = 0
    while True:
        request = urllib.request.Request(
            f"{BACKEND}{DEVICE_API}/telemetry?limit=1000&offset={offset}"
            f"&order=asc&start_time={urllib.parse.quote(start)}&end_time={urllib.parse.quote(end)}",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            page = json.loads(response.read()).get("items", [])
        items.extend(page)
        if len(page) < 1000 or len(items) >= 7200:
            break
        offset += 1000
    points = []
    for item in items:
        meas = item.get("measurements") or {}
        thermal = meas.get("thermal") or {}
        env = meas.get("environment") or {}
        electrical = meas.get("electrical") or {}
        actuation = meas.get("actuation") or {}
        provenance = item.get("provenance") or {}
        quality = item.get("quality") or {}
        source = "REPLAY" if (item.get("timing") or {}).get("status") == "REPLAY" else (
            "REAL_SERIAL" if provenance.get("serial_source") else "BACKEND")
        points.append({
            "raw_id": provenance.get("raw_id"),
            "source": source,
            "t": item.get("backend_received_at"),
            "seq": item.get("seq"),
            "boot_id": item.get("boot_id"),
            "t1_c": _num(thermal.get("t1_c")) if quality.get("thermal") == "VALID" else None,
            "t3_c": _num(thermal.get("t3_c")) if quality.get("thermal") == "VALID" else None,
            "t_air_c": _num(env.get("t_air_c")) if quality.get("environment") == "VALID" else None,
            "cooling": actuation.get("cooling"),
            "duty": actuation.get("duty"),
            "current_a": _num(electrical.get("current_a")) if quality.get("electrical") == "VALID" else None,
            "power_w": _num(electrical.get("power_w")) if quality.get("electrical") == "VALID" else None,
            "quality": (item.get("quality") or {}).get("overall"),
            "door_raw": None, "t4_c": None,
        })
    raw_status = "UNAVAILABLE"
    raw_ids = [p["raw_id"] for p in points if isinstance(p["raw_id"], int)]
    url = _db_url()
    if raw_ids and url:
        try:
            import psycopg

            with psycopg.connect(url, connect_timeout=5) as conn:
                conn.read_only = True
                rows = conn.execute(
                    "SELECT id, raw_json->'serial_source'->>'frame' FROM telemetry_raw "
                    "WHERE device_id = %s AND id = ANY(%s)",
                    (DEVICE, raw_ids),
                ).fetchall()
            frames = dict(rows)
            raw_status = "AVAILABLE"
            for point in points:
                fields = _parse_frame(frames.get(point["raw_id"]) or "")
                if (fields.get("device_id") != DEVICE or fields.get("boot_id") != point["boot_id"]
                        or _int(fields.get("seq")) != point["seq"]):
                    continue
                door_raw = _int(fields.get("door_raw"))
                if door_raw in (0, 1) and fields.get("door_status") == "OK":
                    point["door_raw"] = door_raw
                if fields.get("spare_rom") == T4_ROM and fields.get("raw_spare_status") == "OK":
                    point["t4_c"] = _num(fields.get("raw_spare_c"))
        except Exception:  # Raw store absence leaves the T4 field unavailable.
            pass
    # Per-boot attestation inside this window (never carried across boots).
    levels_by_boot: dict[str, set] = {}
    for p in points:
        if p["door_raw"] is not None:
            levels_by_boot.setdefault((p["source"], p["boot_id"]), set()).add(p["door_raw"])
    door_events: list[dict] = []
    cooling_events: list[dict] = []
    transition_idx: set[int] = set()
    prev = None
    for i, p in enumerate(points):
        attested = levels_by_boot.get((p["source"], p["boot_id"])) == {0, 1}
        p["door_attested"] = attested
        if p["door_raw"] is not None and attested:
            p["door_state"] = "OPEN" if p["door_raw"] == DOOR_RAW_OPEN else "CLOSED"
        else:
            p["door_state"] = None
        if None not in (p["t1_c"], p["t3_c"], p["t4_c"]):
            p["chamber_mean_c"] = round((p["t1_c"] + p["t3_c"] + p["t4_c"]) / 3.0, 3)
        if prev is not None and (p["boot_id"], p["source"]) == (prev["boot_id"], prev["source"]):
            changed = False
            if p["door_state"] and prev["door_state"] and p["door_state"] != prev["door_state"]:
                door_events.append({"t": p["t"], "seq": p["seq"],
                                    "kind": f"DOOR_{p['door_state']}"})
                changed = True
            if p["cooling"] and prev["cooling"] and p["cooling"] != prev["cooling"]:
                cooling_events.append({"t": p["t"], "seq": p["seq"],
                                       "kind": f"TEC_{p['cooling']}"})
                changed = True
            if changed:
                transition_idx.update({i - 1, i})
        prev = p
    # Plot-point budget: stride-sample long windows but never drop the
    # frames adjacent to a door/cooling transition (the event shape stays
    # exact; gaps remain gaps, nothing is interpolated).
    total = len(points)
    if total > 1000:
        stride = -(-total // 1000)
        keep = set(range(0, total, stride)) | transition_idx
        points = [points[i] for i in sorted(keep)]
    return {"points": points, "raw_status": raw_status, "door_events": door_events,
            "cooling_events": cooling_events,
            "window_minutes": minutes, "frames_in_window": total,
            "polarity_rule": f"raw 0 = CLOSED, raw {DOOR_RAW_OPEN} = OPEN "
                             "(owner live observation; per-boot attestation)"}


def _load_inference():
    """Load the inference bridge lazily so the dashboard still starts if its
    optional YAML/XGBoost dependencies are absent; the panel then shows a
    truthful BLOCKED status instead of taking the whole dashboard down."""
    try:  # imported as integration.leader_dashboard_server (tests / package use)
        from .leader_live_inference import InferenceUnavailable, live_prediction
    except ImportError:  # executed directly as backend/integration/leader_dashboard_server.py
        from leader_live_inference import InferenceUnavailable, live_prediction
    return InferenceUnavailable, live_prediction


def live_prediction(*args, **kwargs):
    """Indirection kept patchable for tests; resolved lazily at call time."""
    _unavailable, predict = _load_inference()
    return predict(*args, **kwargs)


def xgb_view() -> dict:
    """Read-only demo score from the selected frozen artifact.

    Computed on GET with a module-cached model; never persists or registers a
    prediction. This is deliberately separate from the door-latency timing
    model reported above.
    """
    try:
        return live_prediction(
            DEVICE, model_version=DEMO_MODEL_VERSION, model_dir=DEMO_MODEL_DIR)
    except Exception as exc:  # noqa: BLE001 - the panel shows the refusal
        unavailable = type(exc).__name__ == "InferenceUnavailable"
        return {
            "mode": "DEMO_ONLY_SHADOW", "demo_only": True,
            "score_status": ("BLOCKED_MODEL_UNAVAILABLE" if unavailable
                             else "BLOCKED_ENDPOINT_ERROR"),
            "score": None,
            "error": "forecast unavailable",
            "note": "no score is presented; see status",
        }


# The forecast computation opens a fresh DB connection and rebuilds features
# over the current-boot history on every call (seconds, growing with history).
# Serving it on the hot GET path stalled the controller's sequential observer
# past the 3 s device lease. Refresh it in the background and serve the last
# result instantly; re-age the anchor at serve time so a stalled refresh still
# fails closed downstream. Mirrors FRAME_MAX_AGE_S / MAX_FORECAST_AGE_S (15 s).
_FORECAST_STALE_AGE_S = 15.0
_XGB_REFRESH_S = 2.0
_xgb_cache_lock = threading.Lock()
_xgb_cache_payload: dict | None = None
_xgb_cache_anchor: datetime | None = None
_xgb_cache_computed_at: datetime | None = None


def _refresh_xgb_cache() -> None:
    global _xgb_cache_payload, _xgb_cache_anchor, _xgb_cache_computed_at
    computed_at = _now()
    payload = xgb_view()
    anchor = _timestamp(payload.get("anchor_utc"))
    with _xgb_cache_lock:
        _xgb_cache_payload = payload
        _xgb_cache_anchor = anchor
        _xgb_cache_computed_at = computed_at


def _xgb_refresh_loop() -> None:
    while True:
        _refresh_xgb_cache()
        time.sleep(_XGB_REFRESH_S)


def xgb_view_cached() -> dict:
    """Instant read of the background-refreshed demo forecast.

    Never blocks on the inference/DB computation. The anchor age is recomputed
    now, so if the refresh stalls the forecast ages out and is labelled stale
    (the controller independently fails closed past its own max forecast age).
    """
    with _xgb_cache_lock:
        payload = _xgb_cache_payload
        anchor = _xgb_cache_anchor
        computed_at = _xgb_cache_computed_at
    if payload is None:
        return {
            "mode": "DEMO_ONLY_SHADOW", "demo_only": True,
            "score_status": "BLOCKED_FORECAST_WARMING",
            "forecast_status": "BLOCKED_FORECAST_WARMING",
            "score": None, "predicted_temperature_c": None,
            "note": "forecast cache is warming; no score is presented yet",
        }
    out = dict(payload)
    out.pop("model_dir", None)
    now = _now()
    if anchor is not None:
        age_s = (now - anchor).total_seconds()
        out["frame_age_s"] = round(age_s, 1)
        out["fresh"] = 0 <= age_s <= _FORECAST_STALE_AGE_S
        out["as_of_utc"] = now.isoformat()
        if not out["fresh"]:
            out["predicted_temperature_c"] = None
            out["predicted_delta_c"] = None
            out["score"] = None
            if out.get("forecast_status") == "OK_EXPERIMENTAL_DEMO":
                out["forecast_status"] = "STALE_NO_FORECAST"
            if out.get("score_status") in ("OK_EXPERIMENTAL_DEMO", "OK_DEMO_ONLY"):
                out["score_status"] = "STALE_NO_FORECAST"
    if computed_at is not None:
        out["cache_age_s"] = round((now - computed_at).total_seconds(), 1)
    return out


def door_events_view(limit: int = 120) -> dict:
    """Read the shadow journal without granting execution authority."""
    events = []
    try:
        with DOOR_EVENTS_FILE.open("r", encoding="utf-8") as stream:
            for line in deque(stream, maxlen=limit):
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("mode") == "shadow":
                    events.append(event)
    except OSError:
        pass
    return {"source": "SHADOW", "events": events}


def shadow_view() -> dict:
    live = STATE.live()
    telemetry = live.get("telemetry") or {}
    waiting = {"source": "SHADOW", "status": "WAITING_FOR_CURRENT_POLICY"}
    if not live.get("fresh"):
        return waiting
    events = door_events_view(limit=1)["events"]
    if not events:
        return waiting
    event = events[0]
    observed = _timestamp(event.get("ts"))
    if (observed is None or not 0 <= (_now() - observed).total_seconds() <= SHADOW_MAX_AGE_S
            or event.get("device_id") != DEVICE or event.get("boot_id") != telemetry["boot_id"]
            or type(event.get("seq")) is not int or event["seq"] > telemetry["seq"]
            or event.get("event") != "DOOR_TICK"):
        return waiting
    return {"source": "SHADOW", "status": "CURRENT_POLICY", **{
        key: event.get(key) for key in ("ts", "boot_id", "seq", "door_action",
                                        "policy_intent", "target_c", "door_state", "door_reason")
    }}


def read_desired_setpoint() -> dict | None:
    """Read the operator-provisioned desired cooling target (desired state only).

    A policy input, never an actuation grant: it carries no arm flag, boot token
    or command authority. Missing/invalid => None, so the orchestrator falls back
    to its environment policy band rather than inventing a target.
    """
    try:
        raw = json.loads(SETPOINT_FILE.read_text(encoding="utf-8"))
        value = float(raw["setpoint_c"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not math.isfinite(value) or not SETPOINT_MIN_C <= value <= SETPOINT_MAX_C:
        return None
    return {"setpoint_c": value, "updated_at": raw.get("updated_at"),
            "source": "OPERATOR_DESIRED"}


def _write_desired_setpoint(value: float) -> dict:
    record = {"setpoint_c": value, "updated_at": _now().isoformat(), "source": "OPERATOR"}
    SETPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETPOINT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    tmp.replace(SETPOINT_FILE)
    return record


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.startswith("/api/leader/stream"):
            self._stream()
            return
        if self.path.startswith("/api/leader/"):
            self._leader()
            return
        if urllib.parse.urlsplit(self.path).path in (
            f"{DEVICE_API}/state", f"{DEVICE_API}/telemetry", "/api/runtime/readiness",
        ):
            self._proxy()
            return
        if self.path in ("/", "/index.html"):
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        self.close_connection = True
        # Drain the (bounded) request body before any early response so closing
        # the connection never aborts the client socket mid-send (WinError 10053).
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if 0 < length <= 4096 else b""
        if urllib.parse.urlsplit(self.path).path == "/api/leader/setpoint":
            self._set_setpoint(body, length)
            return
        self.send_error(405, "Dashboard is read only")

    def _set_setpoint(self, body: bytes, length: int) -> None:
        """Authenticated desired-setpoint write; updates desired state only.

        Fail-closed operator authorization (env-provisioned token, constant-time
        compare) — loopback alone is not authorization. A successful write never
        grants ARM/START or dispatches a device command: the dashboard has no
        command path. Physical actuation stays with the supervised gateway
        console and Member D / Leader policy evaluation.
        """
        if not OPERATOR_TOKEN:
            self._json({"error": "operator authorization not provisioned"}, code=503)
            return
        header = self.headers.get("Authorization", "")
        supplied = header[7:] if header.startswith("Bearer ") else ""
        if not supplied or not hmac.compare_digest(
                supplied.encode("utf-8"), OPERATOR_TOKEN.encode("utf-8")):
            self._json({"error": "operator authorization required"}, code=401)
            return
        if length <= 0 or length > 4096:
            self._json({"error": "a JSON body with setpoint_c is required"}, code=400)
            return
        try:
            raw = json.loads(body)
            value = float(raw["setpoint_c"])
        except (ValueError, KeyError, TypeError):
            self._json({"error": "setpoint_c must be a number"}, code=400)
            return
        if not math.isfinite(value) or not SETPOINT_MIN_C <= value <= SETPOINT_MAX_C:
            self._json({"error": f"setpoint_c must be within "
                                 f"{SETPOINT_MIN_C:.0f}-{SETPOINT_MAX_C:.0f} C"}, code=400)
            return
        try:
            record = _write_desired_setpoint(value)
        except OSError as exc:
            self._json({"error": f"could not write setpoint: {exc}"}, code=500)
            return
        self._json({"ok": True, "setpoint_c": record["setpoint_c"], "actuation": "NONE",
                    "note": "desired target updated; no ARM/START dispatched"})

    def log_message(self, *args) -> None:  # silence the console
        pass

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # client vanished mid-request; not a server error

    def _json(self, payload: dict | list, code: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self) -> None:
        """Server-Sent Events: hydrate the client with the current frame
        immediately, then push each new frame the moment MQTT delivers it.
        Reconnecting clients (page refresh, browser reconnect after a proxy
        or gateway restart) therefore reconcile to the latest CURRENT-BOOT
        frame on the first event instead of waiting on a blank stream."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            last_frame = None
            sent_initial = False
            last_keepalive = time.time()
            while True:
                # Hydrate: the very first event after connect carries the
                # current evidence view (even when no frame has arrived yet,
                # so the page shows the reason instead of a blank stream).
                # Afterwards each genuinely new frame pushes immediately.
                # Same shape as /api/leader/live, so the page renders SSE
                # and polling frames through one code path.
                payload = STATE.live()
                telemetry = payload.get("telemetry") or {}
                identity = (telemetry.get("boot_id"), telemetry.get("seq"), payload["fresh"])
                now = time.time()
                if not sent_initial or identity != last_frame:
                    sent_initial = True
                    last_frame = identity
                    last_keepalive = now
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                    self.wfile.flush()
                elif now - last_keepalive >= 15.0:
                    # Comment frame: keeps intermediaries from timing the
                    # connection out while the device is quiet.
                    last_keepalive = now
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return
        except Exception:  # noqa: BLE001 - one bad client must not kill the server
            return

    def _leader(self) -> None:
        if self.path == "/api/leader/live":
            self._json(STATE.live())
            return
        if self.path.startswith("/api/leader/history"):
            n = 60
            if "n=" in self.path:
                try:
                    n = max(1, min(180, int(self.path.split("n=", 1)[1].split("&")[0])))
                except ValueError:
                    pass
            self._json(STATE.history_view(n))
            return
        if self.path.startswith("/api/leader/door-latency"):
            self._json(STATE.door_latency())
            return
        if self.path.startswith("/api/leader/series"):
            minutes = 15
            if "minutes=" in self.path:
                try:
                    minutes = int(self.path.split("minutes=", 1)[1].split("&")[0])
                except ValueError:
                    pass
            try:
                self._json(series_view(minutes))
            except Exception:  # noqa: BLE001 - the chart shows the error
                self._json({"error": "series unavailable",
                            "points": [], "door_events": [],
                            "cooling_events": []}, code=502)
            return
        if self.path.startswith("/api/leader/door-events"):
            self._json(door_events_view())
            return
        if self.path.startswith("/api/leader/xgb") or self.path.startswith("/api/leader/prediction"):
            payload = xgb_view_cached()
            # Model/feature refusals are valid JSON evidence, not server errors.
            self._json(payload, code=200)
            return
        if self.path == "/api/leader/shadow":
            self._json(shadow_view())
            return
        if self.path == "/api/leader/setpoint":
            desired = read_desired_setpoint()
            self._json({"setpoint_c": desired["setpoint_c"] if desired else None,
                        "updated_at": desired["updated_at"] if desired else None,
                        "source": "OPERATOR_DESIRED", "actuation": "NONE"})
            return
        self.send_error(404)

    def _proxy(self) -> None:
        url = BACKEND + self.path
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = response.read()
                code = response.status
        except urllib.error.HTTPError as exc:
            payload, code = json.dumps({"error": "backend request failed"}).encode(), exc.code
        except Exception:  # noqa: BLE001 - the dashboard shows the failure
            payload, code = json.dumps({"error": "backend unreachable"}).encode(), 502
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(description="ColdGuard live dashboard")
    _parser.add_argument(
        "--model-dir", default=DEMO_MODEL_DIR,
        help="demo model directory (default: $COLDGUARD_DEMO_MODEL_DIR or bundled experimental forecast)")
    _parser.add_argument(
        "--model-version", default=DEMO_MODEL_VERSION,
        help="expected manifest model version (default: selected manifest)")
    _args = _parser.parse_args()
    DEMO_MODEL_DIR = _args.model_dir
    DEMO_MODEL_VERSION = _args.model_version
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as exc:
        # Bind failure = another instance already owns the port and its MQTT
        # subscriber. Exit instead of lingering as a duplicate subscriber
        # fighting the winner over the same MQTT client id.
        print(f"port {PORT} unavailable ({exc}); another dashboard instance "
              f"is already running - exiting", file=sys.stderr, flush=True)
        sys.exit(1)
    subscriber = start_subscriber()
    threading.Thread(target=_xgb_refresh_loop, daemon=True, name="leader-xgb").start()
    print(f"ColdGuard dashboard on http://127.0.0.1:{PORT}/ (backend {BACKEND})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        subscriber.disconnect()
        subscriber.loop_stop()
        server.server_close()
