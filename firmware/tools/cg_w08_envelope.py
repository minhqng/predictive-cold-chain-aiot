"""W08 - the REAL observed electrical envelope of the ColdGuard TEC branch.

    py firmware/tools/cg_w08_envelope.py [--bench-root DIR] [--json OUT.json]
    py firmware/tools/cg_w08_envelope.py --no-local          # git sources only

This module reads captures that were already recorded by supervised bench
sessions and computes what the branch actually did electrically. It never talks
to a port, never energizes anything and never invents a value: every number it
publishes is a statistic over bytes that already exist on disk, and every
excluded frame is listed by name rather than averaged away.

Sources, by trust class
-----------------------
``COMMITTED`` (inside this git repository, so a clean checkout reproduces them)
    * ``evidence/A/W04/tec-cooling-response-600s.csv`` - 957 device frames,
      stage H8-C, 100 % duty for 600 s, boot ``56044b74``.
    * ``evidence/A/W04/h6/first-tec-trace.csv`` - 60 SAMPLE rows at 10 % duty
      with the transport class preserved.
    * ``evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.csv`` and
      ``evidence/A/W03/hardware-2026-10-20/raw/pzem-off.csv`` - the OFF-state
      envelope with explicit per-poll validity.
    * ``evidence/A/W04/g1/42-telemetry.csv`` - the production fail-closed build,
      whose electrical fields are labelled ``NO_DATA`` and whose value cells are
      empty.

``LOCAL_BENCH`` (Member A's local W04 tree; NOT in git, declared and hash-pinned
in ``evidence/A/W08/local-bench-observations.json``)
    * ``h7/NN-run-*pct*.log`` - the 20/30/40/50/60/70/80/90/100 % duty ladder.
    * ``h8/phase4e/*/monitor/samples.jsonl`` and
      ``h8/box-cooling-600s-2026-11-01/monitor-final/samples.jsonl`` - the
      180/420/600/900/1800 s endurance sessions, including the raw stream the
      committed 600 s CSV was derived from.

Register-latency rule
---------------------
The PZEM-017 publishes V/I/P on its own integration cycle, so a frame can name
a state the branch is not in. Four documented patterns are handled explicitly,
in code, and every frame they touch is emitted in ``holdover-frames.csv``:

``PRE_RUN_REGISTER``
    the first frame of a driven block whose current is 0.00 while the applied
    duty is nonzero - the meter had not advanced past the pre-START registers.
    Documented for H6 (``evidence/A/W04/h6/41-h6-run-analysis.md``) and for
    every H7 stage (``h7/50-stage-20pct.md``: "the first sample (at +7 ms) still
    held the pre-run registers").
``OUTPUTS_OFF_REGISTER``
    the first frame after the applied duty reaches 0 - one frame period
    (``POST_OFF_HOLD_POLL_MS``) of the observed 1 Hz cadence - whose current is
    still above the steady-OFF floor. In the committed 600 s capture that frame
    is byte-identical to the two preceding driven frames on **every** measured
    field - voltage, current, power, energy and T1..T4 - with only the BME
    environment readings and the duty/state bookkeeping changed; in the
    H8-B/C/D/E sessions it is one least significant bit off. Either way it is a
    register repeat, not a measurement of the branch with the bridge off, so it
    never enters the OFF envelope and never enters a mean.
``OFF_SETTLING``
    a duty-0 frame within ``OFF_SETTLE_MAX_MS`` of the last driven frame whose
    current is above the steady floor but outside the one-poll hold window - the
    meter unwinding. Recorded values: 0.56 A (H8-C box run, two frame periods
    after the last driven frame), 3.57 A (H8-A), 0.41 A (H8-D), 5.77 A (H7 70 %
    OFF_VERIFY attempt 1).
``OFF_RESIDUAL_ABOVE_FLOOR``
    a duty-0 frame above the floor further out than the settle window. None
    occurs in the sources read here; the class exists so that such a frame is
    named and excluded instead of being averaged into the OFF envelope.

A driven frame with zero current that is NOT the first frame of its block is
tagged ``SUSPECT_ZERO_CURRENT`` and reported, never silently dropped.

The steady-OFF floor ``OFF_STEADY_MAX_A`` is 0.05 A: the largest nonzero steady
OFF current in any source read here is 0.02 A - one PZEM current LSB - and the
bench image's own gate is ``off_current_limit_a=0.200``.

Status labels this module may emit
----------------------------------
``REAL_DATA_ANALYZED`` for anything computed from a capture, ``HOST_VERIFIED``
for the tool's own behaviour, ``NEED_USER_ACTION`` / ``BLOCKED_HARDWARE`` for
what a capture cannot close, ``TEAM_DEPENDENCY`` for the conductor deviation
register. It can never emit ``PHYSICALLY_VERIFIED``: no test is run by this code
and no physical limit is certified by it. ``build_envelope`` asserts that.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field

# Reuse the host suite's percentile convention rather than inventing a second
# one: nearest-rank over values that were actually observed, never interpolated.
import cg_timing_analysis

TOOLS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[1]

STATUS_VOCABULARY = (
    "IMPLEMENTED",
    "HOST_VERIFIED",
    "REAL_DATA_ANALYZED",
    "PHYSICALLY_VERIFIED",
    "NEED_USER_ACTION",
    "TEAM_DEPENDENCY",
    "BLOCKED_HARDWARE",
)
FORBIDDEN_STATUS = "PHYSICALLY_VERIFIED"

# The documented meter-unwinding window. Two polls after outputs-off is the
# recorded pattern (~0.1 s then ~1 s on the OFF_VERIFY path, one and two frame
# periods on the 1 Hz telemetry path); 3000 ms is the shortest window that
# covers every recorded case without reaching the steady OFF floor, and it is
# exported in the JSON so a reviewer can see exactly what was excluded.
OFF_SETTLE_MAX_MS = 3000
# One frame period of the observed 1 Hz telemetry cadence, plus margin. The
# register holdover is always the very first duty-0 frame after a driven block.
POST_OFF_HOLD_POLL_MS = 1500
# Steady OFF floor, in amperes: see the module docstring. Anything at or below
# this is the OFF envelope; anything above it near a drive edge is latency.
OFF_STEADY_MAX_A = 0.05

# PZEM-017 least-significant bits, from firmware/tools/cg_modbus.py:49-52
# (VOLT_LSB / CURRENT_LSB / POWER_LSB / ENERGY_LSB). They give the V x I
# consistency test a quantisation-aware tolerance instead of an arbitrary
# percentage: the worst case is each register's half-LSB error propagated
# through the product, plus the product's own half-LSB rounding.
VOLT_LSB = 0.01
CURRENT_LSB = 0.01
POWER_LSB = 0.1
ENERGY_LSB = 1.0
POWER_TOLERANCE_W = 12.0 * CURRENT_LSB / 2 + 10.0 * VOLT_LSB / 2 + POWER_LSB / 2 + 0.02

H8_CSV = "evidence/A/W04/tec-cooling-response-600s.csv"
H6_CSV = "evidence/A/W04/h6/first-tec-trace.csv"
G1_TELEMETRY = "evidence/A/W04/g1/42-telemetry.csv"
W03_OFF_132B = "evidence/A/W03/hardware-2026-10-27/raw/test-132b-off-envelope.csv"
W03_OFF_2026_10_20 = "evidence/A/W03/hardware-2026-10-20/raw/pzem-off.csv"

# Local-bench captures live in a sibling tree that is NOT committed. Their
# locators are written with this marker instead of a developer absolute path,
# so a pinned artifact stays readable on any machine.
LOCAL_BENCH_MARKER = "<local-bench>/"

# A drive-qualified path (``C:\`` / ``D:/``) or a home-directory path in a pinned
# artifact means the artifact only reproduces on one workstation. Single-letter
# test only, so ``https://`` never matches.
_ABS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|(?:^|[\s\"'(,=])/(?:Users|home)/")


def absolute_path_hits(text: str) -> list[str]:
    """Every absolute-path-looking locator in ``text`` (empty when clean)."""
    return [m.group(0).strip() for m in _ABS_PATH_RE.finditer(text)]

# The H7 duty ladder with the wiring regime each log was recorded in. The two
# regimes are not interchangeable: the series return path measured ~0.268 ohm
# before the return-wire replacement and ~0.019-0.021 ohm after it
# (h7/56-shunt-return-drop-diagnostic.md, h7/57-stage-70pct.md: "Earlier 10.8 V
# 60 % data were taken before the wire replacement and are not used for
# prediction here"), and the same 600 per mille drew 4.33 A before and 5.41 A
# after. Grouping them would invent an envelope, so the regime travels with
# every row this module emits.
H7_LADDER = (
    ("h7/40b-run-20pct-rev3.log", "H7-20pct", "return_path_high_resistance"),
    ("h7/40c-run-30pct-rev4.log", "H7-30pct", "return_path_high_resistance"),
    ("h7/61-run-40pct-rev4.log", "H7-40pct", "return_path_high_resistance"),
    ("h7/63-run-50pct-rev4.log", "H7-50pct", "return_path_high_resistance"),
    ("h7/65-run-60pct-rev4.log", "H7-60pct", "return_path_high_resistance"),
    ("h7/67-run-60pct-diag.log", "H7-60pct-diag1", "return_path_high_resistance"),
    ("h7/69-run-60pct-diag2.log", "H7-60pct-diag2", "return_path_high_resistance"),
    ("h7/70-run-60pct-shunt.log", "H7-60pct-shunt", "return_path_replaced"),
    ("h7/71-run-70pct-rev4.log", "H7-70pct", "return_path_replaced"),
    ("h7/72-run-80pct-rev4.log", "H7-80pct", "return_path_replaced"),
    ("h7/73-run-90pct-rev4.log", "H7-90pct", "return_path_replaced"),
    ("h7/75-run-100pct-rev4.log", "H7-100pct", "return_path_replaced"),
)

H8_SESSIONS = (
    ("h8/phase4e/h8a-enable-fixed-2026-10-31/monitor/samples.jsonl", "H8-A-180s",
     "return_path_replaced"),
    ("h8/phase4e/h8b-run-2026-10-31/monitor/samples.jsonl", "H8-B-420s",
     "return_path_replaced"),
    ("h8/phase4e/h8c-2026-10-31/monitor/samples.jsonl", "H8-C-600s-2026-10-31",
     "return_path_replaced"),
    ("h8/phase4e/h8d-2026-10-31/monitor/samples.jsonl", "H8-D-900s",
     "return_path_replaced"),
    ("h8/phase4e/h8e-2026-10-31/monitor/samples.jsonl", "H8-E-1800s",
     "return_path_replaced"),
    ("h8/box-cooling-600s-2026-11-01/monitor-final/samples.jsonl",
     "W04-H8C-box-600s-raw", "return_path_replaced"),
)

# Member A's local W04 bench tree (H7 ladder + H8 raw streams) is a SIBLING
# worktree of this repository, not a committed artifact. Derive its location from
# this checkout so the default carries no developer-specific absolute path; a
# reviewer can always override with --bench-root / --no-local.
DEFAULT_BENCH_ROOT = (
    REPO_ROOT.parent
    / "A-W04-tec-commissioning" / "evidence" / "A" / "W04"
)

# --------------------------------------------------------------------------
# frame model
# --------------------------------------------------------------------------

DRIVEN = "DRIVEN"
IDLE_OFF = "IDLE_OFF"
PRE_RUN_HOLD = "PRE_RUN_REGISTER"
OFF_HOLD = "OUTPUTS_OFF_REGISTER"
OFF_SETTLING = "OFF_SETTLING"
OFF_RESIDUAL = "OFF_RESIDUAL_ABOVE_FLOOR"
SUSPECT_ZERO = "SUSPECT_ZERO_CURRENT"
NO_ELECTRICAL = "NO_ELECTRICAL_VALUE"

ELECTRICAL_FIELDS = ("voltage", "current", "power", "energy")
LATENCY_CLASSES = (PRE_RUN_HOLD, OFF_HOLD, OFF_SETTLING, OFF_RESIDUAL, SUSPECT_ZERO)
OFF_EXCLUDED_CLASSES = (OFF_HOLD, OFF_SETTLING, OFF_RESIDUAL)

# How a source qualifies its electrical values. ``field`` means a per-value
# validity token travelled with the number (the raw device line), ``poll`` means
# one token covered the whole poll (the W03 host captures), ``none`` means the
# numbers arrived with no validity at all. The distinction is the whole point of
# the ``electrical_status_recorded`` flag: a blank label is not ``OK``.
QUALIFICATION_FIELD = "field"
QUALIFICATION_POLL = "poll"
QUALIFICATION_NONE = "none"


@dataclass
class Frame:
    """One device frame, carrying the provenance of its own validity labels."""

    source: str
    seq: str = ""
    clock_ms: float | None = None
    elapsed_s: float | None = None
    state: str = ""
    stage: str = ""
    stop_reason: str = ""
    fault_bits: str = ""
    snapshot: str = ""
    duty_req: int | None = None
    duty_applied: int | None = None
    duty_readback: int | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    power_w: float | None = None
    energy_wh: float | None = None
    thermal: dict[str, float | None] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    ages_ms: dict[str, float] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    transport: dict[str, str] = field(default_factory=dict)
    classification: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def driven(self) -> bool:
        return self.duty_applied is not None and self.duty_applied > 0


def _num(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: object) -> int | None:
    number = _num(value)
    return None if number is None else int(number)


def r(value: float | None, ndigits: int = 4) -> float | None:
    return None if value is None else round(value + 0.0, ndigits)


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------

def read_h8_csv(path: pathlib.Path, source: str) -> list[Frame]:
    """Load the derived H8 cooling CSV.

    Column names are matched defensively on purpose: the committed 600 s CSV has
    ``voltage_status`` and ``current_status`` columns that are empty in every
    row, and no ``power_status``, ``energy_status`` or ``door_status`` column at
    all. That absence is a finding, so an unknown column is never a zero.
    """
    frames: list[Frame] = []
    with path.open("r", encoding="utf-8", newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            frame = Frame(source=source)
            frame.seq = (row.get("seq") or "").strip()
            frame.clock_ms = _num(row.get("device_ms"))
            frame.elapsed_s = _num(row.get("stage_elapsed_s"))
            frame.state = (row.get("state") or "").strip()
            frame.stage = (row.get("stage") or "").strip()
            frame.stop_reason = (row.get("stop_reason") or "").strip()
            frame.fault_bits = (row.get("fault_bits") or "").strip()
            frame.snapshot = (row.get("snapshot") or "").strip()
            frame.duty_req = _int(row.get("pwm_req_permille"))
            frame.duty_applied = _int(row.get("pwm_applied_permille"))
            frame.duty_readback = _int(row.get("pwm_readback_permille"))
            frame.voltage_v = _num(row.get("voltage_v"))
            frame.current_a = _num(row.get("current_a"))
            frame.power_w = _num(row.get("power_w"))
            frame.energy_wh = _num(row.get("energy_wh"))
            for channel in ("t1", "t2", "t3", "t4"):
                frame.thermal[channel] = _num(row.get(f"{channel}_c"))
                frame.status[channel] = (row.get(f"{channel}_status") or "").strip()
                frame.roles[channel] = (row.get(f"{channel}_role") or "").strip()
                age = _num(row.get(f"{channel}_age_ms"))
                if age is not None:
                    frame.ages_ms[channel] = age
            _read_electrical_status(row, frame)
            frame.status["_columns"] = ",".join(sorted(row))
            frame.transport["class"] = (row.get("pzem_class") or "").strip()
            frame.transport["attempt"] = (row.get("pzem_attempt") or "").strip()
            frames.append(frame)
    return frames


def _read_electrical_status(row: dict[str, str], frame: Frame) -> None:
    """Pick up any per-field validity token the CSV actually carries."""
    aliases = {
        "voltage": ("voltage_status", "voltage_v_status"),
        "current": ("current_status", "current_a_status"),
        "power": ("power_status", "power_w_status"),
        "energy": ("energy_status", "energy_wh_status"),
    }
    for name, keys in aliases.items():
        label = ""
        for key in keys:
            if key in row and (row.get(key) or "").strip():
                label = row[key].strip()
                break
        frame.status[name] = label
    frame.status["power_status_column_exists"] = "true" if "power_status" in row else "false"
    frame.status["energy_status_column_exists"] = "true" if "energy_status" in row else "false"
    frame.status["door_status_column_exists"] = "true" if "door_status" in row else "false"


def read_h6_csv(path: pathlib.Path, source: str) -> list[Frame]:
    """Load the committed H6 conservative trace CSV.

    That CSV uses its own column names - ``duty_permille``, ``vbus_v`` and a
    ``record_type`` that mixes events with samples - so it gets its own reader
    rather than being forced through the H8 column vocabulary. It carries no
    energy counter and no thermal channel
    (``thermal_channels=NOT_READ_BY_H6_IMAGE``).
    """
    frames: list[Frame] = []
    with path.open("r", encoding="utf-8", newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if (row.get("record_type") or "").strip() != "SAMPLE":
                continue
            frame = Frame(source=source)
            frame.seq = (row.get("source_line") or "").strip()
            frame.clock_ms = _num(row.get("elapsed_ms"))
            frame.elapsed_s = None if frame.clock_ms is None else frame.clock_ms / 1000.0
            frame.state = (row.get("state") or "").strip()
            frame.duty_applied = _int(row.get("duty_permille"))
            frame.voltage_v = _num(row.get("vbus_v"))
            frame.current_a = _num(row.get("current_a"))
            frame.power_w = _num(row.get("power_w"))
            for name in ELECTRICAL_FIELDS:
                frame.status[name] = ""
            frame.status["qualification"] = QUALIFICATION_NONE
            frame.status["_columns"] = "h6_trace_csv"
            frame.transport["class"] = (row.get("pzem_class") or "").strip()
            frame.transport["attempt"] = (row.get("pzem_attempt") or "").strip()
            frame.transport["rpwm_level"] = (row.get("rpwm_level") or "").strip()
            frame.transport["ren"] = (row.get("ren") or "").strip()
            frame.transport["len"] = (row.get("len") or "").strip()
            frames.append(frame)
    return frames


def read_g1_csv(path: pathlib.Path, source: str) -> list[Frame]:
    """Load the production fail-closed G1 telemetry CSV (delivered serial schema)."""
    frames: list[Frame] = []
    with path.open("r", encoding="utf-8", newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            frame = Frame(source=source)
            frame.clock_ms = _num(row.get("elapsed_ms"))
            frame.state = (row.get("tec_state") or "").strip()
            frame.duty_applied = _int(row.get("pwm_duty"))
            frame.voltage_v = _num(row.get("voltage_v"))
            frame.current_a = _num(row.get("current_a"))
            frame.power_w = _num(row.get("power_w"))
            frame.energy_wh = _num(row.get("energy_wh"))
            for name, key in (("voltage", "voltage_status"), ("current", "current_status"),
                              ("power", "power_status"), ("energy", "energy_status")):
                frame.status[name] = (row.get(key) or "").strip()
            frame.status["qualification"] = QUALIFICATION_FIELD
            frame.status["output_stage"] = (row.get("output_stage") or "").strip()
            frame.status["fan_status"] = (row.get("fan_status") or "").strip()
            frame.status["fault_reason"] = (row.get("fault_reason") or "").strip()
            frame.status["power_validity"] = (row.get("power_validity") or "").strip()
            frames.append(frame)
    return frames


def read_w03_off(path: pathlib.Path, source: str) -> list[Frame]:
    """Load a W03 OFF-envelope CSV: one validity token for the whole poll."""
    frames: list[Frame] = []
    with path.open("r", encoding="utf-8", newline="", errors="replace") as handle:
        for row in csv.DictReader(handle):
            frame = Frame(source=source)
            frame.seq = (row.get("sample") or "").strip()
            frame.clock_ms = _num(row.get("elapsed_ms"))
            if frame.clock_ms is None:
                seconds = _num(row.get("elapsed_s"))
                frame.clock_ms = None if seconds is None else seconds * 1000.0
            frame.duty_applied = 0
            frame.voltage_v = _num(row.get("voltage_v"))
            frame.current_a = _num(row.get("current_a"))
            frame.power_w = _num(row.get("power_w"))
            frame.energy_wh = _num(row.get("energy_wh"))
            label = (row.get("status") or "").strip() or (row.get("quality") or "").strip()
            for name in ELECTRICAL_FIELDS:
                frame.status[name] = label
            frame.status["qualification"] = QUALIFICATION_POLL
            frame.status["valid_flag"] = (row.get("valid") or "").strip()
            frame.transport["rx_len"] = (row.get("rx_len") or "").strip()
            frame.transport["error"] = (row.get("error") or "").strip()
            frame.transport["received"] = _received_from_error(frame.transport["error"])
            frame.transport["physical_fail"] = (row.get("physical_fail") or "").strip()
            frames.append(frame)
    return frames


def _received_from_error(error: str) -> str:
    match = re.search(r"received=(\d+)", error or "")
    return match.group(1) if match else ""


def read_raw_jsonl(path: pathlib.Path, source: str) -> list[Frame]:
    """Load an H8 monitor ``samples.jsonl``.

    The monitor's parsed object drops the per-field electrical status and age
    tokens the device emitted, so they are recovered from the frame's own
    ``raw`` string. That recovery is what makes the "unqualified in the committed
    CSV, qualified on the wire" distinction provable rather than asserted: the
    wire line carries ``voltage_v_status``/``current_a_status``/``power_w_status``
    plus their ages, while the committed CSV carries empty status cells.
    """
    frames: list[Frame] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        frame = Frame(source=source)
        frame.seq = str(record.get("seq", ""))
        frame.clock_ms = _num(record.get("device_ms"))
        elapsed_ms = _num(record.get("stage_elapsed_ms"))
        frame.elapsed_s = None if elapsed_ms is None else elapsed_ms / 1000.0
        frame.state = str(record.get("state", ""))
        frame.stage = str(record.get("stage", ""))
        frame.stop_reason = str(record.get("stop_reason", ""))
        frame.fault_bits = str(record.get("fault_bits", ""))
        frame.snapshot = str(record.get("snapshot", ""))
        frame.duty_req = _int(record.get("pwm_req"))
        frame.duty_applied = _int(record.get("pwm_applied"))
        frame.duty_readback = _int(record.get("pwm_readback"))
        frame.voltage_v = _num(record.get("voltage_v"))
        frame.current_a = _num(record.get("current_a"))
        frame.power_w = _num(record.get("power_w"))
        frame.energy_wh = _num(record.get("energy_wh"))
        for channel in ("t1", "t2", "t3", "t4"):
            frame.thermal[channel] = _num(record.get(channel))
            frame.status[channel] = str(record.get(f"{channel}_status", ""))
            frame.roles[channel] = str(record.get(f"{channel}_role", ""))
            age = _num(record.get(f"{channel}_age_ms"))
            if age is not None:
                frame.ages_ms[channel] = age
        tokens = _raw_tokens(str(record.get("raw", "")))
        for name, status_key, age_key in (
            ("voltage", "voltage_v_status", "voltage_v_age_ms"),
            ("current", "current_a_status", "current_a_age_ms"),
            ("power", "power_w_status", "power_w_age_ms"),
        ):
            frame.status[name] = tokens.get(status_key, "")
            age = _num(tokens.get(age_key))
            if age is not None:
                frame.ages_ms[name] = age
        # The wire line has no energy validity token of any kind. That is a
        # finding, not an oversight of this reader: see the A3 provenance table.
        frame.status["energy"] = tokens.get("energy_wh_status", "")
        frame.status["qualification"] = QUALIFICATION_FIELD
        frame.status["off_current_limit_a"] = tokens.get("off_current_limit_a", "")
        frame.status["off_current_approved"] = tokens.get("off_current_approved", "")
        frame.status["off_verify"] = tokens.get("off_verify", "")
        frame.status["limits_policy"] = tokens.get("limits_policy", "")
        frame.status["limits_enforced"] = tokens.get("limits_enforced", "")
        frame.status["door_status"] = tokens.get("door_status", "")
        frame.status["interlock_state"] = tokens.get("interlock_state", "")
        frame.status["_columns"] = "raw_kv"
        frames.append(frame)
    return frames


def _raw_tokens(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in raw.split(" "):
        if "=" in token:
            key, value = token.split("=", 1)
            out[key] = value
    return out


H7_SAMPLE_RE = re.compile(
    r"H7 T stage=(?P<stage>\S+) duty_permille=(?P<duty>\d+) "
    r"elapsed_ms=(?P<ms>\d+) vbus_mv=(?P<v>\d+) current_ma=(?P<i>\d+) "
    r"power_mw=(?P<p>\d+) t2=(?P<t2>\S+) t2_dc=(?P<t2dc>\S+) pzem=(?P<pz>\S+)"
)
H7_TRACE_RE = re.compile(
    r"H7 PZEM_TRACE attempt=(?P<attempt>\d+)\b.*?rx_len=(?P<rx>\S+).*?class=(?P<cls>\S+)"
)
H7_OFF_VERIFY_RE = re.compile(
    r"H7 OFF_VERIFY attempt=(?P<attempt>\d+) pzem=(?P<pz>\S+) vbus_mv=(?P<v>\d+) "
    r"current_ma=(?P<i>\d+) duty_readback=(?P<rb>\d+)"
)
H7_STOP_RE = re.compile(
    r"H7 (?:OFF|END) source=(?P<src>\S+)? ?stage=(?P<stage>\S+) reason=(?P<reason>\S+) "
    r"elapsed_ms=(?P<ms>\d+)"
)


def read_h7_run_log(path: pathlib.Path, source: str) -> list[Frame]:
    """Parse the ``H7 T`` sample lines of one H7 stage log."""
    frames: list[Frame] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        match = H7_SAMPLE_RE.search(line)
        if not match:
            continue
        fields = match.groupdict()
        frame = Frame(source=source)
        frame.seq = str(len(frames) + 1)
        frame.clock_ms = float(fields["ms"])
        frame.elapsed_s = frame.clock_ms / 1000.0
        frame.state = "COOLING"
        frame.stage = fields["stage"]
        frame.duty_applied = int(fields["duty"])
        frame.voltage_v = int(fields["v"]) / 1000.0
        frame.current_a = int(fields["i"]) / 1000.0
        frame.power_w = int(fields["p"]) / 1000.0
        frame.thermal["t2"] = int(fields["t2dc"]) / 10.0
        frame.status["t2"] = fields["t2"]
        # The H7 bench frame has no per-field validity token at all: the T line
        # is emitted only when the PZEM read was usable, so the sample's
        # qualification is the line's existence, not a label.
        for name in ELECTRICAL_FIELDS:
            frame.status[name] = ""
        frame.status["qualification"] = QUALIFICATION_NONE
        frame.status["_columns"] = "h7_T_line"
        frame.transport["class"] = fields["pz"]
        frames.append(frame)
    return frames


def read_h7_transport(path: pathlib.Path) -> dict[str, object]:
    """Transport-level PZEM quality of one H7 run log (all polls, not just T)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    traces = [m.groupdict() for m in H7_TRACE_RE.finditer(text)]
    classes: dict[str, int] = {}
    lengths: dict[str, int] = {}
    attempts: dict[str, int] = {}
    for trace in traces:
        classes[trace["cls"]] = classes.get(trace["cls"], 0) + 1
        lengths[trace["rx"]] = lengths.get(trace["rx"], 0) + 1
        attempts[trace["attempt"]] = attempts.get(trace["attempt"], 0) + 1
    return {
        "polls": len(traces),
        "class_counts": classes,
        "rx_len_counts": lengths,
        "attempt_counts": attempts,
        "off_verify": [m.groupdict() for m in H7_OFF_VERIFY_RE.finditer(text)],
        "stop": [m.groupdict() for m in H7_STOP_RE.finditer(text)],
    }


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

