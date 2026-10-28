#!/usr/bin/env python3
"""Kiểm tra cấu trúc bộ chứng cứ W03 của Member A.

Script này KHÔNG xác nhận bất kỳ sự thật vật lý nào và KHÔNG phải nghiệm thu W03.
Nó chỉ kiểm tra những gì có thể kiểm tra bằng máy:

1. Đủ các file bắt buộc của hồ sơ W03.
2. Nhất quán "thiếu thì phải thiếu": các artifact được ``acceptance.md`` khai báo
   MISSING (``pzem-off.csv``, ``rs485-wiring.png``) **không** được tồn tại trên đĩa
   ở snapshot này. Nếu một buổi đo thật tạo ra chúng, phải cập nhật ``acceptance.md``
   và script này **cùng lúc** — không được để file thật xuất hiện cạnh khai báo MISSING.
3. ``acceptance.md`` có đủ 7 hạng mục A-W03-01..A-W03-07 và **có chứa** các nhãn trạng
   thái trung thực bắt buộc (``MEMBER A W03 EVIDENCE — IMPLEMENTED & VERIFIED WITHIN
   TESTED SCOPE``, ``DONE``, ``PARTIAL``, ``HARDWARE-LIMITED``, ``NOT IMPLEMENTED``,
   ``INFRASTRUCTURE-LIMITED``, ``VERIFIED BY EXISTING EVIDENCE``,
   ``MEASURED — BENCH ARTIFACT``, ``OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE``,
   ``RAW_EVIDENCE_NOT_AVAILABLE``, ``MEASUREMENT REQUIRED``, ``PENDING_READBACK``).
   Script chỉ kiểm tra *sự hiện diện* của nhãn — nó **không** đọc hiểu văn xuôi và
   **không** thể phát hiện một câu tự nhận PASS đặt ở chỗ khác. Script cũng **không**
   kiểm tra (và không được dùng để đòi) bất kỳ cổng phê duyệt chéo thành viên nào.
4. ``firmware_commit`` trong ``firmware-tooling-verification.md`` phải là SHA 40 hex
   trỏ tới một commit thật trong repo chứa **các module W03** (``cg_pzem.c``,
   ``cg_crc16.c``, ``cg_rs485.c``, ``cg_power.c``, ``cg_actuator.c``, ``cg_safety.c``,
   ``app_main.c``) và ``coldguard_config.h`` của commit đó phải có grammar 2 +
   actuator default-OFF. Giá trị tạm ``FIRMWARE_COMMIT_PENDING`` là FAIL; không chạy
   được ``git`` cũng là FAIL (claim không kiểm chứng được thì không được coi là hợp lệ).
5. Workflow CI ``.github/workflows/a-w03-espidf-build.yml`` tồn tại, dùng đúng image
   ``espressif/idf:v6.1`` + target ``esp32s3``, có ``fetch-depth: 0`` (validator cần
   lịch sử để xác minh ``firmware_commit``) và **không** chứa lệnh flash nào.
6. Các tệp trọng yếu có nội dung neo đúng thực tế (không chỉ tồn tại):
   ``hardware-deviation-and-safety.md`` neo ``CR-A-W01-01``;
   ``rs485-pin-and-compatibility.md`` neo ``TTL485``; ``ibt2-pin-map.md`` neo
   ``GPIO5``/``GPIO6``; ``pzem-register-readback.txt`` còn ở trạng thái ``PENDING``
   (snapshot này chưa từng có log PZEM thật — nếu có dữ liệu thật, cập nhật file này
   và validator cùng lúc); ``review-w03.md`` giữ nhãn "review tĩnh" của bản ghi
   lịch sử 2026-10-19.
7. Firmware trong repo khớp hồ sơ: chạy ``firmware/tools/cg_check_firmware_w03.py
   --quiet`` (parity register/scaling, read-only, CRC-trước-khi-tin, retry bound,
   default-OFF, boot order, grammar, CMake…).
8. Hai bundle bench tự kiểm tra lại được: chạy ``hardware-2026-10-27/verify_test132b.py``
   (hash, 600 hàng, span 598.99 s, gate ``REVIEW REQUIRED``, CRC TEST 131) và
   ``hardware-2026-10-20/verify_capture.py`` (7/7 hash, 601/594/7, 7 frame CRC,
   FC06 archive-only). Cả hai script chỉ đọc file, không mở serial.

Cách chạy (Windows): ``py validate_w03.py``. Trên một số máy, ``python`` là alias
Microsoft Store bị hỏng và sẽ không chạy.
"""
from pathlib import Path
import re
import subprocess
import sys

