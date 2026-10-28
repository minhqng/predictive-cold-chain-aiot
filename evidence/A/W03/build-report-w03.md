# W03 build report — biên dịch ESP-IDF thật trên GitHub Actions (Member A)

Tệp này ghi **kết quả biên dịch thật** của firmware W03 bằng ESP-IDF chính thức
(image `espressif/idf:v6.1`, target `esp32s3`) và cố định các tham chiếu (run, log,
artifact, SHA-256). Nó **không** phải bằng chứng phần cứng: firmware **chưa** được nạp,
**chưa** được chạy trong W03, không cổng serial nào được mở, không tải/TEC nào được cấp
nguồn.

> **Trạng thái điền số:** lần build đầu tiên của nhánh (run `39212308802`) **FAIL** vì
> một lỗi biên dịch thật — xem §4. Sau fix (`b858693`), run thứ hai
> (`39213118829`, commit `ae1744d`) **SUCCESS cả hai job**; số liệu thật ở §2/§3.
> Mọi giá trị dưới đây được chép nguyên văn từ log/artifact của run đó, không suy diễn.

## 1. Bối cảnh

- Máy cục bộ của Member A **không có** ESP-IDF, Docker hay trình biên dịch C cho Xtensa
  (giới hạn đã khai báo trong `firmware-tooling-verification.md` §6).
- Vì vậy build thật chạy trên **GitHub Actions**, dùng đúng image mà README gốc repo chỉ
  định cho việc verify firmware: `espressif/idf:v6.1` (linux/amd64).
- Workflow W03: `.github/workflows/a-w03-espidf-build.yml`, **2 job**:
  1. `espidf-build` — mô phỏng đúng quy trình README: copy `firmware/` sang thư mục scratch
     (giữ `build/` + `sdkconfig` khỏi cây repo) rồi chạy `idf.py set-target esp32s3 &&
     idf.py build` trong container; thu artifact + SHA-256.
  2. `host-checks` — chạy lại đúng 5 lớp kiểm tra không cần phần cứng của W03 trên runner
     (`run_all_checks_w03.py` là bản gộp; job chạy từng lệnh để log rõ ràng): unittest
     (W02+W03), static W03, static W02, `validate_w02.py`, `validate_w03.py`. Job này cần
     `fetch-depth: 0` vì `validate_w03.py` dùng `git cat-file` để xác minh `firmware_commit`.
- Trigger: push lên `feat/a-w03-power-pzem-logic` chạm `firmware/**` hoặc chính file
  workflow; `pull_request` vào `feat/a-w02-sensor-foundation` **và** `main` (cùng paths);
  `workflow_dispatch`.
- Cả hai job **không** flash, **không** mở serial, **không** chạy tải nào, **không** dùng
  secret nào. A green run là bằng chứng **COMPILE PASS + HOST CHECKS PASS**, không bao giờ
  là bằng chứng bench.

## 2. Kết quả (nguyên văn từ log/artifact thật)

| Mục | Giá trị |
|---|---|
| Kết quả `espidf-build` | **SUCCESS — COMPILE PASS (ESP32-S3)** |
| Kết quả `host-checks` | **SUCCESS** (unittest 113 + static W03 84 + static W02 39 + validate_w02 + validate_w03) |
| Commit được build | `source_commit=ae1744d1f55fe5a78e8453329402062275c96ba2` (`environment.txt`; là tip của nhánh khi push C+D — **cây firmware giống hệt** `firmware_commit b858693`, kiểm bằng `git diff b858693 ae1744d -- firmware` rỗng) |
| Run URL | https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39213118829 (id `39213118829`, event `push`) |
| Runner / image | `ubuntu-latest`, job container `espressif/idf:v6.1` |
| ESP-IDF | `ESP-IDF v6.1` (`idf.py --version`) |
| Toolchain | `xtensa-esp-elf-gcc (crosstool-NG esp-15.2.0_20251204) 15.2.0` |
| Python / CMake | `Python 3.12.3` / `cmake version 4.0.3` |
| Target | `esp32s3` |
| Cảnh báo compiler trong toàn bộ log build | **0** (đếm bằng `Select-String -Pattern "warning:"` trên `20-idf-py-build.log`) |
| Kích thước | `coldguard_firmware.bin` = 230 976 bytes (`0x38640`); phân vùng app nhỏ nhất `0x100000`; **78% trống** (`0xc79c0`) |
| Dòng cuối log build | `coldguard_firmware.bin binary size 0x38640 bytes. …` (sau `Project build complete`) |
| Artifact | `a-w03-espidf-build-report` (2 110 446 bytes, id `12168348689`) — environment, log, sdkconfig, firmware + checksum; giữ 90 ngày |