def classify(frames: list[Frame]) -> list[Frame]:
    """Tag every frame with its electrical role, applying the latency rules.

    Order matters. A duty-0 frame is only evidence about the OFF state once the
    meter has had one integration cycle to notice the change, so the holdover and
    unwinding classes are decided before the steady OFF class.
    """
    for index, frame in enumerate(frames):
        previous = frames[index - 1] if index else None
        if frame.current_a is None:
            frame.classification = NO_ELECTRICAL
            continue
        if frame.driven:
            first_of_block = previous is None or not previous.driven
            if frame.current_a == 0.0:
                if first_of_block:
                    frame.classification = PRE_RUN_HOLD
                    frame.notes.append(
                        "first frame of the driven block reads 0.00 A while the "
                        "applied duty is nonzero: the PZEM register set had not "
                        "advanced past the pre-START values"
                    )
                else:
                    frame.classification = SUSPECT_ZERO
                    frame.notes.append(
                        "nonzero applied duty with 0.00 A inside the block: not a "
                        "start transient, must be explained before use"
                    )
            else:
                frame.classification = DRIVEN
            continue

        delta_ms = _ms_since_last_driven(frames, index)
        above_floor = frame.current_a > OFF_STEADY_MAX_A
        if above_floor and delta_ms is not None and delta_ms <= POST_OFF_HOLD_POLL_MS:
            frame.classification = OFF_HOLD
            if previous is not None and (frame.voltage_v, frame.current_a, frame.power_w) == (
                    previous.voltage_v, previous.current_a, previous.power_w):
                frame.notes.append(
                    f"duty 0 {delta_ms:.0f} ms after the last driven frame and "
                    "byte-identical on (voltage, current, power) to it: register "
                    "repeat, not a measurement of the branch with the bridge off"
                )
            else:
                frame.notes.append(
                    f"duty 0 {delta_ms:.0f} ms after the last driven frame with "
                    "current still at the loaded value: first post-OFF poll returns "
                    "the last loaded registers (documented PZEM latency), not a "
                    "measurement of the branch with the bridge off"
                )
        elif above_floor and delta_ms is not None and delta_ms <= OFF_SETTLE_MAX_MS:
            frame.classification = OFF_SETTLING
            frame.notes.append(
                f"duty 0 with current above the steady floor {delta_ms:.0f} ms "
                f"after the last driven frame (within {OFF_SETTLE_MAX_MS} ms): "
                "meter unwinding"
            )
        elif above_floor:
            frame.classification = OFF_RESIDUAL
            frame.notes.append(
                f"duty 0 with current {frame.current_a} A outside the documented "
                "settle window: named and excluded, never averaged into the OFF "
                "envelope"
            )
        else:
            frame.classification = IDLE_OFF
    return frames


