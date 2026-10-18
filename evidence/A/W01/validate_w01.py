#!/usr/bin/env python3
"""Kiểm tra cấu trúc bộ chứng cứ W01 của Member A.

Script này KHÔNG chứng nhận tính đúng/sai vật lý và KHÔNG phải nghiệm thu
hardware freeze. Nó chỉ kiểm tra: đủ 24 dòng BOM theo thứ tự, header CSV hợp lệ,
nhãn provenance thuộc danh sách cho phép, và mọi tham chiếu ảnh đều tồn tại.

Kiểm tra bổ sung sau khi reconcile bộ 25 ảnh:
- Không dòng nào có dấu phân cách thừa (lỗi cột lệch âm thầm).
- `photos/` không có file "mồ côi" ngoài `photo-inventory.csv`, và ngược lại
  (mọi file thật trên đĩa phải được khai báo truy xuất nguồn).
- CSV không hợp lệ UTF-8 được báo là FAIL, không làm script crash.
"""
from pathlib import Path
import csv
import sys

try:  # Windows consoles default to cp1252 and cannot print Vietnamese text.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "README.md",
    "bom-audit.csv",
    "photo-inventory.csv",
    "pin-candidates-v0.md",
    "physical-risk-ledger.md",
    "legacy-assumption-check.md",
    "hardware-audit-w01.md",
    "freeze-deviation-review.md",
    "acceptance.md",
    "team-w01-member-a-summary.md",
    "PR_BODY.md",
    "validate_w01.py",
]

BOM_COLUMNS = [
    "id", "frozen_item", "frozen_spec", "frozen_qty", "observed_item",
    "observed_qty", "inspection_status", "visible_marking", "seller_sku",
    "physical_condition", "photo_ref", "deviation_or_uncertainty", "next_action",
]

PHOTO_COLUMNS = [
    "file", "source_upload_filename", "content_and_limitations",
    "provenance", "cropped",
]

ALLOWED_STATUS = {
    "PRESENT_PHOTOGRAPHED",
    "PRESENT_PHOTOGRAPHED_PARTIAL",
    "PRESENT_PHOTOGRAPHED_TEST_REPORTED",
    "PRESENT_REPORTED",
    "PRESENT_REPORTED_PARTIAL",
    "PRESENT_REPORTED_TEST_REPORTED",
    "PARTIAL_QUANTITY",
    "UNAPPROVED_SUBSTITUTION",
    "UNVERIFIED",
}

failures = []


def read_csv(rel_name):
    """Đọc CSV UTF-8 (có hoặc không BOM). Lỗi được ghi nhận, không làm crash."""
    try:
        with (ROOT / rel_name).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])
            rows = list(reader)
        return header, rows
    except UnicodeDecodeError as exc:
        failures.append(f"{rel_name}: not valid UTF-8 ({exc})")
    except csv.Error as exc:
        failures.append(f"{rel_name}: malformed CSV ({exc})")
    except OSError as exc:
        failures.append(f"{rel_name}: cannot read ({exc})")
    return [], []


for name in REQUIRED_FILES:
    if not (ROOT / name).is_file():
        failures.append(f"missing required file: {name}")

bom_header, bom_rows = read_csv("bom-audit.csv")
if bom_header and bom_header != BOM_COLUMNS:
    failures.append(f"bom-audit.csv header mismatch: {bom_header}")

expected_ids = [f"HW-{i:02d}" for i in range(1, 25)]
actual_ids = [r.get("id") for r in bom_rows]
if actual_ids != expected_ids:
    failures.append(f"bom-audit.csv expected 24 sorted IDs; got {actual_ids}")

for row in bom_rows:
    if None in row:
        failures.append(f"{row.get('id')}: extra unquoted delimiter in row")
        continue
    status = row.get("inspection_status")
    if status not in ALLOWED_STATUS:
        failures.append(f"{row.get('id')}: unknown inspection_status {status!r}")
    for column, value in row.items():
        if column and (value is None or not value.strip()):
            failures.append(f"{row.get('id')}: empty cell in column {column!r}")

photo_header, photos = read_csv("photo-inventory.csv")
if photo_header and photo_header != PHOTO_COLUMNS:
    failures.append(f"photo-inventory.csv header mismatch: {photo_header}")

declared = set()
for entry in photos:
    if None in entry:
        failures.append(
            "photo-inventory.csv: extra unquoted delimiter in row "
            f"{entry.get('file')!r}"
        )
        continue
    rel = (entry.get("file") or "").strip()
    declared.add(rel)
    if not (ROOT / rel).is_file():
        failures.append(f"missing photo: {rel}")

on_disk = {
    f"photos/{p.name}"
    for p in sorted((ROOT / "photos").glob("*"))
    if p.is_file()
}
for orphan in sorted(on_disk - declared):
    failures.append(f"photo on disk but not declared in photo-inventory.csv: {orphan}")
for stale in sorted(declared - on_disk):
    failures.append(f"photo declared but missing on disk: {stale}")

for row in bom_rows:
    for ref in (row.get("photo_ref") or "").split(";"):
        ref = ref.strip()
        if ref and ref != "NONE" and not (ROOT / ref).is_file():
            failures.append(f"{row['id']}: missing BOM photo: {ref}")

if failures:
    print("W01 STRUCTURE FAIL")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)

print(
    "W01 STRUCTURE PASS: 24 BOM rows; "
    f"{len(photos)} photo records; file references valid."
)
print("KHÔNG PHẢI BÀI TEST NGHIỆM THU VẬT LÝ / HARDWARE FREEZE.")