try:  # Windows consoles default to cp1252 and cannot print Vietnamese text.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]

REQUIRED_FILES = [
    "README.md",
    "acceptance.md",
    "team-dependencies.md",
    "hardware-deviation-and-safety.md",
    "logic-power-measurement.md",
    "rs485-pin-and-compatibility.md",
    "pzem-register-readback.txt",
    "ibt2-pin-map.md",
    "firmware-tooling-verification.md",
    "build-report-w03.md",
    "PR_BODY.md",
    "review-w03.md",
    "validate_w03.py",
    "hardware-2026-10-20/README.md",
    "hardware-2026-10-20/SHA256SUMS.txt",
    "hardware-2026-10-20/verify_capture.py",
    "hardware-2026-10-27/README.md",
    "hardware-2026-10-27/SHA256SUMS.txt",
    "hardware-2026-10-27/provenance-matrix.md",
    "hardware-2026-10-27/as-built-configuration.md",
    "hardware-2026-10-27/test-131-profile-readback.md",
    "hardware-2026-10-27/test-133b-reset-default-off.md",
    "hardware-2026-10-27/shunt-continuity.md",
    "hardware-2026-10-27/verify_test132b.py",
]

# Artifact canonical được acceptance.md khai báo là còn thiếu ở snapshot này. Nếu một
# trong các file này xuất hiện trên đĩa, hồ sơ đang tự mâu thuẫn và phải được rà lại.
DECLARED_MISSING = [
    "pzem-off.csv",
    "rs485-wiring.png",
]

ACCEPTANCE_ITEMS = [f"A-W03-{i:02d}" for i in range(1, 8)]

REQUIRED_ACCEPTANCE_LABELS = [
    "MEMBER A W03 EVIDENCE — IMPLEMENTED & VERIFIED WITHIN TESTED SCOPE",
    "`DONE`",
    "`PARTIAL`",
    "`HARDWARE-LIMITED`",
    "`NOT IMPLEMENTED`",
    "`INFRASTRUCTURE-LIMITED`",
    "VERIFIED BY EXISTING EVIDENCE",
    "MEASURED — BENCH ARTIFACT",
    "OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE",
    "RAW_EVIDENCE_NOT_AVAILABLE",
    "MEASUREMENT REQUIRED",
    "PENDING_READBACK",
]

FIRMWARE_COMMIT_PENDING = "FIRMWARE_COMMIT_PENDING"

# Commit firmware phải chứa đủ các module W03 - chỉ có app_main.c bootstrap là chưa
# đủ, vì như vậy hồ sơ sẽ trỏ về một commit không chứa firmware W03.
FIRMWARE_COMMIT_TREE_FILES = [
    "firmware/main/app_main.c",
    "firmware/main/cg_pzem.c",
    "firmware/main/cg_crc16.c",
    "firmware/main/cg_rs485.c",
    "firmware/main/cg_power.c",
    "firmware/main/cg_actuator.c",
    "firmware/main/cg_safety.c",
]

EXPECTED_CONFIG_HEADER = "firmware/main/coldguard_config.h"

# Trong coldguard_config.h của commit firmware phải có (whitespace co giãn):
CONFIG_EXPECTATIONS = [
    (r"#define\s+CG_LOG_GRAMMAR_VERSION\s+2\b", "grammar v2 (CG_LOG_GRAMMAR_VERSION 2)"),
    (r"#define\s+CG_ACTUATOR_ENABLE_ALLOWED\s+0\b",
     "actuator outputs compile-time refused (CG_ACTUATOR_ENABLE_ALLOWED 0)"),
    (r"#define\s+CG_PZEM_FC_READ_INPUT\s+0x04\b", "PZEM read-input FC 0x04"),
    (r"#define\s+CG_PZEM_HOLDING_CURRENT_RANGE\s+0x0003\b",
     "PZEM current-range holding register 0x0003"),
]

WORKFLOW_REL = ".github/workflows/a-w03-espidf-build.yml"

# Workflow phải dùng đúng image/target và bị CẤM có bất kỳ lệnh flash nào.
WORKFLOW_REQUIRED_SNIPPETS = [
    "espressif/idf:v6.1",
    "set-target esp32s3",
    "fetch-depth: 0",
]
WORKFLOW_FORBIDDEN_SNIPPETS = [
    "idf.py flash",
    "write_flash",
    "esptool.py",
    "esptool ",
]