def _last_driven_clock(frames: list[Frame], index: int) -> float | None:
    for offset in range(1, index + 1):
        candidate = frames[index - offset]
        if candidate.driven:
            return candidate.clock_ms
    return None


def _ms_since_last_driven(frames: list[Frame], index: int) -> float | None:
    frame = frames[index]
    last_driven = _last_driven_clock(frames, index)
    if last_driven is None or frame.clock_ms is None:
        return None
    return frame.clock_ms - last_driven


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def distribution(values: list[float | None]) -> dict[str, object]:
    """Nearest-rank distribution over observed values; nothing interpolated."""
    present = [float(v) for v in values if v is not None]
    if not present:
        return {"count": 0}
    return {
        "count": len(present),
        "min": r(min(present)),
        "p05": r(cg_timing_analysis._percentile(present, 0.05)),
        "median": r(cg_timing_analysis._percentile(present, 0.50)),
        "mean": r(_fmean(present)),
        "p95": r(cg_timing_analysis._percentile(present, 0.95)),
        "max": r(max(present)),
    }


def _fmean(values: list[float]) -> float:
    return sum(values) / len(values)


def power_consistency(frames: list[Frame]) -> dict[str, object]:
    """Reported power versus voltage x current, frame by frame.

    The PZEM computes true power itself, so V x I is a consistency check and not
    an identity. What matters is whether the gap stays inside the quantisation of
    the three registers, and whether an average quoted from these columns can be
    reproduced from them - a published H7 average has already had to be
    corrected for exactly that (h7/56-shunt-return-drop-diagnostic.md records a
    62.521 W figure corrected to 64.10 W because it did not match V x I).
    """
    usable = [
        f for f in frames
        if f.voltage_v is not None and f.current_a is not None and f.power_w is not None
    ]
    deviations = [abs(f.power_w - f.voltage_v * f.current_a) for f in usable]
    beyond = []
    for frame in usable:
        product = frame.voltage_v * frame.current_a
        delta = frame.power_w - product
        if abs(delta) > POWER_TOLERANCE_W:
            beyond.append({
                "source": frame.source,
                "seq": frame.seq,
                "clock_ms": r(frame.clock_ms, 0),
                "voltage_v": r(frame.voltage_v),
                "current_a": r(frame.current_a),
                "power_w": r(frame.power_w),
                "v_times_i_w": r(product),
                "delta_w": r(delta),
            })
    driven = [f for f in usable if f.classification == DRIVEN]
    aggregate: dict[str, object] = {}
    if driven:
        mean_p = _fmean([f.power_w for f in driven])
        mean_v = _fmean([f.voltage_v for f in driven])
        mean_i = _fmean([f.current_a for f in driven])
        product = mean_v * mean_i
        aggregate = {
            "driven_frames": len(driven),
            "mean_reported_power_w": r(mean_p),
            "mean_voltage_times_mean_current_w": r(product),
            "delta_w": r(mean_p - product),
            "delta_percent": r(100.0 * (mean_p - product) / product) if product else None,
        }
    return {
        "frames_compared": len(usable),
        "max_abs_delta_w": r(max(deviations)) if deviations else None,
        "mean_abs_delta_w": r(_fmean(deviations)) if deviations else None,
        "quantisation_tolerance_w": r(POWER_TOLERANCE_W),
        "frames_beyond_tolerance_count": len(beyond),
        "frames_beyond_tolerance": beyond,
        "aggregate_check": aggregate,
        "verdict": (
            "NO_MISMATCH_BEYOND_REGISTER_QUANTISATION" if usable and not beyond
            else ("INSUFFICIENT_DATA" if not usable else "MISMATCH_PRESENT")
        ),
    }


