"""ColdGuard W02 host-side USB reboot automation (A-W02-03 evidence run).

Physical problem this solves: the bench ESP32-S3 is connected over native
USB-Serial/JTAG (VID 0x303A PID 0x1001), so there is no external USB-UART
bridge wired to the EN pin. Two host trigger paths exist for the native
USB-Serial-JTAG peripheral, and they behave very differently on this
bench board (VID 0x303A PID 0x1001, Windows usbser.sys):

* RTS-only hard-reset pulses (the esptool ``--after hard-reset`` style)
  did NOT reset a running application during bench use - the chip kept
  streaming for the whole hold window, no reset banner, no boot block.
* The reset path that IS proven on this exact board: open the port, then
  drop both DTR and RTS to low. The peripheral translates that
  asserted->deasserted transition into ``rst:0x15 (USB_UART_CHIP_RESET)``
  and the chip boots from flash (``boot:0x8 SPI_FAST_FLASH_BOOT``). It
  happened twice on the bench (once with the previous Arduino sketch,
  once with the first W02 firmware image captured in segment 0 of the
  first run), and the port handle survives it.

This tool therefore performs each reboot as one open->drop cycle: it
closes the port, opens it again, drops DTR/RTS, and records the boot
completely, starting a few tens of milliseconds before the ROM banner.

What it does, in order:

1. opens the port and drops DTR/RTS - this itself triggers reset #0,
   recorded as the context segment (never counted as one of --boots);
2. for ``--boots`` cycles: writes a host-side marker line (plain text, no
   ``#CG`` prefix - the log grammar parser counts it as non-firmware
   noise and never interprets it), closes, re-opens, drops DTR/RTS again
   (reset #N), records device output for ``--hold`` seconds;
3. if ``--runtime`` is given, records one additional segment with no
   reset on the same handle, for runtime cadence verification
   (``#CG SAMPLE`` with ``uptime_ms``).

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
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cg_capture import DEFAULT_BAUD  # noqa: E402  (local module)

ISO_NOW = lambda: datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mark(out, text: str) -> None:
    out.write(f"[host {ISO_NOW()}] {text}\n")
    out.flush()


def _open_and_drop(port: str, baud: int) -> Any:
    """Open the port and drop DTR/RTS immediately. On this board's native
    USB-Serial-JTAG the asserted->deasserted transition from the open
    defaults is what triggers ``rst:0x15 (USB_UART_CHIP_RESET)``; the
    handle survives it (proven twice on the bench)."""
    import serial

    handle = serial.Serial(port=port, baudrate=baud, timeout=0.5)
    handle.dtr = False
    handle.rts = False
    return handle


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
    parser.add_argument("--boots", type=int, default=5, help="number of reboots to record (0 = capture only)")
    parser.add_argument("--hold", type=float, default=10.0, help="seconds to record after each reset (default: 10)")
    parser.add_argument("--runtime", type=float, default=0.0, help="extra seconds to record after the boot resets")
    parser.add_argument("--gap", type=float, default=0.3, help="seconds between closing and reopening the port (default: 0.3)")
    args = parser.parse_args(argv)

    import serial  # lazy so analysis-only machines do not need pyserial

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        _mark(out, f"host tool=cg_auto_reboot.py port={args.port} baud={args.baud} "
                   f"boots={args.boots} hold_s={args.hold} runtime_s={args.runtime} "
                   f"reset_method=serial_open_dtr_rts_drop")
        import serial  # noqa: F401  (ensures the port argument exists before opening)
        try:
            handle = _open_and_drop(args.port, args.baud)
        except Exception as exc:
            _mark(out, f"port open FAILED {type(exc).__name__}: {exc}")
            print(f"[cg_auto_reboot] port open failed: {exc}", file=sys.stderr)
            return 1
        _mark(out, "port opened, dtr/rts dropped -> reset #0 expected (context segment)")

        try:
            # Segment 0: the boot triggered by the open+drop itself (context only).
            _mark(out, "segment=reset_0_context record_s=2.0 note=never-counted-as-a-reboot")
            _read_for(handle, out, 2.0)

            for index in range(1, args.boots + 1):
                handle.close()
                time.sleep(args.gap)
                _mark(out, f"reset request {index}/{args.boots} via serial_open_dtr_rts_drop")
                handle = _open_and_drop(args.port, args.baud)
                _mark(out, f"segment=boot_{index} record_s={args.hold}")
                devices, io_errs = _read_for(handle, out, args.hold)
                _mark(out, f"segment=boot_{index} device_lines={devices} io_errors={io_errs}")

            if args.runtime > 0:
                _mark(out, f"segment=runtime record_s={args.runtime} note=no-reset-steady-cadence-capture")
                devices, io_errs = _read_for(handle, out, args.runtime)
                _mark(out, f"segment=runtime device_lines={devices} io_errors={io_errs}")
        finally:
            handle.close()
            _mark(out, "port closed")

    print(f"[cg_auto_reboot] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
