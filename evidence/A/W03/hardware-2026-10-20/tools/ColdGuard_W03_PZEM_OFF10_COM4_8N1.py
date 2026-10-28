#!/usr/bin/env python3
"""ColdGuard W03: create pzem-off.csv using the EXISTING V4 8N1 ESP32 read-only firmware.

PC COM4 (USB CDC) sends only text commands CFG and MEAS to ESP32.
ESP32 GPIO36/GPIO37 -> TTL485 -> PZEM-017; firmware handles FC03/FC04.
This script never sends raw Modbus, FC06, or a TEC/IBT-2 command.

Requires: py -m pip install pyserial
Usage: py ColdGuard_W03_PZEM_OFF10_COM4_8N1.py COM4
Close Arduino Serial Monitor first (COM4 is exclusive).
"""
import csv
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

DURATION_SECONDS = 600
SAMPLE_COUNT = DURATION_SECONDS + 1  # 0..600 seconds => >=10-minute span
BAUD = 115200
CONFIG_RE = re.compile(r"^#CFG_PASS\b.*\bslave=1\b.*\bshunt_reg=0x0001\b.*\bprofile=50A\b")
MEAS_RE = re.compile(
    r"^#MEAS_PASS\s+n=1\s+voltage_v=(?P<voltage>-?[0-9.]+)\s+"
    r"current_a=(?P<current>-?[0-9.]+)\s+power_w=(?P<power>-?[0-9.]+)\s+"
    r"energy_wh=(?P<energy>\d+)\b"
)
RESULT_RE = re.compile(
    r"^#W3_RESULT\s+logical_pass=(?P<pass>\d+)/(?P<target>\d+)\s+"
    r"logical_fail=(?P<fail>\d+)\s+physical_pass=(?P<physical_pass>\d+)\s+"
    r"physical_fail=(?P<physical_fail>\d+)\s+recovered=(?P<recovered>\d+)\s+"
    r"crc_candidate_attempts=(?P<crc>\d+)\s+echo_attempts=(?P<echo>\d+)\b"
)
FIELDS = ["sample", "timestamp_local", "elapsed_s", "voltage_v", "current_a", "power_w",
          "energy_wh", "quality", "physical_fail", "crc_candidate_attempts", "echo_attempts", "error"]


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def capture_command(port, command, raw_log, timeout_s=3.0):
    """Collect one V4 firmware command's output, bounded by #RUN_DONE."""
    port.reset_input_buffer()  # only BEFORE command: remove old boot/status text
    port.write((command + "\n").encode("ascii"))
    port.flush()
    lines = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        lines.append(line)
        raw_log.write(f"{timestamp()} [{command}] {line}\n")
        raw_log.flush()
        if line.startswith("#RUN_DONE "):
            break
    return lines


def verified_preflight(lines):
    result = next((RESULT_RE.match(line) for line in lines if RESULT_RE.match(line)), None)
    return (any(CONFIG_RE.match(line) for line in lines)
            and result is not None
            and result.group("pass") == "1" and result.group("target") == "1"
            and result.group("physical_fail") == "0"
            and any(line.startswith("#RUN_DONE ") for line in lines))