def energy_consistency(frames: list[Frame]) -> dict[str, object]:
    """The reported energy counter against the trapezoidal integral of power."""
    series = [
        f for f in frames
        if f.energy_wh is not None and f.power_w is not None and f.clock_ms is not None
    ]
    if len(series) < 2:
        return {"frames": len(series), "verdict": "INSUFFICIENT_DATA"}
    decreases = [
        [a.seq, r(a.energy_wh), r(b.energy_wh)]
        for a, b in zip(series, series[1:])
        if b.energy_wh < a.energy_wh
    ]
    integral_wh = 0.0
    for a, b in zip(series, series[1:]):
        dt = (b.clock_ms - a.clock_ms) / 1000.0
        if dt <= 0:
            continue
        # power is watts and dt is seconds: /3600 converts W.s to Wh.
        integral_wh += 0.5 * (a.power_w + b.power_w) * dt / 3600.0
    delta = series[-1].energy_wh - series[0].energy_wh
    residual_wh = delta - integral_wh
    verdict = (
        "COUNTER_WITHIN_QUANTISATION" if abs(residual_wh) <= ENERGY_LSB
        else "COUNTER_OUTSIDE_QUANTISATION"
    )
    if not decreases:
        pass
    else:
        verdict = "COUNTER_DECREASED"
    return {
        "frames": len(series),
        "span_s": r((series[-1].clock_ms - series[0].clock_ms) / 1000.0),
        "energy_wh_first": r(series[0].energy_wh),
        "energy_wh_last": r(series[-1].energy_wh),
        "counter_delta_wh": r(delta),
        "distinct_counter_values": len({f.energy_wh for f in series}),
        "trapezoidal_integral_of_power_wh": r(integral_wh),
        "counter_minus_integral_wh": r(residual_wh),
        "counter_quantisation_wh": ENERGY_LSB,
        "monotonic_non_decreasing": not decreases,
        "decrease_events": decreases[:20],
        "verdict": verdict,
        "note": (
            "the counter is published in whole watt-hours with no validity token, "
            "so agreement to within 1 Wh is the strongest statement the data "
            "supports"
        ),
    }


