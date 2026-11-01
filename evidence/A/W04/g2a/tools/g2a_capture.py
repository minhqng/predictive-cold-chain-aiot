"""G2-A timestamped serial capture (scratch evidence tool).

Every device line is written to the output file prefixed with the host
monotonic offset, so an operator-guided probe warming round can be aligned
with the telemetry it produced. The device line itself is unchanged.

The port is opened with pyserial defaults (DTR/RTS asserted) and never
pulsed, so this tool does not deliberately reset the board.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", type=float, default=480.0)
    args = parser.parse_args(argv)

    import serial

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    started_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"#G2A CAPTURE host_started_at={started_at.isoformat()} port={args.port} "
                  f"baud={args.baud} seconds={args.seconds}\n")
        out.flush()
        handle = serial.Serial(port=args.port, baudrate=args.baud, timeout=0.2)
        try:
            deadline = start + args.seconds
            while time.monotonic() < deadline:
                try:
                    raw = handle.readline()
                except Exception as exc:  # port re-enumeration
                    out.write(f"[+{time.monotonic() - start:8.3f}s] [host io-error {type(exc).__name__}]\n")
                    out.flush()
                    time.sleep(0.05)
                    continue
                if not raw:
                    continue
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                out.write(f"[+{time.monotonic() - start:8.3f}s] {text}\n")
                out.flush()
        finally:
            handle.close()
    print(f"[g2a_capture] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