# Neo nội dung: mỗi mục là (file, token bắt buộc, vì sao).
CONTENT_ANCHORS = [
    ("team-dependencies.md", "TD-W03-01",
     "bảng đầu vào còn thiếu phải neo đúng ID"),
    ("team-dependencies.md", "Đầu vào còn thiếu",
     "file phải mô tả đúng vai trò: đầu vào còn thiếu, không phải cổng phê duyệt"),
    ("hardware-deviation-and-safety.md", "CR-A-W01-01",
     "lệch freeze TTL485 vs MAX3485 phải được nêu đúng mã review"),
    ("rs485-pin-and-compatibility.md", "TTL485",
     "module as-built là TTL485-V2.0, không được viết mà bỏ mất sự thật này"),
    ("ibt2-pin-map.md", "GPIO5", "pin map IBT-2 phải neo chân thật của RPWM"),
    ("ibt2-pin-map.md", "GPIO6", "pin map IBT-2 phải neo chân thật của ENABLE"),
    ("ibt2-pin-map.md", "GPIO10",
     "lệch cấu hình GPIO10 với DS18B20 của W02 phải hiện diện trong pin map"),
    ("pzem-register-readback.txt", "PENDING",
     "snapshot này chưa có readback thật; có dữ liệu thật thì cập nhật file + validator"),
    ("review-w03.md", "review tĩnh",
     "bản review 2026-10-19 phải giữ nhãn gốc của bản ghi lịch sử"),
    ("hardware-2026-10-27/README.md", "REVIEW REQUIRED",
     "gate của TEST 132B là REVIEW REQUIRED, không được đổi thành PASS"),
    ("hardware-2026-10-27/README.md", "598.99",
     "cửa sổ mẫu thật là 598.99 s, không được làm tròn thành 600.00 s"),
    ("hardware-2026-10-27/provenance-matrix.md", "RAW CAPTURE FILE NOT AVAILABLE",
     "TEST 131 không có file capture gốc; khoảng trống phải được khai báo"),
    ("hardware-2026-10-27/as-built-configuration.md", "NOT_ASSIGNED",
     "hardware_config_id chưa được gán, không được tự điền"),
    ("hardware-2026-10-27/test-133b-reset-default-off.md", "AFTER FIRMWARE START ONLY",
     "TEST 133B không chứng minh trạng thái trước setup()"),
]

# Hai bundle bench phải tự kiểm tra lại được; script chỉ đọc file, không mở serial.
BUNDLE_VERIFIERS = [
    "hardware-2026-10-27/verify_test132b.py",
    "hardware-2026-10-20/verify_capture.py",
]

failures = []


def read_text(rel_name):
    try:
        return (ROOT / rel_name).read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{rel_name}: cannot read ({exc})")
    except UnicodeDecodeError as exc:
        failures.append(f"{rel_name}: not valid UTF-8 ({exc})")
    return ""