## 3. SHA-256 của artifact firmware (nguyên văn từ `30-artifacts.txt` của job)

| File | Bytes | SHA-256 |
|---|---|---|
| `coldguard_firmware.bin` | 230 976 | `c84d651b75b329c5eb5d356ffa99333f59950be39aa476f4e387605aca7afaf7` |
| `coldguard_firmware.elf` | 4 557 152 | `3656dedffdfb06af37c785fd3a629bc9e7892a8b3d3bdb6fe06cc83eeb0fe483` |
| `coldguard_firmware.map` | 3 790 506 | `4db46214fd92338cb21ce3818922ae138e9e526a75edf1d6d9deb068e8c8a3f2` |
| `bootloader.bin` | 21 120 | `4260ddd36281b754a4d9b7a3b8283597265705644cece61e092ef8b7fb770cb4` |
| `partition-table.bin` | 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| `flasher_args.json` | 927 | `e145340bd24e90bc2881eb0debbf65c80d3c25048aa194239576d2981edceb9f` |
| `sdkconfig` | 92 884 | `15607c6fd88332fbfe2e6e62036b152477382a6df54f9d97926755d38f14a335` |

Các giá trị trên do chính job in ra (`sha256sum` trong bước "Collect firmware artifacts
and checksums"), không sao chép tay.

## 4. Lần build đầu FAIL và cách sửa (2026-10-19)

- Run đầu tiên — commit `5a6cb1f`, push đầu của nhánh: job `espidf-build` **FAILURE**
  tại bước `idf.py build`; job `host-checks` **SUCCESS** (unittest + static + cả hai
  validator).
  https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39212308802
- Lỗi compiler thật trong log (một dòng lỗi duy nhất, không có lỗi nào khác):
  `/tmp/coldguard-firmware-build/main/coldguard_config.h:151:29: error: expected identifier before numeric constant`
- Nguyên nhân: `cg_rs485.h` khai báo `enum { CG_RS485_DIR_AUTO, CG_RS485_DIR_MANUAL }`
  trong khi `coldguard_config.h` có `#define CG_RS485_DIR_MANUAL 1` (switch compile-time).
  Ở translation unit include config **trước** header (ví dụ `cg_power.c`), macro thay thế
  enum constant ngay trong khai báo enum ⇒ lỗi. Lớp kiểm tra tĩnh + unittest cục bộ
  **không thể** thấy loại lỗi này — đúng vai trò của compile thật.
- Sửa: commit `b858693` — enum đổi tên thành `CG_RS485_MODE_AUTO/MANUAL`; `cg_rs485.c`
  và `cg_power.c` cập nhật; tên macro compile-time giữ nguyên (không đổi hành vi).
  Quét bổ sung toàn bộ `firmware/main`: **không còn** xung đột macro/enum nào khác.
- Sau sửa: chạy lại 5 lớp kiểm tra cục bộ (`run_all_checks_w03.py`) → **5/5 PASS**;
  `firmware_commit` của hồ sơ cập nhật thành `b858693`.
- Run thứ hai — commit `ae1744d` (fix + cập nhật evidence): **SUCCESS cả hai job**
  (build + host-checks) — số liệu đầy đủ ở §2/§3. Đây là run được dùng để tuyên bố
  **COMPILE PASS + HOST CHECKS PASS** cho W03.

## 5. Quan hệ với `firmware_commit`

- `firmware_commit` ghi trong `firmware-tooling-verification.md` trỏ tới commit firmware
  W03 (chứa `cg_pzem.c`, `cg_crc16.c`, `cg_rs485.c`, `cg_power.c`, `cg_actuator.c`,
  `cg_safety.c`, `app_main.c`, `coldguard_config.h` grammar 2). `validate_w03.py` xác minh
  bằng `git cat-file`/`git show`, không chỉ so chuỗi.
- Run build lại được kích hoạt bởi push chứa chính commit đó. Nếu build lại (dù cùng
  commit), byte có thể đổi (đường dẫn/timestamp trong ELF) — khi đó phải cập nhật lại bảng
  §3, không dán lại số cũ.

## 6. Giới hạn của tuyên bố này (không giấu)

1. Đây là **COMPILE PASS + HOST CHECKS PASS**, không phải hardware pass. Firmware W03
   **chưa** nạp và **chưa** chạy lần nào; không có dòng `#CG PZEM*` nào là thật.
2. Không bài test vật lý nào chạy trong CI: RS-485 vẫn `MEASUREMENT REQUIRED` cho mức logic
   (CR-A-W01-01), PZEM vẫn `PENDING_READBACK`, OFF envelope vẫn `MEASUREMENT REQUIRED`,
   IBT-2 vẫn chờ phép đo tie-off + cold-boot log.
3. Lớp test hành vi vẫn là mô hình Python + kiểm tra tĩnh; compile pass **không** thay thế
   golden-run trên target.
4. Nhánh `CG_RS485_DIR_MODE 1` (MANUAL, MAX3485 canonical) là nhánh **compile-time không
   được build trong CI** (mặc định là AUTO theo phần cứng as-built). Nếu đổi sang
   module MAX3485 đúng freeze, cần thêm build variant (đổi macro) trước khi tin nhánh đó.
   Ghi ở đây để không ai đọc code MANUAL như đã được compile.

## 7. Bằng chứng biên dịch Native Windows ESP-IDF v6.1 cho commit `f8587dd` (2026-10-27)

- **Bối cảnh:** Sau khi phân phối commit `f8587dd` lên PR #9, GitHub Actions runner trên mây bị chặn khởi chạy bởi giới hạn thanh toán của tài khoản kho mã (`Billing & plans` — run `40532665748`, `40532676477`).
- **Bằng chứng độc lập:** Để cung cấp bằng chứng kỹ thuật rằng mã nguồn C của commit `f8587dd` biên dịch thành công mà không có lỗi cú pháp hay liên kết, bộ công cụ native ESP-IDF v6.1 chính thức (Xtensa GCC 15.2.0, CMake 4.0.3, Ninja 1.12.1) đã được cài đặt và thực thi trên máy trạm Windows trong thư mục scratch cách ly hoàn toàn.
- **Thư mục bằng chứng:** `evidence/A/W03/build-native-windows-2026-10-27/`
- **Kết quả:** `LOCAL ESP-IDF v6.1 BUILD: PASS`
  - Target: `esp32s3`
  - Lệnh: `idf.py set-target esp32s3` (exit 0) && `idf.py build` (exit 0)
  - 1.090 bước Ninja hoàn tất (0 cảnh báo compiler, 0 lỗi).
  - `coldguard_firmware.bin`: 231.680 bytes (`0x38900`), SHA-256 `1AA56B48D9DF6B4CCEE15275A9E2F7F400893EB1E88AD777C33C780E3A5085A9`
  - `coldguard_firmware.elf`: 4.587.188 bytes, SHA-256 `323C7B6D5178EC00C38E3A2202A1CD365BDE35EB532D86D387B14E1E7EF66C0C`
  - Phân vùng app: `0x100000` (1.048.576 bytes); dung lượng trống: `0xc7700` = 816.896 bytes (78% trống).
  - Verifier script: `py evidence/A/W03/build-native-windows-2026-10-27/verify_build.py` (PASS).
- **Ranh giới:** Bằng chứng này xác nhận tính đúng đắn kỹ thuật của mã nguồn C, nhưng **KHÔNG** làm thay đổi trạng thái Cloud CI của GitHub (vẫn cần tài khoản kho mã xử lý thanh toán) và **KHÔNG** phải nghiệm thu phần cứng (TD-W03-01..11 giữ nguyên, nghiêm cấm cấp nguồn TEC).

## 7.1. Bổ sung 2026-10-28 — build lại trên working tree hiện tại

- **Vì sao:** bundle `2026-10-27` build từ `git archive f8587dd`, **không** chứa các thay đổi
  firmware còn trong working tree (`cg_actuator.c/.h`, `cg_door.h`, `cg_log.c/.h`,
  `coldguard_config.h`). Bằng chứng compile phải khớp đúng nguồn sẽ được commit.
- **Thư mục bằng chứng:** `evidence/A/W03/build-native-windows-2026-10-28/` (log thô,
  `SHA256SUMS.txt`, `verify_build.py`, `README.md`).
- **Kết quả:** `LOCAL ESP-IDF v6.1 BUILD: PASS` — `idf.py set-target esp32s3` và `idf.py build`
  exit `0`; `1090/1090` bước Ninja; **0** warning, **0** error; `Project build complete.`
  - `coldguard_firmware.bin`: 231.712 bytes (`0x38920`), trống `0xc76e0` (78%)
  - SHA-256: bin `3855196680e675ff792eeb85f765dc1f6c8e3ee976f14a874eeafd243823fe4d`,
    elf `7f1e83b7c9872014c8ad14665b493b2a25aa8d8d67ec7d4461aee2c24cf9fc02`
  - Verifier: `py evidence/A/W03/build-native-windows-2026-10-28/verify_build.py` (PASS)
- **Ranh giới:** vẫn là build cục bộ, **không** phải GitHub Actions CI và **không** phải nghiệm
  thu phần cứng. Không cấp nguồn TEC, không PWM, không flash.
