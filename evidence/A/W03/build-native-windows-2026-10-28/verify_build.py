#!/usr/bin/env python3
"""Verify the 2026-10-28 native ESP-IDF v6.1 build bundle (Member A, W03).

Checks:
1. SHA-256 of every file listed in SHA256SUMS.txt.
2. raw/20-idf-py-build.log really contains "Project build complete.", the
   1090/1090 Ninja step marker, the expected app image size/free space line,
   and no compiler warning/error lines.
3. raw/10-set-target.log really targets esp32s3.
4. Boundaries: this is a LOCAL compile, not GitHub Actions CI, and not
   hardware acceptance. IBT-2/TEC stay OFF; nothing here was flashed.
"""

from pathlib import Path
import hashlib
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent

EXPECTED_BIN_SIZE = 0x38920
EXPECTED_FREE_BYTES = 0xC76E0
EXPECTED_FREE_PCT = 78


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def read_log_text(p: Path) -> str:
    raw = p.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(1)


def main() -> None:
    sums_file = ROOT / "SHA256SUMS.txt"
    if not sums_file.is_file():
        fail(f"missing {sums_file}")

    for line in sums_file.read_text(encoding="utf-8").strip().splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_hash, rel_path = parts[0], parts[1].strip()
        target = ROOT / rel_path
        if not target.is_file():
            fail(f"missing target file: {rel_path}")
        actual = sha256_file(target)
        if actual.lower() != expected_hash.lower():
            fail(f"hash mismatch for {rel_path}: expected {expected_hash}, got {actual}")
        print(f"[PASS] sha256 {rel_path} = {actual}")

    set_target_log = read_log_text(ROOT / "raw" / "10-set-target.log")
    if "Set Target to: esp32s3" not in set_target_log:
        fail("'Set Target to: esp32s3' missing in raw/10-set-target.log")
    print("[PASS] set-target log targets esp32s3")

    build_log = read_log_text(ROOT / "raw" / "20-idf-py-build.log")

    if "Project build complete." not in build_log:
        fail("'Project build complete.' missing in raw/20-idf-py-build.log")
    if "[1090/1090]" not in build_log:
        fail("Ninja step marker [1090/1090] missing in build log")

    match = re.search(
        r"coldguard_firmware\.bin binary size (0x[0-9a-fA-F]+) bytes\.\s*"
        r"Smallest app partition is (0x[0-9a-fA-F]+) bytes\.\s*"
        r"(0x[0-9a-fA-F]+) bytes \((\d+)%\) free\.",
        build_log,
    )
    if not match:
        fail("cannot find app partition size line in build log")

    bin_size = int(match.group(1), 16)
    part_size = int(match.group(2), 16)
    free_bytes = int(match.group(3), 16)
    free_pct = int(match.group(4))

    if bin_size != EXPECTED_BIN_SIZE:
        fail(f"unexpected binary size {bin_size} (expected {EXPECTED_BIN_SIZE})")
    if free_bytes != EXPECTED_FREE_BYTES:
        fail(f"unexpected free bytes {free_bytes} (expected {EXPECTED_FREE_BYTES})")
    if free_pct != EXPECTED_FREE_PCT:
        fail(f"unexpected free percentage {free_pct} (expected {EXPECTED_FREE_PCT})")
    if bin_size + free_bytes != part_size:
        fail("binary size + free space does not add up to the app partition size")

    warnings = len(re.findall(r"warning:", build_log, re.IGNORECASE))
    errors = len(re.findall(r"error:", build_log, re.IGNORECASE))
    if warnings or errors:
        fail(f"build log contains {warnings} warning(s) and {errors} error(s)")
    print("[PASS] build log has 0 warning and 0 error lines")

    print(f"[INFO] coldguard_firmware.bin = {bin_size} bytes ({match.group(1)}), "
          f"{free_bytes} bytes free ({match.group(3)}, {free_pct}%)")
    print("[PASS] local ESP-IDF v6.1 native Windows build artifacts verified.")
    print("NOTE: LOCAL COMPILE PROOF of the 2026-10-28 working tree only. "
          "GitHub Actions CI remains INFRASTRUCTURE-LIMITED (GitHub billing).")
    print("NOTE: NOT hardware acceptance. IBT-2/TEC stay OFF; nothing was flashed.")


if __name__ == "__main__":
    main()
