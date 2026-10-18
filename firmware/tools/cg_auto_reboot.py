"""ColdGuard W02 host-side USB reboot automation (A-W02-03 evidence run).

Physical problem this solves: the bench ESP32-S3 is connected over native
USB-Serial/JTAG (VID 0x303A PID 0x1001), so there is no external USB-UART
bridge wired to the EN pin. The proven way to reboot the chip from the
host is the same sequence esptool uses for ``--after hard-reset`` (package
``esp_pylib.serial_reset.hard_reset``): pulse RTS low (EN asserted) for
``0.2 s`` and release again, all inside an already-open port handle while
a reader loop keeps copying every byte the device prints. Only the RTS
line is toggled: on Windows ``usbser.sys`` flushes
``SET_CONTROL_LINE_STATE`` only when RTS changes, which is why naive
DTR/RTS pulse trains silently do nothing (observed on this exact bench
board: five pulse attempts, zero reset banners).

What it does, in order:

1. opens the port, puts DTR/RTS into the (high, high) idle state esptool
   leaves after its own reset sequences;
2. records a short context segment of whatever the device is streaming;
3. for ``--boots`` cycles: writes a host-side marker line (plain text, no
   ``#CG`` prefix - the log grammar parser counts it as non-firmware
   noise and never interprets it), performs the RTS hard-reset pulse,
   waits for the chip to re-enumerate, then records device output for
   ``--hold`` seconds;
4. if ``--runtime`` is given, records one additional segment with no reset
   for runtime cadence verification (``#CG SAMPLE`` with ``uptime_ms``).

Everything the device prints is copied to the output file byte for byte;
host marks are clearly labelled. No output is ever dropped, filtered or
invented. To count as reboots, the resets must produce real boot blocks
(``#CG BOOT`` blocks; ``#CG ROM`` lines should follow once the sensor
task reaches its enumeration); if a reset fails, the run stays
inconclusive - it never fakes a boot. Judge the result with
``py firmware/tools/cg_verify_reboots.py --log <file>``.

Usage:

    py firmware/tools/cg_auto_reboot.py --port COM4 --out evidence/A/W02/preview.log --boots 5 --hold 10
    py firmware/tools/cg_auto_reboot.py --port COM4 --out runtime.log --boots 0 --runtime 240
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cg_capture import DEFAULT_BAUD  # noqa: E402  (local module)

ISO_NOW = lambda: datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mark(out, text: str) -> None:
    out.write(f"[host {ISO_NOW()}] {text}\n")
    out.flush()


def _set_idle(handle) -> None:
    """Put DTR/RTS into the (high, high) idle state esptool leaves after
    its own reset sequences (its hard_reset toggles RTS low->high from
    there, and only RTS changes actually reach the chip on Windows)."""
    handle.dtr = True
    handle.rts = True


def _hard_reset(handle, hold_ms: int, post_ms: int) -> None:
    """One real hard reset via RTS only, as esptool does after flashing
    (esp_pylib.serial_reset.hard_reset with USB held-times: 0.2 s / 0.2 s).
    The USB device disappears while reset is asserted and re-enumerates
    after release; the reader loop keeps draining errors meanwhile."""
    handle.rts = False
    time.sleep(hold_ms / 1000.0)
    handle.rts = True
    time.sleep(post_ms / 1000.0)


def _read_for(handle, out, seconds: float) -> tuple[int, int]:
    """Copy device output to `out` for `seconds` seconds; returns
    (device-line count, transient IO-error count during re-enumeration)."""
    deadline = time.monotonic() + seconds
    device_lines = 0
    io_errors = 0
    while time.monotonic() < deadline:
        try:
            raw = handle.readline()
        except Exception:
            io_errors += 1
            time.sleep(0.05)
            continue
        if not raw:
            continue
        out.write(raw.decode("utf-8", errors="replace").rstrip("\r\n") + "\n")
        out.flush()
        device_lines += 1
    return device_lines, io_errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Host-driven USB-Serial-JTAG reboot automation with raw serial capture (A-W02-03)."
    )
    parser.add_argument("--port", default="COM4", help="serial port (default: COM4)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--out", required=True, help="raw capture output path")
    parser.add_argument("--boots", type=int, default=5, help="number of hard resets (0 = capture only)")
    parser.add_argument("--hold", type=float, default=10.0, help="seconds to record after each reset (default: 10)")
    parser.add_argument("--runtime", type=float, default=0.0, help="extra seconds to record after the boot resets")
    parser.add_argument("--settle", type=float, default=0.5, help="seconds to wait after opening the port before the first reset")
    parser.add_argument("--reassert-ms", type=int, default=100,
                        help="ms between idle-state writes and the reset pulse (default: 100)")
    args = parser.parse_args(argv)

    import serial  # lazy so analysis-only machines do not need pyserial

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        _mark(out, f"host tool=cg_auto_reboot.py port={args.port} baud={args.baud} "
                   f"boots={args.boots} hold_s={args.hold} runtime_s={args.runtime} "
                   f"reset_method=esptool_hard_reset_rts_only hold_ms=200")
        handle = serial.Serial(port=args.port, baudrate=args.baud, timeout=0.5)
        _set_idle(handle)
        _mark(out, "port opened dtr=1 rts=1 (esptool idle state)")
        time.sleep(args.settle)

        try:
            # Segment 0: whatever the device is currently streaming (context only).
            _mark(out, "segment=pre_reset record_s=2.0 note=current-device-context-not-a-reboot")
            _read_for(handle, out, 2.0)

            for index in range(1, args.boots + 1):
                _mark(out, f"reset request {index}/{args.boots} via esptool hard_reset (RTS low 0.2 s, release, USB re-enumerates)")
                _set_idle(handle)
                time.sleep(args.reassert_ms / 1000.0)
                _hard_reset(handle, 200, 200)
                _mark(out, f"segment=boot_{index} record_s={args.hold}")
                devices, io_errs = _read_for(handle, out, args.hold)
                _mark(out, f"segment=boot_{index} device_lines={devices} io_errors={io_errs}")

            if args.runtime > 0:
                _mark(out, f"segment=runtime record_s={args.runtime} note=no-reset-steady-cadence-capture")
                devices, io_errs = _read_for(handle, out, args.runtime)
                _mark(out, f"segment=runtime device_lines={devices} io_errors={io_errs}")
        finally:
            handle.dtr = False
            handle.rts = False
            handle.close()
            _mark(out, "port closed")

    print(f"[cg_auto_reboot] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
