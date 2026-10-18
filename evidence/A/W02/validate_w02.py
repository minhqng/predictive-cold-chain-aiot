#!/usr/bin/env python3
"""Kiểm tra cấu trúc bộ chứng cứ W02 của Member A.

Script này KHÔNG xác nhận bất kỳ sự thật vật lý nào và KHÔNG phải nghiệm thu W02.
Nó chỉ kiểm tra những gì có thể kiểm tra bằng máy:

1. Đủ các file bắt buộc của hồ sơ W02.
2. Mỗi ảnh khai báo trong ``screenshot-provenance.csv`` tồn tại, đúng số byte và
   đúng SHA-256 (tức ảnh không bị crop/nén lại/ghi đè).
3. Không có ảnh "mồ côi" nằm trên đĩa mà không được khai báo truy xuất nguồn.
4. ``sensor-rom-map.yaml`` parse được, đúng trạng thái nhãn vật lý còn PENDING,
   có đúng 3 vai trò T1/T2/T3 cộng 1 SPARE và đúng tập ROM đã chọn;
   ``firmware_commit`` phải trỏ tới một commit thật trong repo chứa **các module W02**
   (``cg_onewire.c``, ``cg_rom_map.c``, ``cg_ds18b20.c``, ``cg_door.c``, ``app_main.c``)
   và ROM bytes trong ``coldguard_config.h`` của commit đó phải khớp tệp này.
   Giá trị tạm ``FIRMWARE_COMMIT_PENDING`` là FAIL; không chạy được ``git`` để
   xác minh cũng là FAIL (claim không kiểm chứng được thì không được coi là hợp lệ).
5. ``acceptance.md`` có đủ 7 hạng mục A-W02-01..A-W02-07 và **có chứa** các nhãn trạng thái
   trung thực bắt buộc (``W02 NOT PASS``, ``PENDING_TEST``, ``DEFERRED``,
   ``ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING``, ``RAW_EVIDENCE_PENDING``). Script chỉ
   kiểm tra *sự hiện diện* của nhãn — nó **không** đọc hiểu văn xuôi và **không** thể
   phát hiện một câu tự nhận PASS đặt ở chỗ khác.
6. Nhất quán "thiếu thì phải thiếu": các artifact được ``acceptance.md`` khai báo
   MISSING không được tồn tại trên đĩa (và ngược lại).
7. Firmware trong repo khớp hồ sơ: chạy ``firmware/tools/cg_check_firmware.py --quiet``
   (ROM map ↔ ``coldguard_config.h``, CRC8, shared conversion, không đoán polarity…).

Cách chạy (Windows): ``py validate_w02.py``. Trên một số máy, ``python`` là alias
Microsoft Store bị hỏng và sẽ không chạy.
"""
from pathlib import Path
import csv
import hashlib
import re
import subprocess
import sys

try:  # Windows consoles default to cp1252 and cannot print Vietnamese text.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "README.md",
    "sensor-rom-map.yaml",
    "sensor-consistency-summary.md",
    "door-test-summary.md",
    "screenshot-provenance.csv",
    "acceptance.md",
    "firmware-implementation.md",
    "bench-procedure-w02.md",
    "PR_BODY.md",
    "source-archive-readme.md",
    "validate_w02.py",
    "w02_rom_enumeration_4_devices.png",
    "w02_ds18b20_600_samples_summary.png",
    "w02_mc38_24_cycles.png",
]

REPO_ROOT = ROOT.parents[2]
FIRMWARE_COMMIT_PENDING = "FIRMWARE_COMMIT_PENDING"

PROVENANCE_COLUMNS = [
    "file", "bytes", "sha256", "source_archive", "source_archive_sha256",
    "source_entry", "content_and_limitations", "provenance",
]

# Artifact canonical được acceptance.md khai báo là còn thiếu. Nếu một trong các
# file này xuất hiện trên đĩa, hồ sơ đang tự mâu thuẫn và phải được rà lại.
DECLARED_MISSING = [
    "sensor-consistency.csv",
    "door-test.csv",
    "sensor-placement.png",
]

ACCEPTANCE_ITEMS = [f"A-W02-{i:02d}" for i in range(1, 8)]

EXPECTED_ROLES = {
    "T1": "287088CA00000051",
    "T2": "28AEBF2200000006",
    "T3": "28CBE9CA00000072",
}
EXPECTED_SPARE = ["283BE5C9000000A9"]

EXPECTED_ROMS = {**EXPECTED_ROLES, "SPARE": EXPECTED_SPARE[0]}

