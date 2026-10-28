#!/usr/bin/env python3
"""Read-only verifier for the W03 TEST 132B OFF-envelope capture (2026-10-27).

Script này KHÔNG mở cổng serial, KHÔNG điều khiển phần cứng và KHÔNG phải nghiệm thu
W03. Nó chỉ đọc các file đã archive và kiểm tra những gì có thể kiểm tra bằng máy:

1. Byte integrity: SHA-256 của raw log và CSV trích xuất khớp hằng số pin.
2. CSV: đúng header, đủ 600 hàng, 8 cột/hàng, thứ tự thời gian tăng dần.
3. Giá trị: 600/600 `valid=1` + `status=OK`; V min/max/mean; I/P/energy bằng 0
   theo độ phân giải hiển thị; `rx_len=29` trên mọi hàng.
4. Summary: các dòng DURATION_MS / VALID_SAMPLES / FAILED_SAMPLES / SUCCESS_RATE /
   V_MIN-MAX / V_MEAN khớp dữ liệu CSV (sai số làm tròn cho phép).
5. Cửa sổ mẫu: in rõ span giữa mẫu đầu và mẫu cuối (598.99 s) khác với
   DURATION_MS của test (600 s); không tự đổi một trong hai con số.
6. Gate của chính log: `RESULT: REVIEW REQUIRED` phải còn nguyên. Script FAIL nếu
   ai đó sửa log thành `RESULT: PASS` mà không có bằng chứng mới.
7. TEST 131 profile frame `01 03 02 00 01 79 84`: CRC16/MODBUS tính lại host-side.

Chạy: ``py evidence/A/W03/hardware-2026-10-27/verify_test132b.py``
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

try:  # Windows consoles default to cp1252 and cannot print Vietnamese text.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = Path(__file__).resolve().parent
RAW_LOG = HERE / "raw" / "test-132b-off-envelope.log"
CSV_PATH = HERE / "raw" / "test-132b-off-envelope.csv"

PINNED_SHA256 = {
    "raw/test-132b-off-envelope.log":
        "0af8a083cc1fe788ae13c7b1652effc1d3377862aeef66bf3f0521f2995c557e",
    "raw/test-132b-off-envelope.csv":
        "7eac5f80c2d95ebf7b4147251b2c38d65f5da103951b767413972f29a66f81d8",
}

EXPECTED_HEADER = "elapsed_ms,valid,voltage_v,current_a,power_w,energy_wh,rx_len,status"
EXPECTED_ROWS = 600
EXPECTED_FIRST_ELAPSED = 10
EXPECTED_LAST_ELAPSED = 599_000
EXPECTED_DURATION_MS = 600_000
EXPECTED_RX_LEN = 29
# Cửa sổ giữa mẫu đầu và mẫu cuối: 599000 - 10 = 598990 ms = 598.99 s.
EXPECTED_SAMPLE_SPAN_MS = 598_990

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


# 1. Integrity ---------------------------------------------------------------
for rel, expected in PINNED_SHA256.items():
    path = HERE / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
        continue
    actual = sha256(path)
    if actual != expected:
        fail(f"{rel}: SHA-256 mismatch (pinned {expected}, actual {actual})")
    else:
        print(f"[PASS] sha256 {rel} = {actual}")

if not RAW_LOG.is_file() or not CSV_PATH.is_file():
    print("W03 TEST132B VERIFY: FAIL")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)

# 2. Raw log structure --------------------------------------------------------
text = RAW_LOG.read_text(encoding="utf-8")
lines = text.splitlines()
if "CSV_BEGIN" not in lines or "CSV_END" not in lines:
    fail("raw log: CSV_BEGIN/CSV_END marker missing")
    begin = end = -1
else:
    begin = lines.index("CSV_BEGIN")
    end = lines.index("CSV_END")

if begin >= 0:
    header = lines[begin + 1]
    raw_rows = lines[begin + 2:end]
    if header != EXPECTED_HEADER:
        fail(f"raw log: unexpected header {header!r}")
    if len(raw_rows) != EXPECTED_ROWS:
        fail(f"raw log: expected {EXPECTED_ROWS} rows, found {len(raw_rows)}")

    parsed = []
    for index, row in enumerate(raw_rows, start=1):
        fields = row.split(",")
        if len(fields) != 8:
            fail(f"raw log row {index}: expected 8 columns, found {len(fields)}")
            continue
        try:
            parsed.append({
                "elapsed": int(fields[0]),
                "valid": int(fields[1]),
                "voltage": float(fields[2]),
                "current": float(fields[3]),
                "power": float(fields[4]),
                "energy": int(fields[5]),
                "rx_len": int(fields[6]),
                "status": fields[7],
            })
        except ValueError as exc:
            fail(f"raw log row {index}: unparsable field ({exc})")

    if len(parsed) == EXPECTED_ROWS:
        elapsed = [row["elapsed"] for row in parsed]
        if elapsed[0] != EXPECTED_FIRST_ELAPSED:
            fail(f"first elapsed_ms: expected {EXPECTED_FIRST_ELAPSED}, got {elapsed[0]}")
        if elapsed[-1] != EXPECTED_LAST_ELAPSED:
            fail(f"last elapsed_ms: expected {EXPECTED_LAST_ELAPSED}, got {elapsed[-1]}")
        if elapsed != sorted(elapsed):
            fail("elapsed_ms is not monotonic")
        diffs = {elapsed[i + 1] - elapsed[i] for i in range(len(elapsed) - 1)}
        if diffs != {990, 1000}:
            fail(f"unexpected sample intervals: {sorted(diffs)}")
        span = elapsed[-1] - elapsed[0]
        if span != EXPECTED_SAMPLE_SPAN_MS:
            fail(f"sample span: expected {EXPECTED_SAMPLE_SPAN_MS} ms, got {span} ms")

        valid = sum(row["valid"] for row in parsed)
        ok = sum(row["status"] == "OK" for row in parsed)
        if valid != EXPECTED_ROWS:
            fail(f"valid samples: expected {EXPECTED_ROWS}, got {valid}")
        if ok != EXPECTED_ROWS:
            fail(f"status OK samples: expected {EXPECTED_ROWS}, got {ok}")
        if any(row["current"] != 0.0 for row in parsed):
            fail("current_a is not zero on every row")
        if any(row["power"] != 0.0 for row in parsed):
            fail("power_w is not zero on every row")
        if any(row["energy"] != 0 for row in parsed):
            fail("energy_wh is not zero on every row")
        if any(row["rx_len"] != EXPECTED_RX_LEN for row in parsed):
            fail(f"rx_len is not {EXPECTED_RX_LEN} on every row")

        voltages = [row["voltage"] for row in parsed]
        v_min, v_max = min(voltages), max(voltages)
        v_mean = sum(voltages) / len(voltages)
        print(f"[INFO] rows={len(parsed)} valid={valid} ok={ok} "
              f"span={span} ms ({span / 1000:.2f} s)")
        print(f"[INFO] V min/max/mean = {v_min:.2f}/{v_max:.2f}/{v_mean:.4f} V")
        print(f"[INFO] I/P/energy = 0.00 A / 0.0 W / 0 Wh on all rows "
              f"(device display resolution)")
        print(f"[INFO] rx_len = {EXPECTED_RX_LEN} on all rows")
    else:
        voltages = []
        v_min = v_max = v_mean = float("nan")

# 3. Summary cross-check ------------------------------------------------------
summary: dict[str, str] = {}
for line in lines:
    match = re.match(r"^([A-Z_]+(?:/[A-Z_]+)?):\s*(.+)$", line)
    if match:
        summary[match.group(1)] = match.group(2).strip()

expected_summary = {
    "DURATION_MS": str(EXPECTED_DURATION_MS),
    "VALID_SAMPLES": str(EXPECTED_ROWS),
    "FAILED_SAMPLES": "0",
    "SUCCESS_RATE": "100.00 %",
}
for key, expected in expected_summary.items():
    actual = summary.get(key)
    if actual != expected:
        fail(f"summary {key}: expected {expected!r}, got {actual!r}")

if voltages:
    v_min_text = summary.get("V_MIN/MAX", "")
    if v_min_text.replace(" ", "") != f"{v_min:.2f}/{v_max:.2f}":
        fail(f"summary V_MIN/MAX {v_min_text!r} does not match CSV "
             f"{v_min:.2f}/{v_max:.2f}")
    v_mean_text = summary.get("V_MEAN")
    try:
        if abs(float(v_mean_text) - v_mean) > 0.001:
            fail(f"summary V_MEAN {v_mean_text!r} does not match CSV {v_mean:.4f}")
    except (TypeError, ValueError):
        fail(f"summary V_MEAN is missing or unparsable: {v_mean_text!r}")

for key, expected in (("I_MIN/MAX", "0.00 / 0.00"), ("P_MIN/MAX", "0.0 / 0.0")):
    if summary.get(key) != expected:
        fail(f"summary {key}: expected {expected!r}, got {summary.get(key)!r}")

# 4. The log's own gate must stay honest --------------------------------------
if summary.get("RESULT") != "REVIEW REQUIRED":
    fail("log RESULT is not 'REVIEW REQUIRED'; do not promote the capture to PASS "
         "without a new operator decision and evidence")

# 5. Extracted CSV must match the raw log ------------------------------------
csv_lines = CSV_PATH.read_text(encoding="utf-8").splitlines()
if not csv_lines or csv_lines[0] != EXPECTED_HEADER:
    fail("csv: header missing or unexpected")
if len(csv_lines) - 1 != EXPECTED_ROWS:
    fail(f"csv: expected {EXPECTED_ROWS} data rows, found {len(csv_lines) - 1}")
if begin >= 0 and csv_lines[1:] != raw_rows:
    fail("csv: rows differ from the CSV block embedded in the raw log")

# 6. TEST 131 profile frame CRC ----------------------------------------------
test131 = bytes.fromhex("01 03 02 00 01")
crc = crc16_modbus(test131)
expected_frame = test131 + bytes([crc & 0xFF, crc >> 8])
if expected_frame.hex(" ").upper() != "01 03 02 00 01 79 84":
    fail(f"TEST 131 CRC mismatch: recomputed {expected_frame.hex(' ')}")
else:
    print("[PASS] TEST 131 frame 01 03 02 00 01 79 84 -> CRC16/MODBUS 0x8479")

# Result ---------------------------------------------------------------------
if failures:
    print("W03 TEST132B VERIFY: FAIL")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)

print("W03 TEST132B VERIFY: PASS (structure, integrity, summary, CSV extraction)")
print("SCOPE: Arduino bench capture; NOT ESP-IDF W03 firmware; TEC OFF is the "
      "operator's confirmation.")
print("NOTE: sample window 598.99 s between first/last sample; the test duration "
      "constant is 600 s. The last second has no sample.")
print("NOTE: the capture's own gate is RESULT: REVIEW REQUIRED; this script does "
      "not upgrade it to PASS.")
