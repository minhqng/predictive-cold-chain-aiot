"""ColdGuard W02 serial capture tool (Member A).

Writes an unmodified Serial Monitor capture to a log file with a small
host-side metadata header, so the raw record carries when it was taken,
from which port and by which tool. The firmware lines are copied byte for
byte; the tool never edits, filters or timestamps them individually.

Usage (bench):

    py firmware/tools/cg_capture.py --port COM4 --out evidence/A/W02/serial-w02.log --seconds 900

Notes:

* ``pyserial`` is imported lazily, so the parsing/analysis tools keep
  working on a machine that does not have it.
* ``--from-file`` replays an existing capture through the same pipeline;
  it is used by the automated tests instead of a physical COM port.
* Stop with Ctrl+C: the tool still writes the closing metadata line.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import pathlib
import socket
import sys
import time
from typing import Iterable, Iterator, TextIO

DEFAULT_BAUD = 115200


def iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def capture_header(port: str, baud: int, seconds: float | None) -> str:
    return (
        f"#CG CAPTURE started_at={iso_now()} host={socket.gethostname()} "
        f"port={port} baud={baud} seconds={seconds if seconds is not None else 'until-interrupt'} "
        f"tool=cg_capture.py\n"
    )


def capture_footer(lines: int) -> str:
    return f"#CG CAPTURE ended_at={iso_now()} lines={lines}\n"


def replay(stream: Iterable[str], out: TextIO, port: str, baud: int,
           seconds: float | None = None, delay_s: float = 0.0) -> int:
    """Copy every line of `stream` to `out`, wrapping it in metadata.

    Returns the number of copied lines. This is the whole capture pipeline
    minus the serial port, which is what makes it testable.
    """

    out.write(capture_header(port, baud, seconds))
    count = 0
    for line in stream:
        out.write(line if line.endswith("\n") else line + "\n")
        count += 1
        if delay_s:
            time.sleep(delay_s)
    out.write(capture_footer(count))
    out.flush()
    return count


def open_serial(port: str, baud: int):
    import serial  # imported here so analysis tools never require pyserial

    return serial.Serial(port=port, baudrate=baud, timeout=1)


def read_serial(handle, deadline: float | None) -> Iterator[str]:
    while True:
        if deadline is not None and time.monotonic() > deadline:
            return
        raw = handle.readline()
        if not raw:
            continue
        yield raw.decode("utf-8", errors="replace").rstrip("\r\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a ColdGuard W02 serial log with metadata.")
    parser.add_argument("--port", default="COM4", help="serial port (default: COM4)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--out", required=True, help="output log path")
    parser.add_argument("--seconds", type=float, default=None, help="stop after N seconds (default: until Ctrl+C)")
    parser.add_argument("--from-file", default=None, help="replay an existing capture instead of a serial port")
    args = parser.parse_args(argv)

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        if args.from_file:
            with open(args.from_file, "r", encoding="utf-8", errors="replace") as source:
                lines = replay(source, out, args.port, args.baud, args.seconds)
            print(f"[cg_capture] replayed {lines} lines from {args.from_file} -> {out_path}")
            return 0

        handle = open_serial(args.port, args.baud)
        deadline = None if args.seconds is None else time.monotonic() + args.seconds
        lines = 0
        out.write(capture_header(args.port, args.baud, args.seconds))
        out.flush()
        print(f"[cg_capture] capturing {args.port}@{args.baud} -> {out_path} (Ctrl+C to stop)")
        try:
            for line in read_serial(handle, deadline):
                out.write(line + "\n")
                out.flush()
                lines += 1
        except KeyboardInterrupt:
            print("[cg_capture] interrupted by operator")
        finally:
            out.write(capture_footer(lines))
            out.flush()
            handle.close()
        print(f"[cg_capture] wrote {lines} device lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