VALUE_ATTR = {"voltage": "voltage_v", "current": "current_a",
              "power": "power_w", "energy": "energy_wh"}


def status_coverage(frames: list[Frame]) -> dict[str, object]:
    """Which electrical columns actually carried a validity token, per source.

    A blank label is not ``OK``. The reason this table exists is that a reader
    of the committed 600 s CSV cannot tell whether an electrical value was
    fresh, stale or absent, because that CSV's own status columns are empty and
    it has no power/energy/door status column at all. The same session on the
    wire - ``W04-H8C-box-600s-raw`` - does carry the tokens, which is how this
    function can state the difference as a fact instead of an opinion.
    """
    per_source: dict[str, dict[str, object]] = {}
    for source in sorted({f.source for f in frames}):
        rows = [f for f in frames if f.source == source]
        columns: dict[str, object] = {}
        for name in ELECTRICAL_FIELDS:
            attr = VALUE_ATTR[name]
            labels: dict[str, int] = {}
            with_value = 0
            ok_value = 0
            for frame in rows:
                key = frame.status.get(name) or "(empty)"
                labels[key] = labels.get(key, 0) + 1
                if getattr(frame, attr) is not None:
                    with_value += 1
                    if key == "OK":
                        ok_value += 1
            blank = labels.get("(empty)", 0)
            columns[name] = {
                "label_counts": dict(sorted(labels.items())),
                "frames_without_a_label": blank,
                "frames_with_a_value": with_value,
                "frames_with_a_value_and_OK_label": ok_value,
                "qualified": blank == 0,
                "any_label_present": bool(set(labels) - {"(empty)"}),
            }
        levels = {f.status.get("qualification") for f in rows if f.status.get("qualification")}
        level = ("none" if not levels else
                 next(iter(levels)) if len(levels) == 1 else "mixed")
        any_value = any(columns[name]["frames_with_a_value"] for name in ELECTRICAL_FIELDS)
        qualified = all(columns[name]["qualified"] for name in ("voltage", "current", "power"))
        per_source[source] = {
            "frames": len(rows),
            "qualification_level": level,
            "columns": columns,
            # The flag the rest of the dossier quotes: a published V/I/P figure
            # from a source with this false is an unqualified value.
            "electrical_status_recorded": bool(qualified and any_value),
            "unqualified_columns": [
                name for name in ELECTRICAL_FIELDS
                if not columns[name]["qualified"] and columns[name]["frames_with_a_value"]
            ],
            "valueless_columns": [
                name for name in ELECTRICAL_FIELDS if not columns[name]["frames_with_a_value"]
            ],
            "status_token_absent_on_wire": [
                name for name in ELECTRICAL_FIELDS
                if not columns[name]["any_label_present"]
            ],
            "age_ms": {
                name: distribution([f.ages_ms.get(name) for f in rows])
                for name in ("voltage", "current", "power")
            },
            "note": (
                "electrical values carry a validity token in this source"
                if qualified and any_value else
                ("this source publishes validity tokens but no electrical values at "
                 "all: every cell is empty and labelled INVALID/NO_DATA"
                 if qualified else
                 "no per-value electrical validity token survived into this source: "
                 "its V/I/P figures are unqualified and must be labelled as such")
            ),
        }
    return per_source


# --------------------------------------------------------------------------
# envelope assembly
# --------------------------------------------------------------------------

def drive_stats(frames: list[Frame]) -> dict[str, object]:
    """Distribution of the driven population, with the latency frames excluded."""
    block = [f for f in frames if f.driven]
    used = [f for f in frames if f.classification == DRIVEN]
    excluded = [f for f in block if f.classification != DRIVEN]
    return {
        "driven_frames_in_source": len(block),
        "frames_used": len(used),
        "frames_excluded": len(excluded),
        "excluded_classes": sorted({f.classification for f in excluded}),
        "current_a": distribution([f.current_a for f in used]),
        "voltage_v": distribution([f.voltage_v for f in used]),
        "power_w": distribution([f.power_w for f in used]),
        "energy_wh": distribution([f.energy_wh for f in used]),
        "mean_current_a_inclusive_of_holdovers": r(
            _fmean([f.current_a for f in block if f.current_a is not None])
        ) if block else None,
        "mean_current_a_excluding_holdovers": r(
            _fmean([f.current_a for f in used])
        ) if used else None,
        "electrical_status_recorded": all(
            f.status.get("voltage") and f.status.get("current") and f.status.get("power")
            for f in used
        ) if used else False,
    }


def off_stats(frames: list[Frame]) -> dict[str, object]:
    """The OFF population with every latency frame named rather than averaged.

    ``steady`` means duty 0 at or below ``OFF_STEADY_MAX_A``, far enough from a
    drive edge that the meter has reported the branch, not the previous state.
    """
    off = [f for f in frames if f.duty_applied == 0 and f.current_a is not None]
    steady = [f for f in off if f.classification == IDLE_OFF]
    excluded = [f for f in off if f.classification in OFF_EXCLUDED_CLASSES]
    nonzero = [f for f in steady if f.current_a != 0.0]
    return {
        "off_frames": len(off),
        "steady_frames_used": len(steady),
        "excluded_register_frames": len(excluded),
        "excluded_classes": sorted({f.classification for f in excluded}),
        "steady_current_a": distribution([f.current_a for f in steady]),
        "steady_nonzero_frames": len(nonzero),
        "steady_max_current_a": r(max(f.current_a for f in steady)) if steady else None,
        "excluded_max_current_a": r(max((f.current_a for f in excluded), default=None)),
        "steady_floor_a": OFF_STEADY_MAX_A,
        "bench_off_current_limit_a": 0.200,
        "off_current_limit_provenance": (
            "H8 frame field off_current_limit_a=0.200 (raw telemetry, bench image), "
            "not a canonical limit and not a production value"
        ),
        "electrical_status_recorded": all(
            f.status.get("voltage") and f.status.get("current") and f.status.get("power")
            for f in steady
        ) if steady else False,
    }


def duty_zero_with_current(frames: list[Frame]) -> list[dict[str, object]]:
    """Every duty-0 frame that reports current above the steady floor, one row each.

    Averages hide these; the requirement is that they are listed individually.
    """
    rows = []
    for frame in frames:
        if frame.duty_applied != 0 or frame.current_a is None:
            continue
        if frame.current_a <= OFF_STEADY_MAX_A:
            continue
        rows.append({
            "source": frame.source,
            "seq": frame.seq,
            "clock_ms": r(frame.clock_ms, 0),
            "state": frame.state,
            "stage": frame.stage,
            "stop_reason": frame.stop_reason,
            "duty_req_permille": frame.duty_req,
            "duty_applied_permille": frame.duty_applied,
            "duty_readback_permille": frame.duty_readback,
            "voltage_v": r(frame.voltage_v),
            "current_a": r(frame.current_a),
            "power_w": r(frame.power_w),
            "energy_wh": r(frame.energy_wh),
            "t2_c": r(frame.thermal.get("t2")),
            "classification": frame.classification,
            "electrical_status_recorded": bool(
                frame.status.get("voltage") and frame.status.get("current")
                and frame.status.get("power")
            ),
            "note": "; ".join(frame.notes),
        })
    return rows


def thermal_response(frames: list[Frame]) -> dict[str, object]:
    """Per-channel thermal behaviour, with the device's own role token attached.

    Role-explicit naming is the operator-frozen as-built mapping: T1
    CHAMBER_CENTER, T2 TEC_HOT_SIDE, T3 CHAMBER_BOTTOM, T4 CHAMBER_NEAR_DOOR.
    The device token is reported as emitted - it is not the same thing and it
    changed between images - and no channel here is ever averaged into another.
    """
    as_built = {
        "t1": "CHAMBER_CENTER",
        "t2": "TEC_HOT_SIDE",
        "t3": "CHAMBER_BOTTOM",
        "t4": "CHAMBER_NEAR_DOOR",
    }
    out: dict[str, object] = {}
    for channel in ("t1", "t2", "t3", "t4"):
        series = [f for f in frames if f.thermal.get(channel) is not None]
        if not series:
            continue
        values = [f.thermal[channel] for f in series]
        driven = [f for f in series if f.classification == DRIVEN]
        roles = sorted({f.roles.get(channel, "") or "(empty)" for f in series})
        out[channel] = {
            "as_built_role": as_built[channel],
            "frames": len(series),
            "device_reported_role": roles,
            "role_is_hot_side": any(role in ("HOT_SIDE", "HOT_FINS") for role in roles),
            "min_c": r(min(values)),
            "max_c": r(max(values)),
            "first_c": r(values[0]),
            "last_c": r(values[-1]),
            "last_driven_c": r(driven[-1].thermal[channel]) if driven else None,
            "spread_k": r(max(values) - min(values)),
            "averaged_into_any_statistic": False,
        }
    return out