# Commit firmware phải chứa đủ các module W02 - chỉ có app_main.c bootstrap là
# chưa đủ, vì như vậy hồ sơ sẽ trỏ về một commit không chứa firmware W02.
FIRMWARE_COMMIT_TREE_FILES = [
    "firmware/main/app_main.c",
    "firmware/main/cg_onewire.c",
    "firmware/main/cg_rom_map.c",
    "firmware/main/cg_ds18b20.c",
    "firmware/main/cg_door.c",
]

EXPECTED_ROM_CONFIG_HEADER = "firmware/main/coldguard_config.h"

ROM_MAP_STATUS = "ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING"

REQUIRED_ACCEPTANCE_LABELS = [
    "W02 NOT PASS",
    "PENDING_TEST",
    "DEFERRED",
    ROM_MAP_STATUS,
    "RAW_EVIDENCE_PENDING",
]

failures = []


def sha256_of(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(rel_name):
    try:
        return (ROOT / rel_name).read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{rel_name}: cannot read ({exc})")
    except UnicodeDecodeError as exc:
        failures.append(f"{rel_name}: not valid UTF-8 ({exc})")
    return ""


def read_csv(rel_name):
    """Đọc CSV UTF-8 (có hoặc không BOM). Lỗi được ghi nhận, không làm crash."""
    try:
        with (ROOT / rel_name).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
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


def firmware_commit_problem(firmware_commit):
    """Kiểm tra commit firmware: đủ module W02 + ROM bytes khớp tệp này.

    Trả về chuỗi mô tả lỗi, hoặc None nếu mọi thứ khớp. Có thể ném OSError
    khi không chạy được git - caller phải coi đó là FAIL, không phải bỏ qua.
    """

    missing = []
    for rel in FIRMWARE_COMMIT_TREE_FILES:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{firmware_commit}:{rel}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            missing.append(rel)
    if missing:
        return (
            f"sensor-rom-map.yaml: firmware_commit {firmware_commit} does not contain "
            f"the W02 firmware sources: {missing}"
        )

    show = subprocess.run(
        ["git", "show", f"{firmware_commit}:{EXPECTED_ROM_CONFIG_HEADER}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if show.returncode != 0:
        return (
            f"sensor-rom-map.yaml: cannot read {EXPECTED_ROM_CONFIG_HEADER} "
            f"from firmware_commit {firmware_commit}"
        )

    compact = re.sub(r"\s+", "", show.stdout).lower()
    for role, rom in EXPECTED_ROMS.items():
        byte_sequence = ",".join(f"0x{byte:02x}" for byte in bytes.fromhex(rom))
        if byte_sequence not in compact:
            return (
                f"sensor-rom-map.yaml: ROM {role} ({rom}) is absent from "
                f"{firmware_commit}:{EXPECTED_ROM_CONFIG_HEADER}"
            )
    return None


# 1. File bắt buộc ------------------------------------------------------------
for name in REQUIRED_FILES:
    if not (ROOT / name).is_file():
        failures.append(f"missing required file: {name}")

# 2 + 3. Provenance ảnh ------------------------------------------------------
header, entries = read_csv("screenshot-provenance.csv")
if header and header != PROVENANCE_COLUMNS:
    failures.append(f"screenshot-provenance.csv header mismatch: {header}")

declared = set()
for entry in entries:
    if None in entry:
        failures.append(
            "screenshot-provenance.csv: extra unquoted delimiter in row "
            f"{entry.get('file')!r}"
        )
        continue
    rel = (entry.get("file") or "").strip()
    declared.add(rel)
    target = ROOT / rel
    if not target.is_file():
        failures.append(f"declared evidence file missing on disk: {rel}")
        continue
    expected_bytes = (entry.get("bytes") or "").strip()
    if not expected_bytes:
        failures.append(f"{rel}: empty 'bytes' cell in provenance record")
    elif str(target.stat().st_size) != expected_bytes:
        failures.append(
            f"{rel}: size mismatch (declared {expected_bytes}, "
            f"on disk {target.stat().st_size})"
        )
    expected_hash = (entry.get("sha256") or "").strip().upper()
    if not expected_hash:
        failures.append(f"{rel}: empty 'sha256' cell in provenance record")
    else:
        actual_hash = sha256_of(target).upper()
        if expected_hash != actual_hash:
            failures.append(
                f"{rel}: SHA-256 mismatch (declared {expected_hash}, "
                f"on disk {actual_hash})"
            )
    for column in ("source_archive", "source_archive_sha256", "source_entry"):
        if not (entry.get(column) or "").strip():
            failures.append(f"{rel}: empty provenance column {column!r}")

on_disk = {
    p.name
    for p in sorted(ROOT.iterdir())
    if p.is_file() and p.suffix.lower() == ".png"
}
declared_pngs = {rel for rel in declared if rel.lower().endswith(".png")}
for orphan in sorted(on_disk - declared_pngs):
    failures.append(f"image on disk but not declared in provenance: {orphan}")
for stale in sorted(declared_pngs - on_disk):
    failures.append(f"declared in provenance but not a PNG on disk: {stale}")

# 4. sensor-rom-map.yaml -----------------------------------------------------
rom_text = read_text("sensor-rom-map.yaml")
if rom_text:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is None:
        print("NOTE: PyYAML không có sẵn — chỉ kiểm tra văn bản thô cho ROM map.")
        for role, rom in list(EXPECTED_ROLES.items()) + [("SPARE", EXPECTED_SPARE[0])]:
            if rom not in rom_text:
                failures.append(f"sensor-rom-map.yaml: missing ROM for {role}: {rom}")
    else:
        try:
            data = yaml.safe_load(rom_text)
        except yaml.YAMLError as exc:
            data = None
            failures.append(f"sensor-rom-map.yaml: YAML không parse được ({exc})")
        if isinstance(data, dict):
            status = str(data.get("status", "")).strip()
            if status != ROM_MAP_STATUS:
                failures.append(
                    f"sensor-rom-map.yaml: status must be {ROM_MAP_STATUS}, got {status!r}"
                )
            roles = data.get("roles") or []
            seen = {}
            for entry in roles:
                if isinstance(entry, dict):
                    seen[str(entry.get("role"))] = str(entry.get("rom_hex", ""))
            if seen != EXPECTED_ROLES:
                failures.append(
                    f"sensor-rom-map.yaml: role/ROM map mismatch: {seen}"
                )
            spare = data.get("spare") or []
            spare_roms = [
                str(e.get("rom_hex", "")) for e in spare if isinstance(e, dict)
            ]
            if spare_roms != EXPECTED_SPARE:
                failures.append(
                    f"sensor-rom-map.yaml: spare ROM mismatch: {spare_roms}"
                )
            for entry in spare:
                if isinstance(entry, dict) and entry.get("assigned_role") is not None:
                    failures.append(
                        "sensor-rom-map.yaml: spare probe must not carry a T role"
                    )
            # Nhãn vật lý phải còn PENDING ở MỌI đầu dò (cả vai trò lẫn spare) và
            # vị trí vật lý phải chưa được xác minh — nếu không, hồ sơ đang tự nhận
            # nhiều hơn bằng chứng thật.
            for entry in roles + spare:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("physical_label", "")).strip()
                if label != "PENDING":
                    failures.append(
                        "sensor-rom-map.yaml: "
                        f"{entry.get('role') or entry.get('rom_hex')}: "
                        f"physical_label must remain PENDING, got {label!r}"
                    )
            for entry in roles:
                if isinstance(entry, dict) and entry.get("physical_position_verified") is not False:
                    failures.append(
                        "sensor-rom-map.yaml: "
                        f"{entry.get('role')}: physical_position_verified must be false"
                    )

            # `firmware_commit` phải trỏ tới firmware thật trong repo. Một chuỗi
            # tạm (hoặc một commit không chứa firmware) làm hồ sơ mất truy xuất nguồn.
            firmware_commit = str(data.get("firmware_commit", "")).strip()
            if firmware_commit == FIRMWARE_COMMIT_PENDING:
                failures.append(
                    "sensor-rom-map.yaml: firmware_commit is still "
                    f"{FIRMWARE_COMMIT_PENDING} - record the real firmware commit"
                )
            elif not re.fullmatch(r"[0-9a-f]{40}", firmware_commit):
                failures.append(
                    "sensor-rom-map.yaml: firmware_commit must be a 40-char git SHA "
                    f"or {FIRMWARE_COMMIT_PENDING}, got {firmware_commit!r}"
                )
            else:
                try:
                    commit_problem = firmware_commit_problem(firmware_commit)
                except OSError as exc:
                    failures.append(
                        "sensor-rom-map.yaml: cannot verify firmware_commit with git "
                        f"({exc}); the claim is unverified"
                    )
                else:
                    if commit_problem is not None:
                        failures.append(commit_problem)
        elif data is not None:
            failures.append("sensor-rom-map.yaml: root node is not a mapping")

# 5. acceptance.md -----------------------------------------------------------
acceptance_text = read_text("acceptance.md")
if acceptance_text:
    for item in ACCEPTANCE_ITEMS:
        if item not in acceptance_text:
            failures.append(f"acceptance.md: missing item {item}")
    for label in REQUIRED_ACCEPTANCE_LABELS:
        if label not in acceptance_text:
            failures.append(f"acceptance.md: missing status label {label!r}")

# 6. Nhất quán thiếu/có --------------------------------------------------------
for name in DECLARED_MISSING:
    if (ROOT / name).is_file():
        failures.append(
            f"{name}: declared MISSING in acceptance.md but exists on disk — "
            "cập nhật acceptance.md hoặc bỏ file sai"
        )

# 6b. Bằng chứng bench đã nhập -------------------------------------------------
# Các blob bench thật (sketch Arduino standalone) được ghim bằng kích thước +
# SHA-256; số liệu khớp với các hash khai báo trong báo cáo của từng thư mục
# (`mc38/mc38-bench-report.md`, `ds18b20/`) và trong `acceptance.md`
# §4.2/§12/§13. Mismatch ⇒ bằng chứng đã bị sửa sau khi nhập.
#
# Từ lần cập nhật 7: thêm 4 blob của lần nạp + 5 reboot firmware ESP-IDF thật
# (`espidf-run/` — xem `espidf-run/flash-provenance.md`,
# `espidf-run/reboot-verification.md`, `espidf-run/runtime-cadence.md`).
# Hash khớp với các SHA-256 được ghi trong chính các tệp đó và `acceptance.md`.
# Cả hai nhóm đều là ghim bổ sung — không có blob nào bị bỏ ghim.
BENCH_BLOBS = [
    ("mc38/mc38-bench-original.txt", 2401,
     "38cdeef5f9bd6fb1e13b7183d0903ad48035dc15fdbc0a9c57e7c0b5c9fb4595"),
    ("mc38/mc38-bench.csv", 1994,
     "27690ac7a05d21dcc673dfa188e256ba5cb8e3c9e74d0d53e328f20929279619"),
    ("ds18b20/ds18b20-serial-original.txt", 32190,
     "44228795d48f223b1fdde619c184eccd1c34a56f4dd3d19fdfa12f239289b91c"),
    ("ds18b20/sensor-consistency.csv", 31533,
     "99bdc21cfe1ecbf565b2602a16d7c60871e0efe67f4a2ddb885715b446fefe21"),
    ("ds18b20/sensor-consistency-report.md", 1323,
     "2d53af0983dc5e3035f2ec2e30afdabcf1dce4b0867bdb37b94e9d1cb3b428d7"),
    ("espidf-run/flash-original-log.txt", 4180,
     "8cfaf7a3b67d018020641d739770ad38b71c248b1100263d88a64754759ed351"),
    ("espidf-run/serial-reboot-original.log", 58271,
     "e48977be20cd4e78d233f6c458d05e2d4486930283e0bac17e491320194f7854"),
    ("espidf-run/reboot-verification.json", 1018,
     "08dcd97aa88f3be5dc3bc82200eb7dea93f7ecc75425ac5d6cae15eb4815c739"),
    ("espidf-run/reboot-verification-report.txt", 806,
     "2fa3f0ed07b92d400a0b4d22e1a063344fb68e736dc83157a6d03e8f8d39388a"),
]
bench_blob_hash_verified = 0
for rel, nbytes, expected in BENCH_BLOBS:
    target = ROOT / rel
    if not target.is_file():
        failures.append(f"bench evidence missing on disk: {rel}")
        continue
    if target.stat().st_size != nbytes:
        failures.append(
            f"{rel}: size mismatch (declared {nbytes}, "
            f"on disk {target.stat().st_size})"
        )
        continue
    if sha256_of(target) != expected:
        failures.append(
            f"{rel}: SHA-256 mismatch (declared {expected}, "
            f"on disk {sha256_of(target)})"
        )
        continue
    bench_blob_hash_verified += 1

# 7. Firmware trong repo khớp hồ sơ -------------------------------------------
checker = REPO_ROOT / "firmware" / "tools" / "cg_check_firmware.py"
if not checker.is_file():
    failures.append(f"firmware checker missing: {checker}")
else:
    try:
        result = subprocess.run(
            [sys.executable, str(checker), "--quiet"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        failures.append(f"firmware checker could not run ({exc})")
    else:
        if result.returncode != 0:
            failures.append(
                "firmware static checks failed "
                f"(exit {result.returncode}): "
                + " | ".join((result.stdout or "").strip().splitlines()[-3:])
            )

# Kết quả ---------------------------------------------------------------------
if failures:
    print("W02 STRUCTURE FAIL")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)

print(
    "W02 STRUCTURE PASS: "
    f"{len(REQUIRED_FILES)} required files; "
    f"{len(entries)} provenance records verified by size + SHA-256; "
    f"{bench_blob_hash_verified}/{len(BENCH_BLOBS)} bench/flash/reboot evidence blobs "
    "verified by size + SHA-256 (mc38, ds18b20, espidf-run); "
    "ROM map 3 roles + 1 spare + firmware_commit (W02 modules + ROM bytes); "
    "acceptance.md covers A-W02-01..A-W02-07; "
    "firmware static checks PASS."
)
print("KHÔNG PHẢI BÀI TEST NGHIỆM THU VẬT LÝ. W02 VẪN Ở TRẠNG THÁI NOT PASS.")
