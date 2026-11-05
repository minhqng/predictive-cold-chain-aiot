"""ColdGuard W06 command-lifecycle trace (docs/05A A-W06-05; stdlib only).

docs/02 §33 separates the command lifecycle into stages that are NOT the same
claim:

```text
backend command -> device accept -> applied -> electrical verified
                                                       -> thermal verified
```

This tool reads a serial capture and reports, per `command_id`, how far down that
chain evidence actually exists - and names the first stage where it does not.

It exists because the stages are easy to conflate. An `ACCEPTED` ACK is protocol
evidence (docs/02 §32.2, lines 2188-2197: "device handled the command according to
protocol/local validation"), not proof that current flowed or that the chamber
moved. The tool therefore never promotes a stage:

* frames are attributed to a command only from the **same `boot_id`** and at or
  after the ACK, because a device timestamp from another boot is a different time
  axis;
* `ELECTRICAL_VERIFIED` needs a **fresh** reading (`current_status=OK`) and a
  `current_status` of `STALE`/`INVALID`/`NO_DATA` never counts, whatever number it
  carries;
* `THERMAL_VERIFIED` needs movement in the **direction the command requested** -
  cooling ON must be followed by a fall, OFF by a rise - because spread alone is
  what a warm chamber produces with nothing driving it;
* `APPLIED_STATE` is added only when the applied evidence exists, so `reached.*`
  counts are stages actually attained and never a step taken toward one;
* a replay that reported `reapplied=1` is flagged as the idempotency violation it
  is, even if the ACK status says `DUPLICATE_CANONICAL`.

A command that acknowledged ACCEPTED but never reached applied evidence is reported
`blocked_at=APPLIED_STATE` with the reason, and the summary counts it under
`NOT_APPLIED`.

Real physical traces need an energized, supervised bench session (and a backend
to issue the command at all). What this slice can honestly produce is:

* the record format and the promotion rules, executable and tested;
* a trace built from the injected host-harness sequences, clearly labelled
  synthetic;
* the empty-but-correct report against the committed W04/W05 captures, which is
  `no command lines present` - the absence of a fake lifecycle is the point.

Usage:
    py firmware/tools/cg_command_trace.py <capture.log> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import cg_telemetry_schema as telemetry_schema  # noqa: E402

CMDACK_PREFIX = "#CG CMDACK"

STAGES = (
    "COMMAND_SEEN",
    "DEVICE_ACK",
    "APPLIED_STATE",
    "ELECTRICAL_VERIFIED",
    "THERMAL_VERIFIED",
)

# A canonical command may be issued with a duty ceiling the device cannot accept.
ACCEPT_STATUSES = ("ACCEPTED", "DUPLICATE_CANONICAL")

_MIN_CURRENT_A = 0.05  # PZEM-017 LSB is 0.01 A; this is a named analysis floor.
# Smallest chamber movement counted as a response. One DS18B20 LSB is 0.0625 C, so
# four LSBs across the attributed frames is above sensor noise and below any
# deliberate bench treatment. An analysis choice, not a contract threshold.
_THERMAL_MIN_DELTA_C = 0.25


def _fields(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        out[key] = value
    return out


def parse_capture(lines) -> dict[str, dict[str, object]]:
    """Return per-command_id records built from ACK lines and later telemetry."""
    commands: dict[str, dict[str, object]] = {}
    frames: list[dict[str, str]] = []
    ack_re = re.compile(r"^\s*#CG CMDACK ")

    for raw in lines:
        text = raw.rstrip("\r\n")
        if ack_re.match(text):
            fields = _fields(text.split(" ")[2:])
            command_id = fields.get("command_id")
            if not command_id or command_id == "NONE":
                continue
            record = commands.setdefault(command_id, {"acks": [], "frames_after": []})
            record["acks"].append(fields)
            continue
        if text.startswith(telemetry_schema.PREFIX):
            try:
                record = telemetry_schema.parse_line(text)
            except telemetry_schema.TelemetryError:
                continue
            frames.append(record.raw_fields)

    # Attribute each frame to the most recent ACK at or before its uptime.
    for command_id, record in commands.items():
        first_ack_uptime = min(
            (int(a["uptime_ms"]) for a in record["acks"] if a.get("uptime_ms", "").isdigit()),
            default=None,
        )
        if first_ack_uptime is None:
            continue
        ack_boot = next((a.get("boot_id") for a in record["acks"] if a.get("boot_id")), None)
        record["ack_uptime_ms"] = first_ack_uptime
        record["ack_boot_id"] = ack_boot
        attributed = []
        for frame in frames:
            uptime = frame.get("uptime_ms", "")
            if not uptime.isdigit() or int(uptime) < first_ack_uptime:
                continue
            # A frame from another boot is a different clock axis: comparing its
            # uptime_ms against this ACK would order events that never coexisted.
            if ack_boot is not None and frame.get("boot_id") not in (None, ack_boot):
                continue
            attributed.append(frame)
        record["frames_after"] = attributed[:10]
    return commands


def evaluate(commands: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for command_id, record in sorted(commands.items()):
        acks = record["acks"]
        first = acks[0]
        statuses = [str(a.get("status", "MISSING")) for a in acks]
        reapplied = [str(a.get("reapplied", "MISSING")) for a in acks]
        row: dict[str, object] = {
            "command_id": command_id,
            "source": first.get("source", "MISSING"),
            "command_id_form": first.get("command_id_form", "MISSING"),
            "ack_statuses": statuses,
            "ack_reasons": [str(a.get("reason", "MISSING")) for a in acks],
            "desired_cooling": first.get("desired_cooling", "MISSING"),
            "desired_duty_permille": first.get("desired_duty_permille", "MISSING"),
            "applied_cooling_at_ack": first.get("applied_cooling", "MISSING"),
            "expiry_evaluable": first.get("expiry_evaluable", "MISSING"),
            "reapplied_flags": reapplied,
            "boot_id": record.get("ack_boot_id") or first.get("boot_id", "MISSING"),
            "stages": ["COMMAND_SEEN"],
            "blocked_at": None,
            "notes": [],
        }

        if "1" in reapplied:
            # docs/02 §30.1: a duplicate must not create a second independent
            # application. Reading the flag, not just the status, is what catches
            # a firmware that labels a replay DUPLICATE_CANONICAL and applies
            # anyway.
            row["notes"].append(
                "an ACK reported reapplied=1: the replay applied a second time, which "
                "docs/02 §30.1 (line 2118) forbids regardless of its status label"
            )

        # DEVICE_ACK is earned by an ACK line existing; APPLIED_STATE is earned
        # only by applied evidence. Steps are appended when reached, never
        # pre-added, so reached.* counts stay honest.
        row["stages"].append("DEVICE_ACK")
        if len(acks) > 1 and "DUPLICATE_CANONICAL" not in statuses:
            row["notes"].append(
                "more than one ACK for this command_id and none is labelled "
                "DUPLICATE_CANONICAL: idempotency did not answer the replay"
            )

        if statuses[0] not in ACCEPT_STATUSES:
            row["blocked_at"] = "DEVICE_ACK"
            row["notes"].append(
                f"first ACK was {statuses[0]}/{row['ack_reasons'][0]}; nothing beyond the "
                "acknowledgement is claimed"
            )
            rows.append(row)
            continue

        frames = record.get("frames_after") or []
        applied_on = [f for f in frames if f.get("cooling_applied") == "ON"]
        if not applied_on:
            row["blocked_at"] = "APPLIED_STATE"
            row["notes"].append(
                f"no telemetry frame from boot_id={row['boot_id']} after the ACK reported "
                "cooling_applied=ON; an ACCEPTED ACK is protocol evidence, not applied "
                "evidence (docs/02 §32.2, lines 2188-2197)"
            )
            rows.append(row)
            continue
        row["stages"].append("APPLIED_STATE")

        drawn = [
            f for f in applied_on
            if f.get("current_status") == "OK"
            and _as_float(f.get("current_a")) is not None
            and _as_float(f.get("current_a")) >= _MIN_CURRENT_A
        ]
        if not drawn:
            row["blocked_at"] = "ELECTRICAL_VERIFIED"
            row["notes"].append(
                "cooling_applied=ON appeared, but no attributed frame carried a FRESH "
                "(current_status=OK) current at or above the "
                f"{_MIN_CURRENT_A} A analysis floor; a STALE or INVALID reading is not "
                "evidence about the branch"
            )
            rows.append(row)
            continue
        row["stages"].append("ELECTRICAL_VERIFIED")

        direction = _thermal_direction(row["desired_cooling"], drawn)
        if direction is None:
            row["blocked_at"] = "THERMAL_VERIFIED"
            row["notes"].append(
                "electrical activity observed with no chamber movement in the direction the "
                "command requested; a spread of readings alone is not a response, because a "
                "warm chamber drifts by itself"
            )
            rows.append(row)
            continue
        row["stages"].append("THERMAL_VERIFIED")
        row["notes"].append(f"t_inside moved {direction:+.4f} C across attributed frames")
        rows.append(row)
    return rows


def _thermal_direction(desired: object, frames: list[dict[str, str]]) -> float | None:
    """Signed chamber change across the attributed frames, accepted only if it
    goes the way the command asked: cooling ON must fall, OFF must rise."""
    values = [
        _as_float(frame.get("t_inside_c"))
        for frame in frames
        if frame.get("t_inside_status") == "OK"
    ]
    usable = [value for value in values if value is not None]
    if len(usable) < 3:
        return None
    delta = usable[-1] - usable[0]
    if abs(delta) < _THERMAL_MIN_DELTA_C:
        return None
    if desired == "ON" and delta < 0:
        return delta
    if desired == "OFF" and delta > 0:
        return delta
    return None


def _as_float(token: object) -> float | None:
    if not isinstance(token, str) or token == telemetry_schema.MISSING_TOKEN:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def summarize(commands: dict[str, dict[str, object]], rows: list[dict[str, object]]) -> dict:
    return {
        "commands_observed": len(commands),
        "ack_lines": sum(len(record["acks"]) for record in commands.values()),
        "reached": {
            stage: sum(1 for row in rows if stage in row["stages"]) for stage in STAGES
        },
        # Accepted-but-never-applied is the outcome this tool most needs to keep
        # separate from a verified action.
        "not_applied": sum(1 for row in rows if row["blocked_at"] == "APPLIED_STATE"),
        "blocked_at": {
            stage: sum(1 for row in rows if row["blocked_at"] == stage) for stage in STAGES
        },
        "verdict": (
            "NO_COMMAND_LINES_PRESENT"
            if not commands
            else ("TRACED" if any(row["blocked_at"] is None for row in rows) else "PARTIAL")
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=pathlib.Path)
    parser.add_argument("--json", dest="json_out", type=pathlib.Path)
    parser.add_argument("--per-frame", action="store_true",
                        help="include the attributed telemetry frames in the JSON report")
    args = parser.parse_args(argv)

    lines = args.capture.read_text(encoding="utf-8", errors="replace").splitlines()
    commands = parse_capture(lines)
    rows = evaluate(commands)
    report = {
        "capture": args.capture.as_posix(),
        "stages": list(STAGES),
        "electrical_floor_a": _MIN_CURRENT_A,
        "thermal_delta_c": 0.25,
        "summary": summarize(commands, rows),
        "commands": [
            {k: v for k, v in row.items() if k != "frames_after"} for row in rows
        ],
    }
    if args.per_frame:
        # Rows are sorted by command_id while `commands` keeps arrival order, so
        # pairing them positionally would attach the wrong frames whenever the
        # two orders differ. Look the record up by the identity it belongs to.
        by_id = dict(commands)
        for row in report["commands"]:
            row["frames_after"] = by_id[row["command_id"]].get("frames_after", [])

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        print(f"json={args.json_out}")

    summary = report["summary"]
    print(f"verdict={summary['verdict']} commands={summary['commands_observed']} "
          f"ack_lines={summary['ack_lines']}")
    for stage in STAGES:
        print(f"  reached {stage}: {summary['reached'][stage]} "
              f"(blocked here: {summary['blocked_at'][stage]})")
    for row in rows:
        print(f"  {row['command_id']} status={','.join(row['ack_statuses'])} "
              f"blocked_at={row['blocked_at'] or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