def holdover_rows(frames: list[Frame]) -> list[dict[str, object]]:
    rows = []
    for frame in frames:
        if frame.classification not in LATENCY_CLASSES:
            continue
        rows.append({
            "source": frame.source,
            "seq": frame.seq,
            "clock_ms": r(frame.clock_ms, 0),
            "state": frame.state,
            "stage": frame.stage,
            "duty_applied_permille": frame.duty_applied,
            "voltage_v": r(frame.voltage_v),
            "current_a": r(frame.current_a),
            "power_w": r(frame.power_w),
            "energy_wh": r(frame.energy_wh),
            "classification": frame.classification,
            "note": "; ".join(frame.notes),
        })
    return rows


def load_sources(repo_root: pathlib.Path, bench_root: pathlib.Path | None) -> dict[str, list[Frame]]:
    """Frames grouped by source; the caller tags each COMMITTED or LOCAL_BENCH."""
    sources: dict[str, list[Frame]] = {}
    committed = {
        "W04-H8C-box-600s": (H8_CSV, read_h8_csv),
        "W04-H6-10pct": (H6_CSV, read_h6_csv),
        "W04-G1-production-failclosed": (G1_TELEMETRY, read_g1_csv),
        "W03-132b-off-envelope": (W03_OFF_132B, read_w03_off),
        "W03-pzem-off-2026-10-20": (W03_OFF_2026_10_20, read_w03_off),
    }
    for source, (rel, reader) in committed.items():
        path = repo_root / rel
        if path.is_file():
            sources[source] = classify(reader(path, source))
    if bench_root is None or not bench_root.is_dir():
        return sources
    local_paths: list[tuple[str, pathlib.Path, object]] = []
    for _rel, label, _regime in H7_LADDER:
        local_paths.append((label, bench_root / _rel, read_h7_run_log))
    for rel, label, _regime in H8_SESSIONS:
        local_paths.append((label, bench_root / rel, read_raw_jsonl))
    for label, path, reader in local_paths:
        if path.is_file():
            sources[label] = classify(reader(path, label))
    return sources


COMMITTED_SOURCES = (
    "W04-H8C-box-600s", "W04-H6-10pct", "W04-G1-production-failclosed",
    "W03-132b-off-envelope", "W03-pzem-off-2026-10-20",
)


def source_regime(source: str) -> str:
    for rel, label, regime in H7_LADDER:
        if label == source:
            return regime
    for rel, label, regime in H8_SESSIONS:
        if label == source:
            return regime
    if source == "W04-H8C-box-600s":
        return "return_path_replaced"
    if source == "W04-H6-10pct":
        return "return_path_high_resistance"
    return "not_applicable_off_state"


def source_files(repo_root: pathlib.Path, bench_root: pathlib.Path | None) -> dict[str, str]:
    """The on-disk locator behind each source label, for the provenance table.

    Every value is a MACHINE-INDEPENDENT locator, never a developer absolute
    path: committed sources are repository-relative, local-bench sources are
    prefixed with the ``<local-bench>`` marker and are relative to the bench
    root the operator passed with ``--bench-root``. A pinned artifact that
    carried ``C:\\Users\\...`` could not be reproduced or reviewed elsewhere,
    so the generators refuse to emit one (see validate_w08.py).
    """
    out = {
        "W04-H8C-box-600s": H8_CSV,
        "W04-H6-10pct": H6_CSV,
        "W04-G1-production-failclosed": G1_TELEMETRY,
        "W03-132b-off-envelope": W03_OFF_132B,
        "W03-pzem-off-2026-10-20": W03_OFF_2026_10_20,
    }
    if bench_root is not None:
        for rel, label, _regime in H7_LADDER:
            out[label] = LOCAL_BENCH_MARKER + rel
        for rel, label, _regime in H8_SESSIONS:
            out[label] = LOCAL_BENCH_MARKER + rel
    return out


def assert_no_physical_claim(report: object) -> None:
    """Refuse any structure that carries the physical label.

    Nothing produced by host analysis may promote itself to ``PHYSICALLY_VERIFIED``
    - this guard fires the moment somebody routes a status string through here,
    including a report whose source name merely contains the token.
    """
    text = json.dumps(report, sort_keys=True, default=str)
    if FORBIDDEN_STATUS in text:
        raise ValueError(f"{FORBIDDEN_STATUS} must never be emitted by cg_w08_envelope")


def build_envelope(repo_root: pathlib.Path,
                   bench_root: pathlib.Path | None,
                   transport: bool = True) -> dict[str, object]:
    sources = load_sources(repo_root, bench_root)
    all_frames = [frame for frames in sources.values() for frame in frames]

    per_source: dict[str, object] = {}
    duty_table: dict[str, list[dict[str, object]]] = {}
    for source, frames in sorted(sources.items()):
        used = [f for f in frames if f.classification == DRIVEN]
        duty_values = sorted({f.duty_applied for f in used})
        summary: dict[str, object] = {
            "trust": "COMMITTED" if source in COMMITTED_SOURCES else "LOCAL_BENCH",
            "regime": source_regime(source),
            "frames": len(frames),
            "duty_applied_permille": duty_values[0] if duty_values else None,
            "duty_applied_permille_values": duty_values,
            "drive": drive_stats(frames),
            "off": off_stats(frames),
            "thermal": thermal_response(frames),
            "power_consistency": power_consistency(frames),
            "energy_consistency": energy_consistency(frames),
            "status_coverage": status_coverage(frames)[source],
            "state_counts": frame_label_counts(frames, "state"),
            "stop_reason_counts": frame_label_counts(frames, "stop_reason"),
            "fault_bits_counts": frame_label_counts(frames, "fault_bits"),
            "snapshot_counts": frame_label_counts(frames, "snapshot"),
        }
        per_source[source] = summary
        for duty in duty_values:
            entry = {"source": source, "trust": summary["trust"],
                     "regime": summary["regime"],
                     **drive_stats([f for f in frames if f.duty_applied == duty])}
            duty_table.setdefault(str(duty), []).append(entry)

    report: dict[str, object] = {
        "schema": "cg-w08-envelope-1",
        "status_label": "REAL_DATA_ANALYZED",
        "forbidden_status_emitted": False,
        "local_bench_sources_present": bench_root is not None and bench_root.is_dir(),
        "off_register_latency_rule": {
            "pre_run_register": "first frame of a driven block with 0.00 A while the "
                                "applied duty is nonzero",
            "outputs_off_register": f"duty-0 frame within {POST_OFF_HOLD_POLL_MS} ms of "
                                    "the last driven frame with current above the steady "
                                    "floor: the first post-OFF poll returns the last "
                                    "loaded registers (byte-identical in the committed "
                                    "600 s capture)",
            "off_settling": f"duty-0 frame within {OFF_SETTLE_MAX_MS} ms of the last "
                            "driven frame with current above the steady floor",
            "off_residual_above_floor": f"duty-0 frame above the steady floor outside "
                                        f"{OFF_SETTLE_MAX_MS} ms: named, excluded, never "
                                        "averaged",
            "suspect_zero_current": "driven frame with 0.00 A that is not first in its "
                                    "block - reported, never dropped",
            "settle_window_ms": OFF_SETTLE_MAX_MS,
            "hold_window_ms": POST_OFF_HOLD_POLL_MS,
            "steady_floor_a": OFF_STEADY_MAX_A,
        },
        "sources": per_source,
        "by_duty_permille": {k: sorted(v, key=lambda e: e["source"])
                             for k, v in sorted(duty_table.items(), key=lambda kv: int(kv[0]))},
        "status_coverage": status_coverage(all_frames),
        "holdover_frames": holdover_rows(all_frames),
        "duty_zero_with_current_frames": duty_zero_with_current(all_frames),
        "source_files": source_files(repo_root, bench_root),
    }
    if transport and bench_root is not None and bench_root.is_dir():
        transport_quality = {}
        for rel, label, _regime in H7_LADDER:
            path = bench_root / rel
            if path.is_file():
                transport_quality[label] = read_h7_transport(path)
        report["h7_transport_quality"] = transport_quality
    assert_no_physical_claim(report)
    return report


