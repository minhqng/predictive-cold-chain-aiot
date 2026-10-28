#!/usr/bin/env python3
"""Read-only verifier for the W03 Arduino bench archive (2026-10-20).

This script never opens a serial port, never writes a file, and never touches
hardware. It only re-hashes the archived blobs and re-checks the facts that can
be checked from the archive itself.

It verifies:
  * 7/7 SHA-256 values from SHA256SUMS.txt;
  * the 601-row bench CSV (594 CRC_VALID, 7 INVALID, 600.000 s span);
  * the collector's final line: gate=COLLECTED_WITH_ERRORS;
  * the 7 #RX_RAW frames have no CRC-valid 5/7/17/21-byte window;
  * the shunt log says raw=0x0001 but has no raw FC03 tx/rx hex;
  * the SET50 log/sketch contain FC06 and are archive-only.

It does NOT prove ESP-IDF firmware behavior, a real 50 A load, TEC OFF, or an
IBT-2 cold boot. The archive stays supplementary bench evidence, not ESP-IDF
W03 acceptance.
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXPECTED = {
    "raw/pzem-off.csv": "2DFDCB11490090EFFF9D64EB7B967BBA745C6120BAA09F61E4529B491EE1C87B",
    "raw/pzem-off-serial.log": "85B3DA0F79B8DBAA22795F96B1F28DF4C1A3840983E67163FECDD0B7D40B9D32",
    "raw/w3testlog.txt": "4CB246A75EBFB2639D086FC8573F4A25BDA4393D9673DEC37152A598629F3D10",
    "raw/w3rstestlogshunt.txt": "3AEDC0596DFEEC366D92D31A0B0453A3856251FD4ECBAB0C55E7AAD997E424AD",
    "firmware/ColdGuard_W03_TTL485_V4_8N1_TEST.ino": "21FF99330EB54652F5D402A7EBEF65A72B04B9495D78A898B4128AA406C9EF40",
    "firmware/ColdGuard_W03_TTL485_SET50A_ONCE_8N1.ino": "D4FEBBCECDCFAF9EBB47B13B06DB4724E81F4C528F193C362510E01A57EB1284",
    "tools/ColdGuard_W03_PZEM_OFF10_COM4_8N1.py": "D40AEECF99BB40D4346908900983EFAAD2426FD4A7C1D768EC9A9A21CBEEA046",
}

EXPECTED_GATE = (
    "gate=COLLECTED_WITH_ERRORS samples=601/601 valid=594 invalid=7 "
    "sample_span_s=600.000"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def crc_ok(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    return crc16(frame[:-2]) == (frame[-2] | (frame[-1] << 8))


def check_hashes(failures: list[str]) -> int:
    matched = 0
    for relative, expected in EXPECTED.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing file: {relative}")
            continue
        actual = sha256(path)
        if actual != expected:
            failures.append(f"sha256 mismatch: {relative} actual={actual}")
            continue
        matched += 1
    return matched


def check_csv(failures: list[str]) -> tuple[int, int, int, str]:
    path = ROOT / "raw/pzem-off.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 601:
        failures.append(f"csv rows expected 601, got {len(rows)}")
    samples = [int(row["sample"]) for row in rows]
    if samples != list(range(1, 602)):
        failures.append("csv sample sequence is not 1..601")
    valid = sum(1 for row in rows if row["quality"] == "CRC_VALID")
    invalid = sum(1 for row in rows if row["quality"] == "INVALID")
    other = len(rows) - valid - invalid
    if (valid, invalid, other) != (594, 7, 0):
        failures.append(
            f"csv quality expected 594/7/0, got {valid}/{invalid}/{other}"
        )
    last_elapsed = rows[-1]["elapsed_s"] if rows else ""
    if last_elapsed != "600.000":
        failures.append(f"csv last elapsed expected 600.000, got {last_elapsed!r}")
    return len(rows), valid, invalid, last_elapsed


def check_serial(failures: list[str]) -> tuple[str, int, int]:
    path = ROOT / "raw/pzem-off-serial.log"
    text = path.read_text(encoding="utf-8", errors="replace")
    if EXPECTED_GATE not in text:
        failures.append("serial log does not contain the expected COLLECTED_WITH_ERRORS gate")
    raws = re.findall(r"#RX_RAW n=1 ((?:[0-9A-F]{2} ?)+)", text)
    if len(raws) != 7:
        failures.append(f"serial log #RX_RAW count expected 7, got {len(raws)}")
    valid_counts = {5: 0, 7: 0, 17: 0, 21: 0}
    for raw_hex in raws:
        raw = bytes.fromhex(raw_hex.strip())
        for width in valid_counts:
            for offset in range(0, len(raw) - width + 1):
                if crc_ok(raw[offset : offset + width]):
                    valid_counts[width] += 1
    for width, count in valid_counts.items():
        if count != 0:
            failures.append(f"unexpected CRC-valid {width}-byte window count={count}")
    gate_present = "COLLECTED_WITH_ERRORS" in text
    return ("COLLECTED_WITH_ERRORS" if gate_present else "MISSING"), len(raws), sum(valid_counts.values())


def check_shunt_log(failures: list[str]) -> str:
    path = ROOT / "raw/w3rstestlogshunt.txt"
    text = path.read_text(encoding="utf-8", errors="replace")
    if "#PROFILE_RESULT shunt=50A raw=0x0001" not in text:
        failures.append("shunt log lacks #PROFILE_RESULT shunt=50A raw=0x0001")
    if re.search(r"(?:^|\s)(?:tx|rx)\s*=", text, re.MULTILINE) or "#CG PZEM_RANGE" in text:
        failures.append("shunt log unexpectedly contains a raw/ESP-IDF readback block")
    if re.search(r"\b[0-9A-F]{2}(?: [0-9A-F]{2}){4,}\b", text):
        failures.append("shunt log unexpectedly contains a raw hex frame")
    return "0x0001"


def check_set50(failures: list[str]) -> None:
    log_path = ROOT / "raw/w3testlog.txt"
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if "#WRITE50_FC06_TX_ONCE 01 06 00 03 00 01 B8 0A" not in log_text:
        failures.append("SET50 log lacks the one-shot FC06 TX line")
    if "01 06 00 03 00 01 B8 0A 01 06 00 03 00 01 B8 0A" not in log_text:
        failures.append("SET50 log lacks the untrusted echo/ack pair")
    if "#SET50_VERIFIED PASS readback=3/3 shunt_reg=0x0001" not in log_text:
        failures.append("SET50 log lacks the text-only 0x0001 readback claim")
    sketch = (ROOT / "firmware/ColdGuard_W03_TTL485_SET50A_ONCE_8N1.ino").read_text(
        encoding="utf-8", errors="replace"
    )
    if "FC06" not in sketch or "makeRequest(FC06" not in sketch:
        failures.append("SET50 sketch does not contain the expected FC06 path")


def main() -> int:
    failures: list[str] = []
    matched = check_hashes(failures)
    rows, valid, invalid, last_elapsed = check_csv(failures)
    gate, raw_count, valid_windows = check_serial(failures)
    shunt_raw = check_shunt_log(failures)
    check_set50(failures)

    print("W03 Arduino bench archive verifier (read-only)")
    print(f"HASH_OK={matched}/7")
    print(f"CSV_ROWS={rows} CRC_VALID={valid} INVALID={invalid} LAST_ELAPSED={last_elapsed}")
    print(f"COLLECTOR_GATE={gate}")
    print(f"RX_RAW_FRAMES={raw_count} CRC_VALID_WINDOWS_5_7_17_21={valid_windows}")
    print(f"SHUNT_LOG_RAW={shunt_raw} RAW_FC03_SUCCESS_FRAME=ABSENT")
    print("SET50_FC06=PRESENT ARCHIVE_ONLY=1")
    print("W03_STATUS=NOT_PASS")
    print("ESP_IDF_READBACK=PENDING_READBACK")
    print("CANONICAL_PZEM_OFF_CSV=MISSING")

    if failures:
        print("BENCH_ARCHIVE_FAILED")
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("BENCH_ARCHIVE_VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
