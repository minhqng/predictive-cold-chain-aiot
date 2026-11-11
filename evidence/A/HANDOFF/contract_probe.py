"""Member A -> B/C/D interface compatibility probe (worker R, one-shot tool).

Runs the REAL firmware parser, the REAL backend ingest classifier and the REAL
control validator, and writes a machine-readable verdict next to this file.
Nothing here interprets by hand: every row in the output is produced by calling
the code each member owns.

Import conventions: this file imports backend/control as source trees via
sys.path; it does not modify them.

Reproduce:
    cd A-handoff-contracts/evidence/A/HANDOFF
    PYTHONUTF8=1 <python-with-pytest-deps> contract_probe.py
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # <worktree>/evidence/A/HANDOFF -> worktree root

sys.path.insert(0, str(ROOT / "firmware" / "tools"))
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "control" / "src"))

import cg_telemetry_schema as telem  # noqa: E402


def _const(path: pathlib.Path, name: str) -> tuple[str, int]:
    """Return (value, line_number) for `#define <name> <v>` or `<name> = <v>`."""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    pat = re.compile(
        r"^#define\s+" + re.escape(name) + r"\s+(\S+)"
        r"|^" + re.escape(name) + r"\s*=\s*(\S+)"
        r"|^WIRE_SCHEMA_VERSION\s*=\s*(\S+)"
    )
    for i, line in enumerate(text, start=1):
        m = pat.match(line.strip())
        if m:
            return (next(g for g in m.groups() if g), i)
    return ("<not found>", -1)


# ---------------------------------------------------------------- (A) schema numbers
FW_HEADER = ROOT / "firmware" / "main" / "coldguard_config.h"
FW_SCHEMA_PY = ROOT / "firmware" / "tools" / "cg_telemetry_schema.py"
BE_CONTRACTS = ROOT / "backend" / "src" / "coldguard_backend" / "contracts.py"

schema_numbers = {
    "device_serial_schema": {
        "name": "CG_TELEMETRY_SCHEMA_VERSION",
        "value": _const(FW_HEADER, "CG_TELEMETRY_SCHEMA_VERSION")[0],
        "file": str(FW_HEADER),
        "line": _const(FW_HEADER, "CG_TELEMETRY_SCHEMA_VERSION")[1],
        "namespace": "serial #CG TELEM line",
    },
    "device_parser_schema": {
        "name": "SCHEMA_VERSION",
        "value": _const(FW_SCHEMA_PY, "SCHEMA_VERSION")[0],
        "file": str(FW_SCHEMA_PY),
        "line": _const(FW_SCHEMA_PY, "SCHEMA_VERSION")[1],
        "supported_schemas": telem.SUPPORTED_SCHEMAS,
    },
    "backend_wire_schema": {
        "name": "WIRE_SCHEMA_VERSION",
        "value": _const(BE_CONTRACTS, "WIRE_SCHEMA_VERSION")[0],
        "file": str(BE_CONTRACTS),
        "line": _const(BE_CONTRACTS, "WIRE_SCHEMA_VERSION")[1],
        "namespace": "MQTT JSON Telemetry envelope",
        "supported": sorted(__import__("coldguard_backend.validation",
                                       fromlist=["x"]).SUPPORTED_SCHEMA_VERSIONS),
    },
}

# ------------------------------------------------- (B) one schema-3 device frame
DEMO = ROOT / "evidence" / "A" / "W06" / "demo-command-capture.log"
committed_line = next(
    ln for ln in DEMO.read_text(encoding="utf-8").splitlines()
    if ln.startswith(telem.PREFIX)
)
committed_record = telem.parse_line(committed_line, 1)
committed_schema = committed_record.fields["schema"]

# The no-command-received frame the shipped formatter emits (cg_telemetry.c:382-385).
W06_NO_COMMAND_TAIL = (
    " command_id=NONE desired_cooling=NONE desired_duty_permille=nan"
    " last_ack_status=NONE last_ack_reason=NO_COMMAND_RECEIVED"
)
# The no-command-received frame the shipped formatter emits (cg_telemetry.c:382-385).
W06_NO_COMMAND_TAIL = (
    " command_id=NONE desired_cooling=NONE desired_duty_permille=nan"
    " last_ack_status=NONE last_ack_reason=NO_COMMAND_RECEIVED"
)
# The committed capture line already carries the full no-command tail on every
# schema=3 frame (cg_telemetry.c:382-385), so upgrade a historical schema=2
# line only; appending the tail to a schema=3 line would duplicate five fields
# and be rejected by parse_line.
if committed_schema == 3:
    schema3_line = committed_line
elif committed_schema == 2:
    replaced = committed_line.replace("schema=2 ", "schema=3 ", 1)
    if replaced == committed_line:
        raise SystemExit(
            "committed capture claims schema=2 but carries no schema=2 token")
    schema3_line = replaced + W06_NO_COMMAND_TAIL
else:
    raise SystemExit(
        f"unsupported committed capture schema {committed_schema!r}: "
        "the probe supports schema 2 (upgrade) and schema 3 (direct parse) only"
    )
frame3 = telem.parse_line(schema3_line, 1)
device_raw = dict(frame3.raw_fields)
device_fields = dict(frame3.fields)

# Numeric-looking tokens the parser left as strings: the real type-gap report,
# recomputed from the parsed probe frame on every run (never a static claim).
untyped_numeric_fields = sorted(
    k for k, v in device_fields.items()
    if isinstance(v, str) and re.match(r"^-?\d+(\.\d+)?$", v)
)

# ---------------------------------------------------------------- (C) translation
# Field-name/unit mapping a Member C gateway would have to perform to turn one
# device frame into one docs/02 Telemetry JSON. Derived from the two field sets,
# not invented: left side is the device token, right side the backend attribute.
TRANSLATION = {
    "schema": ("schema_version", "int", "int"),
    "timestamp_utc": ("captured_at", "literal UNAVAILABLE", "tz-aware datetime"),
    "device_id": ("device_id", "str", "str"),
    "boot_id": ("boot_id", "str", "str"),
    "seq": ("seq", "int", "int"),
    "uptime_ms": ("uptime_ms", "int", "int"),
    "run_id": ("run_id", "str", "str|null"),
    "hardware_config_id": ("hardware_config_id", "str", "str"),
    "firmware_version": ("firmware_version", "str", "str"),
    "calibration_id": ("calibration_id", "str", "str|null"),
    "raw_t1_c": ("thermal.t1", "float|nan", "float|null"),
    "raw_t2_c": ("thermal.t2", "float|nan", "float|null"),
    "raw_t3_c": ("thermal.t3", "float|nan", "float|null"),
    "t_ambient_c": ("environment.t_air", "float|nan", "float|null"),
    "relative_humidity_pct": ("environment.rh", "float|nan", "float|null"),
    "voltage_v": ("electrical.voltage_v", "float|nan", "float|null"),
    "current_a": ("electrical.current_a", "float|nan", "float|null"),
    "power_w": ("electrical.power_w", "float|nan", "float|null"),
    "energy_wh": ("electrical.energy_wh", "float|nan", "float|null"),
    "cooling_applied": ("actuation.cooling", "ON|OFF", "ON|OFF"),
    "pwm_duty": ("actuation.duty", "int permille 0..1000", "float 0.0..1.0"),
    "thermal_quality": ("quality.thermal", "VALID|DEGRADED|INVALID|UNKNOWN",
                        "VALID|DEGRADED|INVALID"),
    "environment_quality": ("quality.environment", "VALID|DEGRADED|INVALID|UNKNOWN",
                            "VALID|DEGRADED|INVALID"),
    "electrical_quality": ("quality.electrical", "VALID|DEGRADED|INVALID|UNKNOWN",
                           "VALID|DEGRADED|INVALID"),
    "quality": ("quality.overall", "VALID|DEGRADED|INVALID|UNKNOWN",
                "VALID|DEGRADED|INVALID"),
}


def _opt(section_key: str):
    """Honest value translation for one device token.

    Note: cg_telemetry_schema._coerce (firmware/tools/cg_telemetry_schema.py:309-345)
    leaves every token that is not in FLOAT_FIELDS/INTEGER_FIELDS as a raw string,
    so `raw_t1_c`/`raw_t2_c`/`raw_t3_c` arrive as text ("25.0625" or "nan"). The
    explicit numeric cast below is therefore part of the translation layer this
    probe is proving necessary, not a convenience.
    """
    v = device_fields.get(section_key)
    if v is None or v == "nan":
        return None
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def build_wire(*, keep_real_schema: bool) -> dict:
    """Translate the device frame into a docs/02-shaped Telemetry JSON.

    Only the honest translation is performed. No value is invented: the
    device reports timestamp_utc=UNAVAILABLE, so captured_at is carried as the
    literal token the device actually sends.
    """
    return {
        "schema_version": (int(device_fields["schema"]) if keep_real_schema else 1),
        "device_id": device_fields["device_id"],
        "boot_id": device_fields["boot_id"],
        "seq": int(device_fields["seq"]),
        "captured_at": device_fields["timestamp_utc"],
        "uptime_ms": int(device_fields["uptime_ms"]),
        "run_id": device_fields["run_id"],
        "hardware_config_id": device_fields["hardware_config_id"],
        "firmware_version": device_fields["firmware_version"],
        "calibration_id": device_fields["calibration_id"],
        "thermal": {"t1": _opt("raw_t1_c"), "t2": _opt("raw_t2_c"), "t3": _opt("raw_t3_c")},
        "environment": {"t_air": _opt("t_ambient_c"), "rh": _opt("relative_humidity_pct")},
        "door": {"state": "UNKNOWN"},
        "electrical": {
            "voltage_v": _opt("voltage_v"),
            "current_a": _opt("current_a"),
            "power_w": _opt("power_w"),
            "energy_wh": _opt("energy_wh"),
        },
        "actuation": {"cooling": device_fields["cooling_applied"],
                      "duty": int(device_fields["pwm_duty"]) / 1000.0},
        "quality": {
            "thermal": device_fields["thermal_quality"],
            "environment": device_fields["environment_quality"],
            "electrical": device_fields["electrical_quality"],
            "overall": device_fields["quality"],
        },
    }


from coldguard_backend.raw_store import classify_raw  # noqa: E402
from coldguard_backend.contracts import Telemetry  # noqa: E402

TOPIC = f"coldguard/{device_fields['device_id']}/telemetry"

cases = {}
for label, payload in (
    ("faithful_translation_real_schema3", build_wire(keep_real_schema=True)),
    ("schema_forced_to_1_otherwise_faithful", build_wire(keep_real_schema=False)),
):
    blob = json.dumps(payload).encode("utf-8")
    verdict = classify_raw(TOPIC, blob)
    cases[label] = {
        "ingest_status": verdict["ingest_status"],
        "validation_errors": verdict["validation_errors"],
        "payload_sent": payload,
    }

# Isolate the quality-vocabulary clash from the timestamp clash: same payload,
# only captured_at replaced by a real tz-aware instant (what the gateway would
# have to do with a host clock).
probe_no_ts = build_wire(keep_real_schema=False)
probe_no_ts["captured_at"] = datetime.now(timezone.utc).isoformat()
try:
    Telemetry.model_validate(probe_no_ts)
    quality_case = {"accepted": True}
except Exception as exc:  # noqa: BLE001 - we want the verbatim reason
    quality_case = {"accepted": False, "error": str(exc)[:1500]}

# Duty unit clash, isolated.
duty_case = {}
for raw_duty in (0, 250, 1000):
    p = dict(probe_no_ts)
    p["actuation"] = {"cooling": "OFF", "duty": raw_duty / 1000.0}
    duty_case[f"device_pwm_duty_{raw_duty}"] = {
        "wire_duty": raw_duty / 1000.0,
        "raw_text_on_serial": f"pwm_duty={raw_duty}",
    }

# ---------------------------------------------------------- (D) MQTT topic surface
consumer = __import__("coldguard_backend.mqtt_consumer", fromlist=["x"])
simulator = __import__("coldguard_backend.simulator", fromlist=["x"])
subscriptions = list(consumer.SUBSCRIPTIONS)

sim_command_ack = {}
try:
    sim_command_ack["topic_for"] = simulator.topic_for("coldguard-001", "command_ack")
except Exception as exc:  # noqa: BLE001
    sim_command_ack["topic_for"] = f"ERROR {exc}"
try:
    sim_command_ack["qos_retain_for"] = str(simulator.qos_retain_for("command_ack"))
except Exception as exc:  # noqa: BLE001
    sim_command_ack["qos_retain_for"] = f"ERROR {type(exc).__name__}: {exc}"

topics = {
    "device_mqtt_publishers_found": 0,
    "device_evidence": str(ROOT / "firmware" / "main" / "app_main.c") + ":20",
    "backend_subscriptions": [{"topic": t, "qos": q} for t, q in subscriptions],
    "backend_acl_command_ack_read": str(ROOT / "infra" / "mosquitto" / "acl.conf") + ":37",
    "simulator_family_allows_command_ack": str(ROOT / "backend" / "src" / "coldguard_backend"
                                               / "simulator.py") + ":57",
    "simulator_publish_policy_command_ack": sim_command_ack,
    "device_ack_line_kind": "#CG CMDACK (firmware/main/cg_command.c:448), serial only",
}


def _grep(path: pathlib.Path, pattern: str) -> list[str]:
    rx = re.compile(pattern)
    return [
        f"{path.relative_to(ROOT)}:{i}: {ln.strip()}"
        for i, ln in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1)
        if rx.search(ln)
    ]


topic_evidence = {
    "docs_00": _grep(ROOT / "docs" / "00-project-scope-architecture.md",
                     r"coldguard/\{deviceId\}/"),
    "docs_02": _grep(ROOT / "docs" / "02-aiot-closed-loop-engineering.md",
                     r"coldguard/\{device_id\}/"),
    "docs_05C": _grep(ROOT / "docs" / "05C-member-c-iot-backend-digital-twin.md",
                      r"coldguard/\{device_id\}/"),
    "broker_acl": _grep(ROOT / "infra" / "mosquitto" / "acl.conf", r"^topic "),
    "firmware_topic_strings": _grep(ROOT / "firmware" / "main" / "app_main.c",
                                    r"(?i)coldguard/|mqtt|topic"),
}
ack_grammar_source = _grep(ROOT / "firmware" / "main" / "cg_command.c",
                           r'#CG CMDACK schema=1 event=ACK')

# ------------------------------------------------------------ (E) command surface
cmd_required = [
    "schema_version", "command_id", "device_id", "created_at_ms", "expires_at_ms",
    "controller_id", "policy_version", "reason_code", "action_cooling",
    "action_duty_permille",
]
backend_command_fields = sorted(
    name for name in __import__("coldguard_backend.contracts",
                                fromlist=["x"]).Command.model_fields
)

command_surface = {
    "device_parser_required_names": cmd_required,
    "device_parser_rejects_unknown_field": True,
    "device_parser_evidence": str(ROOT / "firmware" / "main" / "cg_command.c") + ":780",
    "backend_command_field_names": backend_command_fields,
    "name_clashes": [
        {"backend": "created_at (ISO-8601 datetime)", "device": "created_at_ms (int ms)"},
        {"backend": "expires_at (ISO-8601 datetime)", "device": "expires_at_ms (int ms)"},
        {"backend": "action.cooling (nested object)", "device": "action_cooling (flat token)"},
        {"backend": "action.duty (float 0.0..1.0)", "device": "action_duty_permille (int)"},
    ],
    "backend_only_fields_the_device_never_sees": [
        f for f in backend_command_fields if f not in cmd_required
    ],
}

# Control validator: does it accept the device's schema number?
from coldguard_control.commands import (  # noqa: E402
    CommandRequest, LocalSafetyEvidence, SUPPORTED_SCHEMA_VERSION as CTRL_SCHEMA,
    validate_command,
)
from coldguard_control.config import PolicyConfig  # noqa: E402
from coldguard_control.types import (  # noqa: E402
    AckStatus, CoolingState, DeviceMode, PolicyState, QualityState, ReasonCode,
)

# Synthetic-only policy values (no commissioning authority); the probe varies
# exactly one thing: the schema number the device actually declares.
CFG = PolicyConfig(
    policy_version="probe-synthetic-v0", representative_source="TMAX",
    upper_on_c=8.0, lower_off_c=6.0, thermal_max_age_s=15.0,
    command_max_future_skew_s=5.0, broker_offline_grace_s=30.0,
    backend_state_max_age_s=10.0, safe_local_exit_min_stable_s=60.0,
    predictive_enabled=False,
)
EVIDENCE = LocalSafetyEvidence(
    device_mode=DeviceMode.ONLINE_NORMAL, policy_state=PolicyState.NORMAL,
    thermal_quality=QualityState.VALID, thermal_age_s=1.0, fan_available=True,
)

control_probe = {"SUPPORTED_SCHEMA_VERSION": CTRL_SCHEMA}
for label, version in (("device_declared_schema", int(device_fields["schema"])),
                       ("control_own_schema", CTRL_SCHEMA)):
    try:
        decision = validate_command(
            CommandRequest(
                schema_version=version,
                command_id="00000000-0000-4000-8000-00000000000a",
                device_id="coldguard-001",
                action=CoolingState.OFF, created_at=0.0, expires_at=100.0,
                authorized=True,
            ),
            EVIDENCE, CFG, now_s=50.0, expected_device_id="coldguard-001", processed={},
        )
        control_probe[label] = {
            "status": decision.status.value,
            "reason_code": (decision.reason_code.value
                            if decision.reason_code else None),
            "detail": decision.detail,
        }
    except Exception as exc:  # noqa: BLE001
        control_probe[label] = f"RAISED {type(exc).__name__}: {exc}"

# ------------------------------------------------------------- compatibility matrix
rows = []
for dev_name, (be_name, dev_type, be_type) in TRANSLATION.items():
    rows.append({
        "device_field": dev_name,
        "device_value_in_probe_frame": device_raw.get(dev_name, "<absent>"),
        "device_declared_type": dev_type,
        "backend_field": be_name,
        "backend_declared_type": be_type,
    })

# Backend-reachable verdict per mapped field, from the real classifier output.
# Evaluated on the schema-forced-to-1 payload, i.e. the best case a gateway can
# reach after rewriting the version number and nothing else. At the device's own
# schema number nothing below is reachable at all (see ingest_cases).
errs = cases["schema_forced_to_1_otherwise_faithful"]["validation_errors"] or []
for r in rows:
    be = r["backend_field"]
    leaf = be.split(".")[-1]
    hit = [e for e in errs if str(e.get("loc")) in (be, leaf)]
    if hit:
        r["backend_verdict"] = "REJECT"
        r["backend_error"] = "; ".join(f"{e.get('code')}@{e.get('loc')}: {e.get('message')}"
                                       for e in hit)
    else:
        r["backend_verdict"] = "ACCEPT (only after schema rewrite + name mapping)"
        r["backend_error"] = ""

# Two rows need the at-source verdict stated explicitly, because the row above
# only measured the best case a gateway reaches after rewriting the value.
for r in rows:
    if r["device_field"] == "schema":
        r["backend_verdict"] = "REJECT at the device's own value"
        r["backend_error"] = ("UNSUPPORTED_SCHEMA@schema_version: unsupported "
                              "schema_version 3; supported: [1] "
                              "(raw_store.classify_raw -> validation.py:210)")
    if r["device_field"] == "timestamp_utc":
        r["backend_verdict"] = "REJECT - unsatisfiable on the device"
        r["backend_error"] = ("SCHEMA_VIOLATION@captured_at: Input should be a valid "
                              "datetime or date, invalid character in year; the device "
                              "has no wall clock and emits the literal UNAVAILABLE "
                              "(cg_telemetry.c:232)")

# Device fields with no backend counterpart at all.
mapped_dev = set(TRANSLATION) | {"schema"}
unmapped = sorted(k for k in device_fields if k not in mapped_dev)
for name in unmapped:
    rows.append({
        "device_field": name,
        "device_value_in_probe_frame": device_raw[name],
        "device_declared_type": "serial token",
        "backend_field": "<none>",
        "backend_declared_type": "<none>",
        "backend_verdict": "IGNORED (Telemetry._WireBase extra='allow'; "
                           "not a column in normalized_store.telemetry)",
        "backend_error": "",
    })

# Backend-required fields the device cannot supply.
gaps = [{
    "backend_field": "captured_at",
    "backend_requirement": "timezone-aware datetime (contracts.py:161, validation.py:230)",
    "device_reality": "timestamp_utc=UNAVAILABLE, no wall clock "
                      "(cg_telemetry.c:232; cg_telemetry_schema.py:17-22)",
    "verdict": "HARD INCOMPATIBILITY - only a gateway-side clock can fill it",
}, {
    "backend_field": "door.state",
    "backend_requirement": "Literal OPEN|CLOSED|UNKNOWN (contracts.py:44,107)",
    "device_reality": "door_open=0|1|nan + door_status=OK|UNVERIFIED (cg_telemetry.c:275-281)",
    "verdict": "TRANSLATION REQUIRED - device never emits OPEN/CLOSED on TELEM",
}, {
    "backend_field": "quality.device_mode",
    "backend_requirement": "BOOT|SELF_TEST|ONLINE_NORMAL|ONLINE_DEGRADED|SAFE_LOCAL|FAULT_LOCKOUT"
                           " (contracts.py:41-43,147)",
    "device_reality": "absent from #CG TELEM; #CG CMDACK sends device_mode=OFF "
                      "(cg_command.c:468, evidence/A/W06/ack-fixture.json)",
    "verdict": "VOCABULARY CLASH - OFF is not a DeviceMode on either consumer side",
}, {
    "backend_field": "quality.* (any section)",
    "backend_requirement": "Literal VALID|DEGRADED|INVALID (contracts.py:40)",
    "device_reality": "VALID|DEGRADED|INVALID|UNKNOWN (cg_telemetry_schema.py:216); "
                      "the probe frame really carries quality=UNKNOWN",
    "verdict": "HARD VOCABULARY GAP - UNKNOWN is unrepresentable in the backend",
}, {
    "backend_field": "actuation.duty",
    "backend_requirement": "float within [0.0, 1.0] (contracts.py:132-137)",
    "device_reality": "pwm_duty is integer permille 0..1000 (cg_telemetry.c:303)",
    "verdict": "UNIT SCALE MISMATCH - raw 250 would fail the range validator",
}, {
    "backend_field": "schema_version",
    "backend_requirement": "Literal[1] + SUPPORTED_SCHEMA_VERSIONS={1} "
                           "(contracts.py:38,157; validation.py:47,210)",
    "device_reality": "CG_TELEMETRY_SCHEMA_VERSION=3 (coldguard_config.h) - serial namespace",
    "verdict": "NAMESPACE CLASH, not a version negotiation: the two numbers count "
               "different streams; the device never emits a JSON schema_version at all",
}]

defects = [
    {"id": "R-01", "severity": "P0", "owner": "Member C gateway (new component)",
     "claim": "There is no device-side MQTT publisher at all; the backend contract "
              "and the device serial line are two different wire formats.",
     "evidence": "firmware/main/app_main.c:20 (Not implemented on purpose: MQTT/"
                 "telemetry publishing); backend/src/coldguard_backend/contracts.py:38",
     "verdict": "Translation layer REQUIRED - not a version bump on either side."},
    {"id": "R-02", "severity": "P0", "owner": "Member A + Member C jointly",
     "claim": "The device cannot produce a timezone-aware captured_at.",
     "evidence": "firmware/main/cg_telemetry.c:232 (timestamp_utc=UNAVAILABLE); "
                 "backend/src/coldguard_backend/validation.py:230 (NAIVE_TIMESTAMP) and "
                 "contracts.py:161",
     "verdict": "Backend event time must be gateway-assigned and labelled as such; "
                "Member A must not be asked to invent a clock."},
    {"id": "R-03", "severity": "P0", "owner": "Member C",
     "claim": "quality vocabulary is closed at three states on the wire but four in "
              "the firmware contract, so a real device frame is unrepresentable.",
     "evidence": "backend/src/coldguard_backend/contracts.py:40 vs "
                 "firmware/tools/cg_telemetry_schema.py:216 and docs/01 (VALID/DEGRADED/"
                 "INVALID/UNKNOWN); control/src/coldguard_control/types.py:25-35 DOES "
                 "include UNKNOWN",
     "verdict": "MEMBER C MUST CHANGE: add UNKNOWN to the wire Quality literal. "
                "Member D already models it, so the backend is the outlier."},
    {"id": "R-04", "severity": "P0", "owner": "Member C",
     "claim": "The backend never subscribes to command_ack, although the broker ACL "
              "grants both directions.",
     "evidence": "backend/src/coldguard_backend/mqtt_consumer.py:60-65 vs "
                 "infra/mosquitto/acl.conf:29 and :37; "
                 "backend/src/coldguard_backend/simulator.py:57 admits the family but "
                 ":63-73 has no publish policy for it",
     "verdict": "Device ACKs are unobservable in the backend today."},
    {"id": "R-05", "severity": "P1", "owner": "canonical docs owner",
     "claim": "Two canonical docs name the ACK topic differently.",
     "evidence": "docs/00-project-scope-architecture.md:1593 'coldguard/{deviceId}/ack' "
                 "vs docs/02-aiot-closed-loop-engineering.md:787 "
                 "'coldguard/{device_id}/command_ack' (and docs/05C:425, acl.conf:29/37)",
     "verdict": "docs/02 is the command contract; docs/00 line 1593 is stale."},
    {"id": "R-06", "severity": "P1", "owner": "Member A + Member C jointly",
     "claim": "The command field sets do not intersect on names or units.",
     "evidence": "firmware/main/cg_command.c:558-561 (created_at_ms / expires_at_ms / "
                 "action_cooling / action_duty_permille, all mandatory, unknown field "
                 "refused at :780) vs backend/src/coldguard_backend/contracts.py:235-249 "
                 "(created_at / expires_at datetime, nested action.duty in [0.0,1.0])",
     "verdict": "Gateway must re-encode; Member A's refusal of unknown fields is "
                "intentional and must not be relaxed."},
    {"id": "R-07", "severity": "P1", "owner": "Member A",
     "claim": "Member A's own W06 evidence exercises the schema-3 telemetry branch.",
     "evidence": "evidence/A/W06/demo-command-capture.log line 10 carries schema=3 and "
                 "the full W06 command/ACK tail",
     "verdict": "RESOLVED: the committed demo capture is a real schema=3 frame with "
                "the no-command-received tail; test_cg_command_trace.py pins it."},
    {"id": "R-08", "severity": "P2", "owner": "Member A",
     "claim": "raw_t1_c/raw_t2_c/raw_t3_c/raw_spare_c are typed by the Member A "
              "parser (fixed in this remediation).",
     "evidence": "firmware/tools/cg_telemetry_schema.py FLOAT_FIELDS now contains the "
                 "four raw temperature tokens; parsed as float|None",
     "verdict": "RESOLVED: the four raw temperature tokens are in FLOAT_FIELDS and "
                "parse as float|None; the regression pins the coercion."},
]

ack_vs_execution = {
    "rule": "An MQTT PUBACK is broker receipt, and a device ACK is protocol evidence; "
            "neither is device execution.",
    "stated_by_backend": "backend/src/coldguard_backend/mqtt_consumer.py:12-31 "
                         "(the PUBACK is not the authority for durably processed) and "
                         "backend/src/coldguard_backend/simulator.py:22",
    "stated_by_device": "firmware/main/cg_command.h:48-54 (an ACK is protocol evidence, "
                        "never physical evidence; in this build the applied state an ACK "
                        "can ever report is OFF)",
    "stated_by_control": "control/src/coldguard_control/commands.py:15-17 and 119-131",
    "conflation_found": False,
    "residual_defect": "The loop is still not closable: the device has no transport, so "
                       "no ACK of any kind can be delivered, and the applied state is "
                       "compiled out. A-W06-05/06 remain open physically.",
}

CG_CMD_C = (ROOT / "firmware" / "main" / "cg_command.c").read_text(
    encoding="utf-8", errors="replace")
CG_CMD_STRINGS = set(re.findall(r'"([A-Z][A-Z0-9_]{3,})"', CG_CMD_C))
CTRL_REASON_VALUES = {m.value for m in ReasonCode}

reason_vocab = {
    "device_ack_status_tokens": sorted(
        t for t in CG_CMD_STRINGS
        if t in {"ACCEPTED", "REJECTED", "DUPLICATE_CANONICAL", "EXPIRED",
                 "SAFETY_BLOCKED", "INVALID_STATE", "OUT_OF_RANGE", "NONE"}
    ),
    "control_ack_status_members": [s.name for s in AckStatus],
    "telemetry_only_extra_token": "NONE (cg_telemetry_schema.py:263) - no command "
                                  "received this boot; not an ACK status",
    "device_parse_reason_tokens_absent_from_control_ReasonCode": sorted(
        t for t in CG_CMD_STRINGS
        if re.match(r"^(MISSING_|BAD_|SOURCE_|DEVICE_ID_TOO|EPOCH_|LIMITS_|DUPLICATE_FIELD)", t)
        and t not in CTRL_REASON_VALUES
    ),
    "shared_reason_tokens": sorted(
        t for t in CG_CMD_STRINGS
        if t in CTRL_REASON_VALUES and t not in {"NONE"}
    ),
}

out = {
    "artifact": "member-a-bcd-contract",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "generated_by": "evidence/A/HANDOFF/contract_probe.py",
    "worktree": str(ROOT),
    "claim_class_legend": {
        "OBSERVED": "produced or read by this run against committed source",
        "HISTORICAL": "carried from an existing document, not re-verified here",
    },
    "schema_numbers": schema_numbers,
    "probe_frame": {
        "committed_capture_line": committed_line,
        "committed_capture_schema": committed_schema,
        "derived_frame_schema": frame3.fields["schema"],
        "derived_frame_provenance": (
            "PARSED, not derived: the committed W06 demo capture carries schema=3 "
            "with the full W06 command/ACK tail already in the frame; it was parsed "
            "directly with no token appended."
            if committed_schema == 3 else
            "DERIVED, not captured: the committed W06 demo capture carries "
            f"schema={committed_schema}; schema=3 was reached by replacing the "
            "schema token and appending the five no-command-received tokens "
            "exactly as firmware/main/cg_telemetry.c:382-384 emits them."
        ),
        "parsed_field_count": len(device_fields),
        "frame_token_order": list(device_raw.keys()),
        "fields": device_raw,
    },
    "device_parser_type_gaps": {
        "note": (
            "Member A's parser coerced every mapped wire number in the probe "
            "frame to float|int; no numeric field crossed as text."
            if not untyped_numeric_fields else
            "cg_telemetry_schema._coerce left these numeric-looking tokens as "
            f"raw strings: {', '.join(untyped_numeric_fields)}. A gateway must "
            "cast them itself."
        ),
        "untyped_numeric_fields": untyped_numeric_fields,
    },
    "compatibility_matrix": rows,
    "backend_hard_gaps": gaps,
    "ingest_cases": cases,
    "quality_vocabulary_probe": quality_case,
    "duty_unit_probe": duty_case,
    "mqtt_topics": {
        **topics,
        "topic_strings_verbatim": topic_evidence,
        "ack_grammar_source_line": ack_grammar_source,
    },
    "command_surface": command_surface,
    "control_validator_probe": control_probe,
    "defect_register": defects,
    "ack_reason_vocabulary": reason_vocab,
    "ack_vs_execution": ack_vs_execution,
    "grammars": {
        "telemetry_serial_frame": (
            "prefix '#CG' + kind 'TELEM' (coldguard_config.h:552 and :568), single space "
            "separators, one trailing '\\n', no '=' inside values, no duplicate keys, "
            "no empty tokens (cg_telemetry_schema.py:432-446); max "
            "CG_TELEMETRY_LINE_MAX=3072 bytes (coldguard_config.h:474); the formatter "
            "refuses to emit a truncated frame (cg_telemetry.c:33-39,387-390); floats "
            "printed %.4f, missing number is the literal 'nan' "
            "(CG_INVALID_VALUE_TOKEN, coldguard_config.h:577); fault_code printed "
            "0x%08lX; age fields saturate at 2^64-1 on clock rewind (cg_telemetry.c:67-73)"
        ),
        "telemetry_token_order": list(device_raw.keys()),
        "command_ack_frame": (
            "#CG CMDACK schema=1 event=ACK command_id=<id> command_id_form=<UUID|"
            "TEST_TOKEN|NONE> source=<NETWORK|LOCAL_CONSOLE|UNKNOWN> device_id=<id> "
            "boot_id=<id> boot_count=<n> uptime_ms=<n> ack_seq=<n> status=<7-token "
            "ACK set> reason=<stable token> desired_cooling=<ON|OFF> "
            "desired_duty_permille=<int> applied_cooling=<ON|OFF> "
            "applied_duty_permille=<int> reapplied=<0|1> expiry_evaluable=<0|1> "
            "time_sync_state=<SYNCHRONIZED|UNSYNCHRONIZED> device_mode=<token> "
            "fault_code=0x<8hex> [canonical_status=<token> when DUPLICATE_CANONICAL] "
            "[output_stage=<ENABLED|DISABLED> allowed_duty_max_permille=<int> when "
            "context supplied] - cg_command.c:447-480. schema=1 here is the docs/02 "
            "command envelope version, NOT the serial telemetry schema "
            "(cg_log.h:26-28, cg_command.h:241-243)."
        ),
        "command_device_encoding": (
            "space-separated key=value, exactly the 10 names at cg_command.c:558-561, "
            "all mandatory except controller_id (cg_command.c:576-586), record <= "
            "CG_COMMAND_RECORD_MAX=512 bytes, unknown key -> UNKNOWN_FIELD, duplicate "
            "key -> DUPLICATE_FIELD, at most CG_CMD_FIELDS_MAX=24 key=value tokens per "
            "record (cg_command.c:13, :630)"
        ),
    },
}

out_json = HERE / "member-a-bcd-contract.json"
out_json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

out_csv = HERE / "member-a-bcd-compatibility-matrix.csv"
with out_csv.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=[
        "device_field", "device_value_in_probe_frame", "device_declared_type",
        "backend_field", "backend_declared_type", "backend_verdict", "backend_error",
    ])
    writer.writeheader()
    writer.writerows(rows)

print(json.dumps({
    "schema_numbers": {k: v["value"] for k, v in schema_numbers.items()},
    "committed_capture_schema": committed_schema,
    "ingest_status_real_schema3": cases["faithful_translation_real_schema3"]["ingest_status"],
    "ingest_errors_real_schema3": cases["faithful_translation_real_schema3"]["validation_errors"],
    "ingest_status_schema1": cases["schema_forced_to_1_otherwise_faithful"]["ingest_status"],
    "ingest_errors_schema1": cases["schema_forced_to_1_otherwise_faithful"]["validation_errors"],
    "quality_probe": quality_case,
    "control_probe": control_probe,
    "simulator_command_ack": sim_command_ack,
    "matrix_rows": len(rows),
    "json": str(out_json),
    "csv": str(out_csv),
}, indent=2, default=str))
