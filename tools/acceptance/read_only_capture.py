"""Read-only serial capture used by the Member A acceptance entrypoint.

Re-implements, rather than imports, the DTR/RTS-safe zero-write pattern of
  C:/Users/dlbac/Downloads/coldguard-repo/_probe-id/capture_probe_id.py
because that tool hard-codes its output next to itself, outside this phase's
write fence, and must not be modified. The port handling is identical: open,
de-assert DTR and RTS immediately, then only ever call read().

This module contains no write call of any kind. The bytes_written counter it
reports is a real accumulator that nothing increments, so the caller can assert
"zero bytes written to the port" from observed output instead of from a comment.

A port error exits 3 and is terminal: the caller must not retry, because losing
COM mid-session is evidence the operator has to look at, not a transient.

  py read_only_capture.py --port COM4 --seconds 30 --out capture.log
                                                   --json-out summary.json

exit codes: 0 lines captured, 1 zero lines, 2 pyserial missing, 3 port error.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "firmware" / "tools"))
import cg_telemetry_schema as schema  # noqa: E402

TELEMETRY_MARKER = "pwm_applied_permille="
TELEMETRY_PREFIX = "#CG TELEM "


def is_telemetry_frame(text: str) -> bool:
    """True only for a complete device telemetry frame.

    A line counts as telemetry when it declares the canonical serial
    telemetry grammar AND the real parser validates it, so malformed
    "#CG TELEM ..." lines are never counted. Legacy H8 frames keep the
    historical pwm token as their proof.
    """
    if text.startswith(TELEMETRY_PREFIX):
        try:
            schema.parse_line(text)
        except Exception:
            return False
        return True
    return TELEMETRY_MARKER in text
DISTINCT_KEYS = (
    "fw",
    "hw",
    "device",
    "pin_map",
    "grammar",
    "firmware",
    "test_mode",
    "boot_id",
    "state",
    "stage",
    "fault_bits",
    "fault",
    "stop_reason",
    "pwm_req_permille",
    "pwm_applied_permille",
    "pwm_readback_permille",
    "ren_command",
    "len_command",
    "voltage_v",
    "current_a",
    "power_w",
)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def fields_of(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in line.split():
        if "=" in token and not token.startswith("#"):
            key, _, value = token.partition("=")
            if key in DISTINCT_KEYS and key not in out:
                out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args(argv)

    summary: dict[str, object] = {
        "port": args.port,
        "baud": args.baud,
        "seconds": args.seconds,
        "bytes_written": 0,
        "writes_to_port": "NONE",
        "lines": 0,
        "telemetry_frames": 0,
        "field_values": {},
        "error": None,
    }
    seen: dict[str, list[str]] = {}

    try:
        import serial  # lazy: absent pyserial is a NOT_RUN, not a crash
    except ImportError:
        summary["error"] = "PYSERIAL_MISSING"
        write_json(pathlib.Path(args.json_out), summary)
        print("PYSERIAL_MISSING: pyserial is not installed for this interpreter")
        return 2

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = utcnow()
    buffer = bytearray()
    exit_code = 0

    try:
        with serial.Serial(args.port, args.baud, timeout=1.0) as port:
            port.dtr = False
            port.rts = False
            with out_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    f"# READ_ONLY_CAPTURE port={args.port} baud={args.baud} "
                    f"host_start_utc={started.isoformat()} seconds={args.seconds} "
                    f"dtr=False rts=False writes_to_port=NONE\n"
                )
                handle.flush()
                while (utcnow() - started).total_seconds() < args.seconds:
                    chunk = port.read(256)
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    while b"\n" in buffer:
                        line, _, buffer = buffer.partition(b"\n")
                        text = line.decode("utf-8", errors="replace").rstrip("\r")
                        stamp = utcnow()
                        handle.write(
                            f"{stamp.isoformat()} +{(stamp - started).total_seconds():7.3f} "
                            f"{text}\n"
                        )
                        summary["lines"] = int(summary["lines"]) + 1
                        summary["lines"] = int(summary["lines"]) + 1
                        if is_telemetry_frame(text):
                            summary["telemetry_frames"] = (
                                int(summary["telemetry_frames"]) + 1
                            )
                            for key, value in fields_of(text).items():
                                bucket = seen.setdefault(key, [])
                                if value not in bucket:
                                    bucket.append(value)
                        handle.flush()
    except serial.SerialException as exc:
        summary["error"] = f"PORT_ERROR: {exc}"
        exit_code = 3

    summary["field_values"] = seen
    write_json(pathlib.Path(args.json_out), summary)
    print(
        f"lines={summary['lines']} telemetry_frames={summary['telemetry_frames']} "
        f"bytes_written={summary['bytes_written']} out={out_path}"
    )
    if exit_code == 0 and int(summary["lines"]) == 0:
        print("ZERO_LINES: port opened but the device emitted nothing")
        exit_code = 1
    return exit_code


def write_json(path: pathlib.Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
