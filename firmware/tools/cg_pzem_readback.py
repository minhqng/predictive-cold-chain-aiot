"""Decode the PZEM current-range readback from a real serial capture (A-W03-04).

A-W03-04 requires the PZEM profile to be *read back* from the device, never
inferred from the shunt label. The firmware logs the whole exchange:

    #CG PZEM_CFG slave=1 baud=9600 framing=8N1 dir=AUTO read_only=1
    #CG PZEM_RANGE uptime_ms=... status=OK value=0x0001 profile=50A crc_ok=1 exc=0 tx=... rx=...

This tool re-derives everything it can from the raw ``tx``/``rx`` hex in the
capture instead of trusting the firmware's own decode:

* CRC16/MODBUS is recomputed host-side and compared with the logged
  ``crc_ok`` flag (a mismatch is a finding, not a warning);
* the range value and profile name are decoded by ``cg_modbus`` from the
  response bytes and compared with the firmware's ``value``/``profile``
  tokens;
* the ``read_only=1`` claim in ``#CG PZEM_CFG`` is required: a capture
  without it cannot certify that the session stayed read-only.

The tool never builds a write request and never connects to the device; it
only re-reads a capture. Exit codes: 0 = readback decoded and consistent,
1 = readback missing/inconsistent/profile mismatch, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cg_modbus  # noqa: E402
import cg_serial  # noqa: E402


def decode_range_line(line: cg_serial.PzemRangeLine, slave: int) -> dict:
    """Host-side decode + cross-check of one firmware PZEM_RANGE line."""

    tx = bytes.fromhex(line.tx) if line.tx else b""
    rx = bytes.fromhex(line.rx) if line.rx else b""

    host_crc_ok = cg_modbus.crc_ok(rx) if len(rx) >= 4 else False
    decoded_raw = None
    decoded_hex = None
    decoded_profile = None
    decode_status = "NO_RESPONSE"
    if len(rx) >= 4:
        parsed = cg_modbus.parse_range(rx, slave)
        decode_status = parsed.status.value
        if parsed.status is cg_modbus.Status.OK:
            decoded_raw = parsed.registers[0]
            decoded_hex = cg_modbus.range_hex(decoded_raw)
            decoded_profile = cg_modbus.profile_name(decoded_raw)

    problems: list[str] = []
    if line.status == "OK" and not len(rx) >= 4:
        problems.append("firmware claims OK but no response bytes were logged")
    if len(rx) >= 4 and host_crc_ok != line.crc_ok:
        problems.append(
            f"CRC disagreement: firmware crc_ok={int(line.crc_ok)}, host crc_ok={int(host_crc_ok)}"
        )
    if decoded_hex is not None and decoded_hex != line.value_hex:
        problems.append(
            f"value disagreement: firmware {line.value_hex}, host {decoded_hex}"
        )
    if decoded_profile is not None and decoded_profile != line.profile:
        problems.append(
            f"profile disagreement: firmware {line.profile}, host {decoded_profile}"
        )
    if line.status == "OK" and line.profile not in (
        "50A",
        "100A",
        "200A",
        "300A",
        "UNKNOWN",
    ):
        problems.append(f"unexpected profile token: {line.profile!r}")

    return {
        "uptime_ms": line.uptime_ms,
        "status": line.status,
        "tx": line.tx,
        "rx": line.rx,
        "firmware_crc_ok": line.crc_ok,
        "host_crc_ok": host_crc_ok,
        "host_decode_status": decode_status,
        "firmware_value_hex": line.value_hex,
        "host_value_hex": decoded_hex,
        "firmware_profile": line.profile,
        "host_profile": decoded_profile,
        "exception_code": line.exception_code,
        "problems": problems,
    }


def render(report: dict) -> str:
    lines: list[str] = []
    cfg = report["config"]
    if cfg is None:
        lines.append("PZEM_CFG            : MISSING (cannot certify read_only=1)")
    else:
        lines.append(
            f"PZEM_CFG            : slave={cfg['slave']} baud={cfg['baud']} "
            f"framing={cfg['framing']} dir={cfg['direction']} read_only={int(cfg['read_only'])}"
        )
    lines.append(f"range lines         : {report['n_range_lines']}")
    for row in report["range_lines"]:
        lines.append("")
        lines.append(f"uptime_ms={row['uptime_ms']} status={row['status']}")
        lines.append(f"  tx                    : {row['tx']}")
        lines.append(f"  rx                    : {row['rx']}")
        lines.append(
            f"  crc firmware/host     : {int(row['firmware_crc_ok'])}/{int(row['host_crc_ok'])}"
        )
        lines.append(
            f"  value firmware/host   : {row['firmware_value_hex'] or 'nan'}"
            f" / {row['host_value_hex'] or 'nan'}"
        )
        lines.append(
            f"  profile firmware/host : {row['firmware_profile'] or 'nan'}"
            f" / {row['host_profile'] or 'nan'}"
        )
        for problem in row["problems"]:
            lines.append(f"  PROBLEM               : {problem}")
    if report["expected_profile"] is not None:
        lines.append("")
        lines.append(f"expected profile    : {report['expected_profile']}")
    lines.append("")
    lines.append("NOTE: readback from the device register, not from the shunt label.")
    lines.append("NOTE: this tool only decodes a capture; it never opens the serial port.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decode the PZEM current-range readback from a real capture (A-W03-04)."
    )
    parser.add_argument("log", help="serial capture that contains #CG PZEM_RANGE lines")
    parser.add_argument(
        "--expect-profile",
        choices=("50A", "100A", "200A", "300A"),
        default=None,
        help="optional expected profile; report fails when the readback differs",
    )
    parser.add_argument(
        "--boot",
        type=int,
        default=None,
        help="boot index (0-based, order of #CG BOOT lines) when the capture spans several reboots",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="also write the report as JSON")
    args = parser.parse_args(argv)

    try:
        parsed = cg_serial.read_log(args.log)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    if not parsed.pzem_range_lines:
        print(
            "no #CG PZEM_RANGE lines in this capture - nothing to decode "
            "(A-W03-04 stays PENDING until a real readback exists)",
            file=sys.stderr,
        )
        return 1

    indices = cg_serial.pzem_boot_indices(parsed)
    if args.boot is not None:
        if args.boot not in indices:
            print(
                f"--boot {args.boot} has no PZEM lines; capture contains boots {indices}",
                file=sys.stderr,
            )
            return 2
        range_lines = [line for line in parsed.pzem_range_lines if line.boot_index == args.boot]
        configs = [cfg for cfg in parsed.pzem_configs if cfg.boot_index == args.boot]
    else:
        if len(indices) > 1:
            print(
                "capture contains PZEM lines from multiple boots "
                f"({indices}): capture one boot per readback or select one with --boot N",
                file=sys.stderr,
            )
            return 1
        range_lines = list(parsed.pzem_range_lines)
        configs = list(parsed.pzem_configs)

    slave = configs[0].slave if configs and configs[0].slave is not None else 1
    rows = [decode_range_line(line, slave) for line in range_lines]

    config_row = None
    if configs:
        cfg = configs[0]
        config_row = {
            "slave": cfg.slave,
            "baud": cfg.baud,
            "framing": cfg.framing,
            "direction": cfg.direction,
            "read_only": cfg.read_only,
        }

    report = {
        "source_log": str(args.log),
        "boot": args.boot if args.boot is not None else indices[0],
        "config": config_row,
        "n_range_lines": len(rows),
        "range_lines": rows,
        "expected_profile": args.expect_profile,
    }

    print(render(report))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"json written: {args.json_out}")

    problems = [problem for row in rows for problem in row["problems"]]
    if config_row is None:
        print("PZEM READBACK: NOT DECODED (no #CG PZEM_CFG - read_only not certified)")
        return 1
    if not config_row["read_only"]:
        print("PZEM READBACK: NOT DECODED (#CG PZEM_CFG does not state read_only=1)")
        return 1
    if problems:
        print(f"PZEM READBACK: INCONSISTENT ({len(problems)} finding(s))")
        return 1
    if any(row["status"] != "OK" for row in rows):
        print("PZEM READBACK: NOT DECODED (cluster response status is not OK)")
        return 1
    if args.expect_profile is not None:
        profiles = {row["firmware_profile"] for row in rows}
        if profiles != {args.expect_profile}:
            print(
                f"PZEM READBACK: PROFILE MISMATCH (read {sorted(profiles)}, "
                f"expected {args.expect_profile})"
            )
            return 1
    print("PZEM READBACK: DECODED (CRC, value and profile consistent host/side firmware-side)")
    print(
        "Reminder: this record proves what the register reported in that session; "
        "it is not a measurement approval and not a write."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
