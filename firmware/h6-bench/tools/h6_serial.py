#!/usr/bin/env python3
"""H6 bench console: timestamped capture and command injection.

The console port can only be opened by one process, so commands are injected
by appending lines to a control file that this process watches. Every line
(device output and injected command) is printed with both a monotonic
elapsed stamp and a UTC wall-clock stamp, and appended to --out.

Usage:
  python h6_serial.py --port COM4 --out run.log --control cmd.txt \
      --seconds 90 --exit-on-end --send STATUS

Nothing here touches the device except writing the given ASCII lines plus
LF to the serial port.
"""
import argparse
import datetime
import os
import sys
import time

import serial

EXIT_OK = 0
EXIT_TIMEOUT = 0
EXIT_SERIAL = 1


def utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--out", required=True)
    parser.add_argument("--control", required=True)
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--exit-on-end", action="store_true")
    parser.add_argument("--send", action="append", default=[])
    args = parser.parse_args()

    control_pos = 0
    if os.path.exists(args.control):
        control_pos = os.path.getsize(args.control)

    t0 = time.monotonic()
    buffer = b""

    try:
        port = serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=2)
    except Exception as exc:  # noqa: BLE001 - report and exit
        print(f"serial open failed: {exc}", file=sys.stderr)
        return EXIT_SERIAL

    log = open(args.out, "a", encoding="utf-8")
    log.write(f"# capture start {datetime.datetime.now(datetime.timezone.utc).isoformat()} "
              f"port={args.port} baud={args.baud}\n")
    log.flush()

    def emit(text):
        line = f"[{time.monotonic() - t0:8.3f}] {utc_stamp()} {text}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    def send(command):
        port.write((command + "\n").encode("ascii"))
        port.flush()
        emit(f">>> {command}")

    stop_reason = "timeout"

    with port:
        for command in args.send:
            send(command)
        try:
            while True:
                if time.monotonic() - t0 > args.seconds:
                    break

                data = port.read(4096)
                if data:
                    buffer += data
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        text = raw.decode("utf-8", "replace").rstrip("\r")
                        emit(text)
                        if args.exit_on_end and "H6 END" in text:
                            stop_reason = "end"
                            raise StopIteration

                if os.path.exists(args.control):
                    size = os.path.getsize(args.control)
                    if size > control_pos:
                        with open(args.control, "r", encoding="utf-8") as handle:
                            handle.seek(control_pos)
                            fresh = handle.read()
                        control_pos = size
                        for command in fresh.splitlines():
                            command = command.strip()
                            if command:
                                send(command)

                time.sleep(0.05)
        except StopIteration:
            pass
        except KeyboardInterrupt:
            stop_reason = "keyboard"
        finally:
            log.write(f"# capture end {datetime.datetime.now(datetime.timezone.utc).isoformat()} "
                      f"reason={stop_reason}\n")
            log.close()

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
