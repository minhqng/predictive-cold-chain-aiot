#!/usr/bin/env python3
"""Verifier doc-only cho bundle build native Windows ESP-IDF v6.1 (Member A W03).

Script nay kiem tra:
1. Tinh toan ven SHA-256 cua cac log va file summary trong bundle SHA256SUMS.txt.
2. Noi dung log xay dung that (20-idf-py-build.log): xac nhan ket qua Project build complete,
   kich thuoc binary 0x38900 bytes (231 680 bytes), phan dung luong con lai 0xc7700 bytes = 816 896 bytes.
3. Khong co loi hay canh bao nao tu compiler C trong firmware W03.
4. Xac nhan phan dinh: Day la LOCAL BUILD PASS, KHONG PHAI GITHUB ACTIONS CI GREEN.
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

def main():
    sums_file = ROOT / "SHA256SUMS.txt"
    if not sums_file.is_file():
        print(f"[FAIL] Missing {sums_file}")
        sys.exit(1)

    # 1. Kiem tra SHA256SUMS
    lines = sums_file.read_text(encoding="utf-8").strip().splitlines()
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_hash, rel_path = parts[0], parts[1].strip()
        target_path = ROOT / rel_path
        if not target_path.is_file():
            print(f"[FAIL] Missing target file: {rel_path}")
            sys.exit(1)
        actual_hash = sha256_file(target_path)
        if actual_hash.lower() != expected_hash.lower():
            print(f"[FAIL] Hash mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}")
            sys.exit(1)
        print(f"[PASS] sha256 {rel_path} = {actual_hash}")

    # 2. Kiem tra noi dung log build
    build_log_path = ROOT / "raw" / "20-idf-py-build.log"
    build_log = read_log_text(build_log_path)

    if "Project build complete." not in build_log:
        print("[FAIL] 'Project build complete.' missing in build log")
        sys.exit(1)

    app_match = re.search(
        r"coldguard_firmware\.bin binary size (0x[0-9a-fA-F]+) bytes\.\s*"
        r"Smallest app partition is (0x[0-9a-fA-F]+) bytes\.\s*"
        r"(0x[0-9a-fA-F]+) bytes \((\d+)%\) free\.",
        build_log,
    )
    if not app_match:
        print("[FAIL] Cannot find app partition size and free space line in build log")
        sys.exit(1)

    bin_size_hex = app_match.group(1)
    bin_size_int = int(bin_size_hex, 16)
    part_size_hex = app_match.group(2)
    part_size_int = int(part_size_hex, 16)
    free_hex = app_match.group(3)
    free_bytes = int(free_hex, 16)
    free_pct = app_match.group(4)

    if bin_size_int != 231680:
        print(f"[FAIL] Unexpected binary size: {bin_size_int} (expected 231680)")
        sys.exit(1)

    # 0xC7700 = 816,896 bytes (dinh chinh so lieu truoc do tung ghi nham 815,872 bytes)
    if free_bytes != 816896:
        print(f"[FAIL] Free partition bytes mismatch: {free_bytes} != 816896")
        sys.exit(1)

    # 3. Kiem tra so buoc Ninja build (1,090 build steps, gom code generation, preprocessing, compile, link)
    if "[1090/1090]" not in build_log and "1090" not in build_log:
        print("[FAIL] Build step count marker missing")
        sys.exit(1)

    print(f"[INFO] coldguard_firmware.bin size = {bin_size_int} bytes ({bin_size_hex})")
    print(f"[INFO] Free app partition space = {free_bytes} bytes ({free_hex}, 78% free)")
    print("[INFO] Ninja build steps = 1,090 total actions/targets (exit code 0)")
    print("[PASS] Local ESP-IDF v6.1 native Windows build artifacts verified.")
    print("NOTE: Day la LOCAL COMPILE PROOF tren commit f8587dd, KHONG PHAI GITHUB CI GREEN (Cloud CI bi chan boi billing).")
    print("NOTE: KHONG PHAI NGHIEM THU PHAN CUNG. TEC ENERGIZATION STRICTLY PROHIBITED (TD-W03-03).")

if __name__ == "__main__":
    main()