def parse_meas(lines):
    frame = next((MEAS_RE.match(line) for line in lines if MEAS_RE.match(line)), None)
    result = next((RESULT_RE.match(line) for line in lines if RESULT_RE.match(line)), None)
    done = any(line.startswith("#RUN_DONE ") for line in lines)
    success = (frame is not None and result is not None and done
               and result.group("pass") == "1" and result.group("target") == "1"
               and result.group("fail") == "0" and result.group("physical_pass") == "1"
               and result.group("physical_fail") == "0" and result.group("recovered") == "0")
    if success:
        return {
            "voltage_v": frame.group("voltage"), "current_a": frame.group("current"),
            "power_w": frame.group("power"), "energy_wh": frame.group("energy"),
            "quality": "CRC_VALID", "physical_fail": "0",
            "crc_candidate_attempts": result.group("crc"),
            "echo_attempts": result.group("echo"), "error": ""
        }
    bad_line = next((line for line in lines if line.startswith("#FAIL ")), "")
    return {
        "voltage_v": "", "current_a": "", "power_w": "", "energy_wh": "",
        "quality": "INVALID", "physical_fail": result.group("physical_fail") if result else "",
        "crc_candidate_attempts": result.group("crc") if result else "",
        "echo_attempts": result.group("echo") if result else "",
        "error": (bad_line or ("missing_RUN_DONE" if not done else "missing_or_inconsistent_result"))[:350]
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: py ColdGuard_W03_PZEM_OFF10_COM4_8N1.py COM4")
        return 2
    port_name = sys.argv[1]
    csv_file = Path.cwd() / "pzem-off.csv"
    log_file = Path.cwd() / "pzem-off-serial.log"
    if csv_file.exists() or log_file.exists():
        print("#STOP Files pzem-off.csv / pzem-off-serial.log already exist. Rename/back them up first; never overwrite evidence.")
        return 2
    print("#SAFETY This script sends ONLY CFG and MEAS over USB COM4 to the read-only V4 8N1 firmware.")
    print("#SAFETY No software command here can set TEC OFF. Confirm TEC/IBT-2 is PHYSICALLY OFF, safely powered, and the PZEM supply is correct.")
    print("#SAFETY USB-RS485 COM5 remains disconnected; Arduino Serial Monitor must be CLOSED.")
    try:
        confirmed = input("Type OFF to confirm external TEC OFF and proceed: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n#STOP Not confirmed")
        return 2
    if confirmed != "OFF":
        print("#STOP Not confirmed")
        return 2
    try:
        import serial
    except ImportError:
        print("#STOP Missing pyserial. Run: py -m pip install pyserial")
        return 2

    try:
        with serial.Serial(port_name, BAUD, timeout=0.15, write_timeout=2.0) as port:
            print(f"#PORT_OPEN {port_name} baud={BAUD} -- waiting for possible ESP32 reset")
            time.sleep(3)
            # File creation is after successful port open so a busy COM port doesn't leave stale files.
            with log_file.open("x", encoding="utf-8", newline="\n") as raw_log:
                raw_log.write(f"{timestamp()} #SESSION_START port={port_name} span_target_s={DURATION_SECONDS} uart_pzem=9600_8N1 firmware_expected=ColdGuard_W03_TTL485_V4_8N1_TEST\n")
                print("#PREFLIGHT Sending CFG; requiring slave=1, shunt=50A, CRC-valid readback")
                preflight = capture_command(port, "CFG", raw_log, 3.0)
                if not verified_preflight(preflight):
                    print("#STOP PREFLIGHT_FAIL. No CSV created. Actual lines:")
                    for l in preflight:
                        print(l)
                    return 3
                print("#PREFLIGHT PASS shunt=50A slave=1 read_only_firmware")
                total_ok = total_bad = 0
                count = 0
                started = time.monotonic()
                # x mode: never overwrite earlier raw evidence.
                with csv_file.open("x", encoding="utf-8", newline="") as out:
                    writer = csv.DictWriter(out, fieldnames=FIELDS)
                    writer.writeheader()
                    out.flush()
                    try:
                        for i in range(SAMPLE_COUNT):
                            target = started + i
                            wait = target - time.monotonic()
                            if wait > 0:
                                time.sleep(wait)
                            stamp = timestamp()
                            elapsed = time.monotonic() - started
                            lines = capture_command(port, "MEAS", raw_log, 2.5)
                            fields = parse_meas(lines)
                            fields.update({"sample": i + 1, "timestamp_local": stamp,
                                           "elapsed_s": f"{elapsed:.3f}"})
                            writer.writerow(fields)
                            out.flush()  # preserve completed samples on interruption
                            count += 1
                            if fields["quality"] == "CRC_VALID":
                                total_ok += 1
                            else:
                                total_bad += 1
                                print(f"#SAMPLE_INVALID n={count} elapsed_s={elapsed:.1f} reason={fields['error']}")
                            if count % 30 == 0 or count == SAMPLE_COUNT:
                                print(f"#OFF10_PROGRESS n={count}/{SAMPLE_COUNT} valid={total_ok} invalid={total_bad} elapsed_s={elapsed:.1f}")
                    except KeyboardInterrupt:
                        print("\n#INTERRUPTED Partial CSV retained; cannot claim 10-minute PASS")
                last_elapsed = time.monotonic() - started  # only after last sample returns
                # Duration is checked against start of the final issued sample in the CSV,
                # not serial processing time after a partially completed final request.
                actual_span = elapsed if count else 0
                complete = count == SAMPLE_COUNT and actual_span >= DURATION_SECONDS
                gate = ("PASS" if complete and total_bad == 0 else
                        "COLLECTED_WITH_ERRORS" if complete else "INCOMPLETE")
                summary = (f"#OFF10_RESULT gate={gate} samples={count}/{SAMPLE_COUNT} "
                           f"valid={total_ok} invalid={total_bad} sample_span_s={actual_span:.3f} "
                           f"runtime_s={last_elapsed:.3f} csv={csv_file.name} raw_log={log_file.name}")
                print(summary)
                raw_log.write(f"{timestamp()} {summary}\n")
                raw_log.flush()
                return 0 if gate == "PASS" else 1
    except (OSError, ValueError) as e:
        print(f"#STOP Serial/file error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
