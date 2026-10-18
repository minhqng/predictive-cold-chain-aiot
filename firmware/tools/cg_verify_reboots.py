"""Verify ColdGuard W02 reboot identity from a serial capture (A-W02-03 / SEN-H1-02).

Reads a raw capture that contains at least ``--min-boots`` boot blocks and
asserts that every role (T1, T2, T3) keeps exactly one ROM across all of
them, that no ROM is assigned to two roles, and that every role was
actually present in every boot. The boot metadata must also look like N
distinct reboots: pairwise distinct ``boot_id`` values and a strictly
increasing NVS ``boot_count`` (duplicated blocks or a reset counter are
rejected, never counted as five reboots).

Exit codes: 0 = identity stable across enough boots, 1 = not proven,
2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cg_serial  # noqa: E402  (local module next to this script)


def render(report: dict) -> str:
    lines = []
    lines.append(f"verdict              : {report['verdict']}")
    lines.append(f"boots observed       : {report['boots_observed']} (min required {report['min_boots_required']})")
    lines.append(f"boot ids             : {', '.join(bid or 'n/a' for bid in report['boot_ids'])}")
    lines.append(f"boot counts (NVS)    : {report['boot_counts']}")
    metadata_issues = report.get("boot_metadata_issues") or []
    if metadata_issues:
        for item in metadata_issues:
            extras = ", ".join(
                f"{key}={value}" for key, value in item.items() if key not in ("code", "boot")
            )
            suffix = f" ({extras})" if extras else ""
            lines.append(f"BOOT METADATA {item['code']} boot{item['boot']}{suffix}")
    else:
        lines.append("boot metadata        : OK (boot_id distinct, boot_count increasing)")
    lines.append("")
    roles = report["roles"]
    header = "role  " + "  ".join(f"boot{b}" for b in range(report["boots_observed"]))
    lines.append(header)
    for role in roles:
        row = [role.ljust(4)]
        for rom in report["role_roms"][role]:
            row.append(rom or "MISSING ")
        lines.append("  ".join(row))
    if report["missing_boot_indices"]:
        lines.append("")
        lines.append(f"boots with a missing role: {report['missing_boot_indices']}")
    if report["mismatches"]:
        lines.append("")
        for item in report["mismatches"]:
            lines.append(
                f"MISMATCH {item['role']}: boot{item['workspace_boot']}={item['workspace_rom']} "
                f"vs boot{item['boot']}={item['rom']}"
            )
    if report["duplicated_roms"]:
        lines.append("")
        for item in report["duplicated_roms"]:
            lines.append(f"DUPLICATE ROM in boot{item['boot']}: {item['rom']} -> {item['roles']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify ROM->role identity across reboots (A-W02-03).")
    parser.add_argument("log", help="serial capture produced by cg_capture.py")
    parser.add_argument("--min-boots", type=int, default=5, help="minimum reboot cycles (default: 5)")
    parser.add_argument("--json", dest="json_out", default=None, help="also write the report as JSON")
    args = parser.parse_args(argv)

    try:
        parsed = cg_serial.read_log(args.log)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2

    report = cg_serial.verify_reboot_identity(parsed, min_boots=args.min_boots)
    print(render(report))
    print()

    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"json report written: {args.json_out}")

    if report["verdict"] == "IDENTITY_STABLE":
        print(
            f"REBOOT IDENTITY: PASS ({report['boots_observed']} boots, roles stable, "
            "boot metadata consistent)"
        )
        return 0
    print(f"REBOOT IDENTITY: NOT PROVEN ({report['verdict']})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