def firmware_commit_problem(firmware_commit):
    """Kiểm tra commit firmware: đủ module W03 + config đúng bất biến W03.

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
            f"firmware-tooling-verification.md: firmware_commit {firmware_commit} "
            f"does not contain the W03 firmware sources: {missing}"
        )

    show = subprocess.run(
        ["git", "show", f"{firmware_commit}:{EXPECTED_CONFIG_HEADER}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if show.returncode != 0:
        return (
            f"firmware-tooling-verification.md: cannot read {EXPECTED_CONFIG_HEADER} "
            f"from firmware_commit {firmware_commit}"
        )

    for pattern, label in CONFIG_EXPECTATIONS:
        if not re.search(pattern, show.stdout):
            return (
                f"firmware-tooling-verification.md: {EXPECTED_CONFIG_HEADER} of "
                f"{firmware_commit} is missing {label}"
            )
    return None


# 1. File bắt buộc ------------------------------------------------------------
for name in REQUIRED_FILES:
    if not (ROOT / name).is_file():
        failures.append(f"missing required file: {name}")

# 2. acceptance.md -----------------------------------------------------------
acceptance_text = read_text("acceptance.md")
if acceptance_text:
    for item in ACCEPTANCE_ITEMS:
        if item not in acceptance_text:
            failures.append(f"acceptance.md: missing item {item}")
    for label in REQUIRED_ACCEPTANCE_LABELS:
        if label not in acceptance_text:
            failures.append(f"acceptance.md: missing status label {label!r}")

# 3. Nhất quán thiếu/có --------------------------------------------------------
for name in DECLARED_MISSING:
    if (ROOT / name).is_file():
        failures.append(
            f"{name}: declared MISSING in acceptance.md but exists on disk — "
            "cập nhật acceptance.md hoặc bỏ file sai"
        )

# 4. firmware_commit -----------------------------------------------------------
verification_text = read_text("firmware-tooling-verification.md")
firmware_commit = ""
if verification_text:
    matches = re.findall(r"(?m)^\s*firmware_commit:\s*(\S+)\s*$", verification_text)
    if not matches:
        failures.append(
            "firmware-tooling-verification.md: no 'firmware_commit: <sha>' line found"
        )
    else:
        firmware_commit = matches[0]
        if firmware_commit == FIRMWARE_COMMIT_PENDING:
            failures.append(
                "firmware-tooling-verification.md: firmware_commit is still "
                f"{FIRMWARE_COMMIT_PENDING} - record the real firmware commit"
            )
        elif not re.fullmatch(r"[0-9a-f]{40}", firmware_commit):
            failures.append(
                "firmware-tooling-verification.md: firmware_commit must be a 40-char "
                f"git SHA or {FIRMWARE_COMMIT_PENDING}, got {firmware_commit!r}"
            )
        else:
            try:
                commit_problem = firmware_commit_problem(firmware_commit)
            except OSError as exc:
                failures.append(
                    "firmware-tooling-verification.md: cannot verify firmware_commit "
                    f"with git ({exc}); the claim is unverified"
                )
            else:
                if commit_problem is not None:
                    failures.append(commit_problem)

# 5. Workflow CI ---------------------------------------------------------------
# Path nhận cả "/" trên Windows lẫn POSIX nên dùng thẳng chuỗi tương đối.
workflow_path = REPO_ROOT / Path(WORKFLOW_REL)
if not workflow_path.is_file():
    workflow_path = REPO_ROOT.joinpath(*WORKFLOW_REL.split("/"))
workflow_text = ""
if not workflow_path.is_file():
    failures.append(f"missing workflow: {WORKFLOW_REL}")
else:
    try:
        workflow_text = workflow_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        failures.append(f"{WORKFLOW_REL}: cannot read ({exc})")
if workflow_text:
    compact = re.sub(r"\s+", " ", workflow_text)
    for snippet in WORKFLOW_REQUIRED_SNIPPETS:
        if snippet not in compact:
            failures.append(f"{WORKFLOW_REL}: missing required snippet {snippet!r}")
    for snippet in WORKFLOW_FORBIDDEN_SNIPPETS:
        if snippet in compact:
            failures.append(
                f"{WORKFLOW_REL}: contains forbidden flash command {snippet!r} — "
                "CI của W03 không được flash bất kỳ board nào"
            )

# 6. Neo nội dung --------------------------------------------------------------
for rel_name, token, reason in CONTENT_ANCHORS:
    text = read_text(rel_name)
    if text and token not in text:
        failures.append(f"{rel_name}: missing required token {token!r} ({reason})")

# 7. Firmware trong repo khớp hồ sơ -------------------------------------------
checker = REPO_ROOT / "firmware" / "tools" / "cg_check_firmware_w03.py"
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

# 8. Bundle bench tự kiểm tra ---------------------------------------------------
for rel_name in BUNDLE_VERIFIERS:
    script = ROOT / rel_name
    if not script.is_file():
        failures.append(f"bundle verifier missing: {rel_name}")
        continue
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        failures.append(f"{rel_name}: could not run ({exc})")
    else:
        if result.returncode != 0:
            failures.append(
                f"{rel_name}: FAILED (exit {result.returncode}): "
                + " | ".join((result.stdout or "").strip().splitlines()[-3:])
            )

# Kết quả ---------------------------------------------------------------------
if failures:
    print("W03 STRUCTURE FAIL")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)

print(
    "W03 STRUCTURE PASS: "
    f"{len(REQUIRED_FILES)} required files; "
    f"declared-missing honored ({', '.join(DECLARED_MISSING)}); "
    "acceptance.md covers A-W03-01..A-W03-07 with the honesty labels; "
    f"firmware_commit {firmware_commit} contains the W03 modules + grammar v2 + "
    "actuator default-OFF; "
    f"workflow {WORKFLOW_REL} (idf v6.1, esp32s3, fetch-depth 0, no flash); "
    "content anchors verified; "
    "firmware static checks PASS; "
    f"bench bundle verifiers PASS ({len(BUNDLE_VERIFIERS)})."
)
print(
    "KHÔNG PHẢI BÀI TEST NGHIỆM THU VẬT LÝ. "
    "Phần code/tooling đã kiểm chứng bằng máy; phần vật lý vẫn MEASUREMENT REQUIRED."
)