def frame_label_counts(frames: list[Frame], attribute: str) -> dict[str, int]:
    """Counts of a string field over frames - the honest way to list stop reasons."""
    out: dict[str, int] = {}
    for frame in frames:
        key = str(getattr(frame, attribute, "") or "(empty)")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _csv_escape(value: str) -> str:
    if any(character in value for character in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def render_duty_csv(envelope: dict[str, object]) -> str:
    header = [
        "duty_permille_applied", "source", "trust", "series_path_regime",
        "frames_used", "frames_excluded", "excluded_classes",
        "current_min_a", "current_p05_a", "current_median_a", "current_mean_a",
        "current_p95_a", "current_max_a",
        "voltage_min_v", "voltage_median_v", "voltage_max_v",
        "power_min_w", "power_median_w", "power_mean_w", "power_p95_w", "power_max_w",
        "mean_current_incl_holdovers_a", "mean_current_excl_holdovers_a",
        "electrical_status_recorded",
    ]
    lines = [",".join(header)]
    for duty, entries in envelope["by_duty_permille"].items():
        for entry in entries:
            current = entry["current_a"]
            voltage = entry["voltage_v"]
            power = entry["power_w"]
            lines.append(",".join(_csv_escape(_fmt(v)) for v in [
                duty, entry["source"], entry["trust"], entry["regime"],
                entry["frames_used"], entry["frames_excluded"],
                "|".join(entry["excluded_classes"]),
                current.get("min"), current.get("p05"), current.get("median"),
                current.get("mean"), current.get("p95"), current.get("max"),
                voltage.get("min"), voltage.get("median"), voltage.get("max"),
                power.get("min"), power.get("median"), power.get("mean"),
                power.get("p95"), power.get("max"),
                entry["mean_current_a_inclusive_of_holdovers"],
                entry["mean_current_a_excluding_holdovers"],
                "true" if entry["electrical_status_recorded"] else "false",
            ]))
    return "\n".join(lines) + "\n"


def render_holdover_csv(envelope: dict[str, object]) -> str:
    columns = [
        "source", "seq", "clock_ms", "state", "stage", "duty_applied_permille",
        "voltage_v", "current_a", "power_w", "energy_wh", "classification", "note",
    ]
    lines = [",".join(columns)]
    rows = sorted(envelope["holdover_frames"],
                  key=lambda row: (row["source"], _seq_key(row["seq"]),
                                   float(row["clock_ms"] or 0)))
    for row in rows:
        lines.append(",".join(_csv_escape(_fmt(row.get(column))) for column in columns))
    return "\n".join(lines) + "\n"


def render_duty_zero_current_csv(envelope: dict[str, object]) -> str:
    columns = [
        "source", "seq", "clock_ms", "state", "stage", "stop_reason",
        "duty_req_permille", "duty_applied_permille", "duty_readback_permille",
        "voltage_v", "current_a", "power_w", "energy_wh", "t2_c",
        "classification", "electrical_status_recorded", "note",
    ]
    lines = [",".join(columns)]
    rows = sorted(envelope["duty_zero_with_current_frames"],
                  key=lambda row: (row["source"], _seq_key(row["seq"]),
                                   float(row["clock_ms"] or 0)))
    for row in rows:
        lines.append(",".join(
            _csv_escape(_fmt(True if row.get(c) is True else
                             False if row.get(c) is False else row.get(c)))
            for c in columns))
    return "\n".join(lines) + "\n"


def _seq_key(seq: object) -> int:
    try:
        return int(str(seq))
    except (TypeError, ValueError):
        return 0


def render_status_coverage_csv(envelope: dict[str, object]) -> str:
    header = [
        "source", "frames", "qualification_level", "column",
        "frames_with_a_value", "frames_without_a_label", "label_counts",
        "qualified", "electrical_status_recorded",
    ]
    lines = [",".join(header)]
    for source, coverage in sorted(envelope["status_coverage"].items()):
        for column in ELECTRICAL_FIELDS:
            entry = coverage["columns"][column]
            counts = json.dumps(entry["label_counts"], sort_keys=True)
            lines.append(",".join(_csv_escape(v) for v in [
                source, str(coverage["frames"]), coverage["qualification_level"], column,
                str(entry["frames_with_a_value"]), str(entry["frames_without_a_label"]),
                counts, "true" if entry["qualified"] else "false",
                "true" if coverage["electrical_status_recorded"] else "false",
            ]))
    return "\n".join(lines) + "\n"


def render_source_summary_csv(envelope: dict[str, object]) -> str:
    header = [
        "source", "trust", "series_path_regime", "frames",
        "duty_applied_permille", "driven_frames_used", "driven_frames_excluded",
        "current_median_a", "current_p95_a", "current_max_a",
        "power_median_w", "power_max_w", "voltage_min_v", "voltage_max_v",
        "off_steady_max_current_a", "off_excluded_frames", "off_excluded_max_current_a",
        "energy_counter_delta_wh", "energy_integral_wh", "energy_verdict",
        "power_consistency_verdict", "power_max_abs_delta_w",
        "electrical_status_recorded",
    ]
    lines = [",".join(header)]
    for source, summary in sorted(envelope["sources"].items()):
        drive, off = summary["drive"], summary["off"]
        current, power, voltage = drive["current_a"], drive["power_w"], drive["voltage_v"]
        energy, powerc = summary["energy_consistency"], summary["power_consistency"]
        lines.append(",".join(_csv_escape(_fmt(v)) for v in [
            source, summary["trust"], summary["regime"], summary["frames"],
            summary["duty_applied_permille"], drive["frames_used"], drive["frames_excluded"],
            current.get("median"), current.get("p95"), current.get("max"),
            power.get("median"), power.get("max"), voltage.get("min"), voltage.get("max"),
            off.get("steady_max_current_a"), off.get("excluded_register_frames"),
            off.get("excluded_max_current_a"),
            energy.get("counter_delta_wh"), energy.get("trapezoidal_integral_of_power_wh"),
            energy.get("verdict"), powerc.get("verdict"), powerc.get("max_abs_delta_w"),
            "true" if summary["status_coverage"]["electrical_status_recorded"] else "false",
        ]))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# envelope -> operating-envelope-v1.yaml
# --------------------------------------------------------------------------

def render_yaml(envelope: dict[str, object]) -> str:
    """Emit the envelope as the canonical ``operating-envelope-v1.yaml``.

    Hand-written emitter (this repository has no PyYAML dependency anywhere),
    driven by exactly the dict that produced the CSVs, so the YAML and the CSV
    can never disagree.
    """
    h8 = envelope["sources"].get("W04-H8C-box-600s", {})
    h8_drive = h8.get("drive", {}) or {}
    h8_off = h8.get("off", {}) or {}
    g1 = envelope["sources"].get("W04-G1-production-failclosed", {})
    rule = envelope["off_register_latency_rule"]
    lines: list[str] = [
        "# A-W08-01 observed operating envelope, version 1.",
        "# Generated by firmware/tools/cg_w08_envelope.py through",
        "#   evidence/A/W08/build_w08_artifacts.py.",
        "# Every range below is an OBSERVATION of a past supervised session on one",
        "# bench, one board, one PSU and one ambient condition. It is not a certified",
        "# limit, not an envelope the plant may be exercised at, and not physically",
        "# verified by any host analysis here. Values whose source is not committed in",
        "# git carry trust: LOCAL_BENCH and reproducible_from_git: false.",
        "schema: cg-w08-envelope-1",
        f"status_label: {envelope['status_label']}",
        f"git_only_derivation: "
        f"{'true' if not envelope['local_bench_sources_present'] else 'false'}",
        "",
        "allowed_action_state:",
        "  production_build_w04_w06:",
        f"    frames_observed: {g1.get('frames')}",
        "    output_stage: DISABLED          # coldguard_config.h compiles the stage out",
        "    requested_duty_permille: 0      # cg_tec_limits.h: six limits UNRESOLVED",
        "    actuator_enable: disallowed",
        "    electrical_values_published: none   # schema labels them NO_DATA, cells empty",
        "    start_gate: 'cg_tec_limits_all_resolved() gates cg_tec_start()'",
        "    status: REAL_DATA_ANALYZED",
        "  bench_images_h6_h7_h8:",
        "    states_observed: [OFF, ARMED, COOLING, COOLDOWN]",
        "    gated_by: [operator_present_at_psu, supervised_authorized, snapshot_valid,",
        "              arm_ttl, duty_readback_match, off_current_gate]",
        "    status: REAL_DATA_ANALYZED",
        "    note: the bench images are not the delivered firmware and were never",
        "          built from this branch",
        "",
        "healthy_current_range_a:",
    ]
    for duty, entries in sorted(envelope["by_duty_permille"].items(),
                                key=lambda item: int(item[0])):
        for entry in entries:
            current = entry["current_a"]
            if not current.get("count"):
                continue
            lines += [
                f"  - duty_permille: {duty}",
                f"    source: {entry['source']}",
                f"    trust: {entry['trust']}",
                f"    reproducible_from_git: "
                f"{'true' if entry['trust'] == 'COMMITTED' else 'false'}",
                f"    series_path_regime: {entry['regime']}",
                f"    frames_used: {entry['frames_used']}",
                f"    frames_excluded: {entry['frames_excluded']}",
                f"    excluded_classes: [{', '.join(entry['excluded_classes'])}]",
                f"    electrical_status_recorded: "
                f"{'true' if entry['electrical_status_recorded'] else 'false'}",
                f"    min: {current['min']}",
                f"    median: {current['median']}",
                f"    mean: {current['mean']}",
                f"    p95: {current['p95']}",
                f"    max: {current['max']}",
            ]
    lines += ["", "healthy_power_range_w:"]
    for duty, entries in sorted(envelope["by_duty_permille"].items(),
                                key=lambda item: int(item[0])):
        for entry in entries:
            power = entry["power_w"]
            if not power.get("count"):
                continue
            lines += [
                f"  - duty_permille: {duty}",
                f"    source: {entry['source']}",
                f"    trust: {entry['trust']}",
                f"    electrical_status_recorded: "
                f"{'true' if entry['electrical_status_recorded'] else 'false'}",
                f"    min: {power['min']}",
                f"    median: {power['median']}",
                f"    mean: {power['mean']}",
                f"    p95: {power['p95']}",
                f"    max: {power['max']}",
            ]
    lines += [
        "",
        "off_current_envelope:",
        f"  steady_max_observed_a: {h8_off.get('steady_max_current_a')}",
        f"  steady_frames: {h8_off.get('steady_frames_used')}",
        f"  steady_nonzero_frames: {h8_off.get('steady_nonzero_frames')}",
        f"  steady_floor_a: {h8_off.get('steady_floor_a')}",
        f"  latency_frames_excluded: {h8_off.get('excluded_register_frames')}",
        f"  latency_excluded_peak_a: {h8_off.get('excluded_max_current_a')}",
        f"  bench_gate_limit_a: {h8_off.get('bench_off_current_limit_a')}",
        f"  provenance: {h8_off.get('off_current_limit_provenance')}",
        "  rule: see off_register_latency_rule below; the excluded frames are listed",
        "        individually in holdover-frames.csv and duty-zero-current-frames.csv",
        "  status: REAL_DATA_ANALYZED",
        "",
        "off_register_latency_rule:",
        f"  pre_run_register: {rule['pre_run_register']}",
        f"  outputs_off_register: {rule['outputs_off_register']}",
        f"  off_settling: {rule['off_settling']}",
        f"  off_residual_above_floor: {rule['off_residual_above_floor']}",
        f"  suspect_zero_current: {rule['suspect_zero_current']}",
        f"  hold_window_ms: {rule['hold_window_ms']}",
        f"  settle_window_ms: {rule['settle_window_ms']}",
        f"  steady_floor_a: {rule['steady_floor_a']}",
        f"  frames_named_not_averaged: {len(envelope['holdover_frames'])}",
        "",
        "thermal_response_window:",
    ]
    for channel, values in sorted((h8.get("thermal") or {}).items()):
        lines += [
            f"  - channel: {channel}",
            f"    as_built_role: {values['as_built_role']}",
            f"    device_reported_role: {','.join(values['device_reported_role'])}",
            f"    min_c: {values['min_c']}",
            f"    max_c: {values['max_c']}",
            f"    spread_k: {values['spread_k']}",
            f"    last_driven_c: {values['last_driven_c']}",
            f"    last_c: {values['last_c']}",
            "    single_channel_observation: true",
        ]
    lines += [
        "  caveat: three of the four channels report role UNASSIGNED in every frame of",
        "          the committed capture; TEC_HOT_SIDE is never averaged into a",
        "          chamber-air statistic, and no channel is labelled COLD_SIDE, so no",
        "          cold-side or junction statement is made anywhere in this envelope",
        "",
        "energy_consistency:",
    ]
    for source, summary in sorted(envelope["sources"].items()):
        energy = summary["energy_consistency"]
        if energy.get("verdict") in (None, "INSUFFICIENT_DATA"):
            continue
        lines += [
            f"  - source: {source}",
            f"    counter_delta_wh: {energy.get('counter_delta_wh')}",
            f"    trapezoidal_integral_of_power_wh: "
            f"{energy.get('trapezoidal_integral_of_power_wh')}",
            f"    residual_wh: {energy.get('counter_minus_integral_wh')}",
            f"    verdict: {energy.get('verdict')}",
            "    counter_has_no_validity_token: true",
        ]
    lines += [
        "",
        "power_consistency_v_times_i:",
    ]
    for source, summary in sorted(envelope["sources"].items()):
        power = summary["power_consistency"]
        if not power.get("frames_compared"):
            continue
        lines += [
            f"  - source: {source}",
            f"    frames_compared: {power['frames_compared']}",
            f"    max_abs_delta_w: {power['max_abs_delta_w']}",
            f"    mean_abs_delta_w: {power['mean_abs_delta_w']}",
            f"    tolerance_w: {power['quantisation_tolerance_w']}",
            f"    frames_beyond_tolerance: {power['frames_beyond_tolerance_count']}",
            f"    verdict: {power['verdict']}",
        ]
    lines += [
        "",
        "stop_conditions_observed:",
        "  - stop_reason: STAGE_DEADLINE",
        "    meaning: stage timer expiry at the requested duration",
        "    observed_in: [W04-H8C-box-600s, H8-B-420s, H8-C-600s-2026-10-31, H8-D-900s,",
        "                  H8-E-1800s]",
        "  - stop_reason: TIMEOUT",
        "    meaning: H7 guard timer at 60.000 s (source=guard_timer)",
        "    observed_in: [H7-20pct .. H7-100pct]",
        "  - stop_reason: ACTUATOR",
        "    meaning: H8-A start self-check refused, fail-closed, no drive applied",
        "    observed_in: [H8-A retry session before the enable fix]",
        "  - stop_reason: HOST_ACK_LOST",
        "    meaning: the monitor withheld the zero-current ACK and the stage aborted",
        "    observed_in: [H8-A retry session]",
        "  - stop_reason: NONE",
        "    meaning: idle frames before the stage started",
        f"    fault_bits_observed_in_the_committed_600s_capture: "
        f"{_fmt((h8.get('fault_bits_counts') or {}))}",
        "",
        "do_not_extrapolate:",
        "  - the TEC has no continuous rating in this repository; the 55 degC hot-side",
        "    limit was PROVISIONAL and the fleet rating is unstated",
        "  - duty levels between the measured points are not characterised",
        "  - the 20-60 % ladder was recorded through a degraded return path and is not",
        "    comparable with the 70-100 % ladder at the same duty",
        "  - every range above is a past-session observation on one bench, one board,",
        "    one PSU and one ambient condition",
        "  - no value here is a limit, a rating, or a permission to energize",
        "",
        "open_inputs_blocking_a_frozen_envelope:",
        "  - id: A-W08-02",
        "    status: BLOCKED_HARDWARE",
        "    gap: the installed ampacity basis of the branch conductor (recorded as a",
        "         1.75 mm copper core diameter, i.e. ~2.405 mm2 only if it is round",
        "         solid; insulation class, run length and bundling are unrecorded) and",
        "         the fuse body marking",
        "  - id: A-W04-02",
        "    status: TEAM_DEPENDENCY",
        "    gap: conductor class deviation against the canonical 2 x 2.5 mm2 ask; the",
        "         derived 2.405 mm2 is a ~4 % area gap under a solid-round assumption,",
        "         not a nominal 2.5 mm2 claim, and HW-19 stays UNVERIFIED",
        "  - id: A-W08-03",
        "    status: NEED_USER_ACTION",
        "    gap: terminals/IBT-2 abnormal behaviour under a long run is an operator",
        "         observation; no recorded frame measures it",
        "  - id: A-W08-04",
        "    status: TEAM_DEPENDENCY",
        "    gap: SAFE_LOCAL is Member D's policy state; firmware observes inputs, it",
        "         does not decide the mode",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    parser.add_argument(
        "--bench-root", type=pathlib.Path, default=DEFAULT_BENCH_ROOT,
        help="root of Member A's local W04 tree (H7/H8 raw sessions, not in git)",
    )
    parser.add_argument("--no-local", action="store_true",
                        help="restrict the analysis to sources committed in git")
    parser.add_argument("--json", type=pathlib.Path, help="write the full envelope JSON")
    args = parser.parse_args(argv)

    bench = None if args.no_local else args.bench_root
    envelope = build_envelope(args.repo_root, bench)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8", newline="\n")
        print(f"wrote {args.json}")

    print(f"sources analysed            : {len(envelope['sources'])}")
    print(f"local bench sources present : {envelope['local_bench_sources_present']}")
    for source, summary in sorted(envelope["sources"].items()):
        drive = summary["drive"]
        current = drive["current_a"]
        coverage = summary["status_coverage"]
        flag = "qualified" if coverage["electrical_status_recorded"] else "UNQUALIFIED"
        if current.get("count"):
            print(f"  {source:32s} duty={summary['duty_applied_permille']:>4} "
                  f"used={drive['frames_used']:4} excluded={drive['frames_excluded']} "
                  f"I med={current['median']} p95={current['p95']} "
                  f"mean={current['mean']} max={current['max']} [{flag}]")
        else:
            off = summary["off"]
            print(f"  {source:32s} no driven frames; off steady max "
                  f"{off.get('steady_max_current_a')} A over "
                  f"{off.get('steady_frames_used')} frames [{flag}]")
    print(f"latency/suspect frames      : {len(envelope['holdover_frames'])}")
    print(f"duty-0 frames with current  : "
          f"{len(envelope['duty_zero_with_current_frames'])}")
    unqualified = [
        source for source, coverage in envelope["status_coverage"].items()
        if not coverage["electrical_status_recorded"]
    ]
    print(f"sources with unqualified V/I/P: {sorted(unqualified)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
