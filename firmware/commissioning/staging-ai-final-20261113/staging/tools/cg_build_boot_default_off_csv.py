"""Build the W04 default-OFF evidence table from every boot banner on the bench.

    py firmware/tools/cg_build_boot_default_off_csv.py <log> [<log> ...] \
        --csv evidence/A/W04/boot-default-off.csv

One row per device start event found in the raw captures. Nothing is
synthesised: the reset cause comes from the ROM bootloader banner
(`rst:0x.. (NAME)`), the OFF evidence comes from the first device record after
that banner, and `off_evidence_level` distinguishes what the device *reported*
from what a meter *measured* on the pin — those are different claims and the
canonical A-W04-04 ask is about the pin.

Fields that a given image does not emit stay empty rather than being filled in
from another session, so a reader can see exactly which evidence each image can
and cannot supply.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys

BANNER = re.compile(r"rst:0x([0-9a-fA-F]{1,2})\s*\(([^)]*)\)")
CAPTURE_DATE = re.compile(r"# capture start (\d{4}-\d{2}-\d{2})")
HOST_TIME = re.compile(r"^\[\s*[\d.]+\]\s+(\d\d:\d\d:\d\d\.\d\d\d)")
FIELDS = re.compile(r"(\w+)=(\S+)")
TELEM = re.compile(r"#CG TELEM\b")
H8_BOOT = re.compile(r"#CG H8 BOOT\b")
CG_BOOT = re.compile(r"#CG BOOT\b")
SAFE_OFF = re.compile(r"\b(H[67]) (SAFE_OFF|SAFE_OFF_EARLY)\b")
H8_TELEM = re.compile(r"#CG H8 (?:TELEM|STATUS)\b")

# ROM bootloader reset causes worth naming explicitly. Everything else keeps the
# banner's own text so a new cause cannot be silently mislabelled.
RST_NAMES = {
    "1": "POWER_ON",
    "3": "SW_RESET_LEGACY",
    "4": "DEEPSLEEP_WAKEUP",
    "5": "RTC_WATCHDOG_RESET",
    "8": "VBAT_WATCHDOG_RESET",
    "9": "BROWNOUT_RESET",
    "c": "SOFTWARE_RESET",
    "d": "TASK_WDT_RESET",
    "15": "USB_JTAG_CHIP_RESET",
}

COLUMNS = [
    "source_file", "capture_file", "duplicate_captures", "source_line", "host_date", "host_time",
    "rst_code", "reset_cause", "start_kind_class", "boot_banner",
    "image", "firmware_version", "hardware_config_id", "boot_id", "boot_count",
    "first_record_type", "tec_state", "output_stage", "duty_permille",
    "fan_command", "ren", "len", "rpwm_level",
    "current_a", "current_status", "voltage_v", "power_w",
    "fault_code", "fault_reason", "off_evidence_level", "pin_level_measurement",
    "image_basis",
]

SEARCH_WINDOW = 600


def classify(code: str, text: str) -> tuple[str, str]:
    name = RST_NAMES.get(code.lower(), text.strip().upper() or "UNKNOWN")
    if code.lower() == "1":
        klass = "GENUINE_COLD_BOOT"
    elif code.lower() in {"c", "3", "d", "5", "8", "9"}:
        klass = "SOFTWARE_OR_WATCHDOG_RESET"
    elif code.lower() == "15":
        klass = "USB_JTAG_RESET"
    else:
        klass = "UNCLASSIFIED"
    return name, klass


def parse_record(line: str) -> dict[str, str]:
    return dict(FIELDS.findall(line))


def build(paths: list[pathlib.Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            print(f"skip {path}: {error}")
            continue
        date = "UNKNOWN_DATE"
        for head in lines[:5]:
            match = CAPTURE_DATE.search(head)
            if match:
                date = match.group(1)
                break
        for index, line in enumerate(lines):
            banner = BANNER.search(line)
            if not banner:
                continue
            code, text = banner.group(1), banner.group(2)
            cause, klass = classify(code, text)
            row = {column: "" for column in COLUMNS}
            row["source_file"] = path.as_posix()
            row["capture_file"] = path.name
            row["source_line"] = str(index + 1)
            row["host_date"] = date
            stamp = HOST_TIME.match(line.strip())
            row["host_time"] = stamp.group(1) if stamp else ""
            row["rst_code"] = f"0x{code.lower()}"
            row["reset_cause"] = cause
            row["start_kind_class"] = klass
            row["boot_banner"] = text.strip()
            row["off_evidence_level"] = "NO_DEVICE_RECORD_AFTER_BANNER"
            row["pin_level_measurement"] = "NOT_FOUND_IN_THIS_CAPTURE"

            image_hint = "unknown"
            if "/h6" in path.as_posix():
                image_hint = "h6-bench(path)"
            elif "/h7" in path.as_posix():
                image_hint = "h7-bench(path)"
            elif "/h8" in path.as_posix():
                image_hint = "h8-bench(path)"
            elif "/g1/" in path.as_posix() or "_w04-g1-evidence" in path.as_posix():
                image_hint = "production-cg-w04(path)"
            elif "/W02/" in path.as_posix():
                image_hint = "cg-w02(path)"
            elif "/W03/" in path.as_posix():
                image_hint = "cg-w03(path)"
            row["image"] = image_hint
            row["image_basis"] = "path_hint_only"

            for offset in range(index + 1, min(index + 1 + SEARCH_WINDOW, len(lines))):
                record = lines[offset]
                if BANNER.search(record):
                    break
                fields = parse_record(record)
                if TELEM.search(record) and not H8_TELEM.search(record):
                    row.update({
                        "first_record_type": "CG_TELEM",
                        "firmware_version": fields.get("firmware_version", ""),
                        "hardware_config_id": fields.get("hardware_config_id", ""),
                        "boot_id": fields.get("boot_id", ""),
                        "boot_count": fields.get("boot_count", ""),
                        "tec_state": fields.get("tec_state", ""),
                        "output_stage": fields.get("output_stage", ""),
                        "duty_permille": fields.get("pwm_duty", ""),
                        "fan_command": fields.get("fan_command", ""),
                        "current_a": fields.get("current_a", ""),
                        "current_status": fields.get("current_status", ""),
                        "voltage_v": fields.get("voltage_v", ""),
                        "power_w": fields.get("power_w", ""),
                        "fault_code": fields.get("fault_code", ""),
                        "fault_reason": fields.get("fault_reason", ""),
                        "off_evidence_level": "DEVICE_REPORTED",
                    })
                    if fields.get("firmware_version"):
                        # The device names its own build: that outranks any path hint.
                        row["image"] = fields["firmware_version"]
                        row["image_basis"] = "telemetry firmware_version line"
                    break
                if H8_BOOT.search(record) or CG_BOOT.search(record):
                    row["boot_id"] = row["boot_id"] or fields.get("boot_id", "")
                    row["boot_count"] = row["boot_count"] or fields.get("boot_count", "")
                    if fields.get("firmware"):
                        row["image"] = fields["firmware"]
                        row["image_basis"] = "boot line firmware field"
                    if fields.get("test_mode"):
                        row["fault_reason"] = row["fault_reason"] or f"test_mode={fields['test_mode']}"
                    continue
                safe = SAFE_OFF.search(record)
                if safe:
                    row.update({
                        "first_record_type": f"{safe.group(1)}_{safe.group(2)}",
                        "duty_permille": fields.get("duty_permille", fields.get("duty", "")),
                        "ren": fields.get("ren", ""),
                        "len": fields.get("len", ""),
                        "rpwm_level": fields.get("rpwm_level", ""),
                        "tec_state": fields.get("tec_output", ""),
                        "off_evidence_level": "DEVICE_REPORTED",
                    })
                    row["image"] = f"{safe.group(1).lower()}-bench"
                    row["image_basis"] = f"{safe.group(1)} SAFE_OFF line"
                    break
                if H8_TELEM.search(record):
                    row.update({
                        "first_record_type": "H8_TELEM",
                        "duty_permille": fields.get("pwm_applied_permille", fields.get("pwm_applied", "")),
                        "ren": fields.get("ren_command", ""),
                        "len": fields.get("len_command", ""),
                        "tec_state": fields.get("state", ""),
                        "current_a": fields.get("current_a", ""),
                        "current_status": fields.get("current_a_status", ""),
                        "voltage_v": fields.get("voltage_v", ""),
                        "power_w": fields.get("power_w", ""),
                        "off_evidence_level": "DEVICE_REPORTED",
                    })
                    if fields.get("physical_output"):
                        row["fault_reason"] = f"physical_output={fields['physical_output']}"
                    break
            rows.append(row)
    return rows


def deduplicate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The same capture exists in the delivery worktree, the bench worktree and the
    scratch folder, so a raw per-banner count double-books physical boot events."""
    groups: dict[tuple, dict[str, str]] = {}
    order: list[tuple] = []
    for row in rows:
        key = (row["image"], row["boot_id"], row["boot_count"], row["capture_file"],
               row["reset_cause"], row["first_record_type"], row["tec_state"],
               row["duty_permille"], row["source_line"])
        if key not in groups:
            groups[key] = dict(row)
            groups[key]["duplicate_captures"] = ""
            order.append(key)
        else:
            kept = groups[key]
            seen = [s.strip() for s in (kept["duplicate_captures"] or kept["source_file"]).split(";") if s.strip()]
            if row["source_file"] not in seen:
                seen.append(row["source_file"])
            kept["duplicate_captures"] = "; ".join(seen)
    return [groups[key] for key in order]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--csv", type=pathlib.Path, required=True)
    args = parser.parse_args()

    raw_rows = build(args.logs)
    rows = deduplicate(raw_rows)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"banner rows parsed   : {len(raw_rows)}")
    print(f"unique start events  : {len(rows)} -> {args.csv}  (identical captures in more than one copy merged, listed in duplicate_captures)")
    for klass in ("GENUINE_COLD_BOOT", "USB_JTAG_RESET", "SOFTWARE_OR_WATCHDOG_RESET", "UNCLASSIFIED"):
        subset = [r for r in rows if r["start_kind_class"] == klass]
        if not subset:
            print(f"  {klass:28}: 0")
            continue
        by_image: dict[str, int] = {}
        for row in subset:
            by_image[row["image"]] = by_image.get(row["image"], 0) + 1
        detail = ", ".join(f"{name}={count}" for name, count in sorted(by_image.items()))
        print(f"  {klass:28}: {len(subset)}  ({detail})")
    reported = sum(1 for r in rows if r["off_evidence_level"] == "DEVICE_REPORTED")
    with_current = sum(1 for r in rows if r["current_status"] in {"OK", "VALID"})
    print(f"  events with a device OFF record: {reported}")
    print(f"  events where PZEM current was actually live (status OK): {with_current}")
    print("  pin-level (DMM/scope) OFF measurements found: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
