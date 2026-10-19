# W03 build report — biên dịch ESP-IDF thật trên GitHub Actions (Member A)

Tệp này ghi **kết quả biên dịch thật** của firmware W03 bằng ESP-IDF chính thức
(image `espressif/idf:v6.1`, target `esp32s3`) và cố định các tham chiếu (run, log,
artifact, SHA-256). Nó **không** phải bằng chứng phần cứng: firmware **chưa** được nạp,
**chưa** được chạy trong W03, không cổng serial nào được mở, không tải/TEC nào được cấp
nguồn.

> **Trạng thái điền số:** phiên bản này được commit **trước** lần chạy CI đầu tiên của
> nhánh W03. Các ô kết quả (run URL, SHA-256, cảnh báo…) được **cập nhật bằng một commit
> evidence-only ngay sau khi run đầu tiên kết thúc** — đúng nội dung log/artifact thật,
> không suy diễn. Nếu bạn đọc bản này mà §2 vẫn ghi "cập nhật sau", nghĩa là bạn đang ở
> commit trước bước cập nhật đó; kiểm tra danh sách run của workflow.

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

## 2. Kết quả (điền từ log/artifact thật sau run đầu tiên)

| Mục | Giá trị |
|---|---|
| Kết quả `espidf-build` | _cập nhật sau lần chạy đầu tiên_ |
| Kết quả `host-checks` | _cập nhật sau lần chạy đầu tiên_ |
| Commit được build | _cập nhật (từ `environment.txt`: `source_commit=…`)_ |
| Run URL | _cập nhật sau lần chạy đầu tiên_ |
| Runner / image | `ubuntu-latest`, job container `espressif/idf:v6.1` |
| Target | `esp32s3` |
| Cảnh báo compiler | _cập nhật (đếm trên `20-idf-py-build.log`)_ |
| Artifact | `a-w03-espidf-build-report` (environment, log, sdkconfig, firmware + checksum) |

## 3. SHA-256 của artifact firmware (điền nguyên văn từ `30-artifacts.txt` của job)

| File | Bytes | SHA-256 |
|---|---|---|
| `coldguard_firmware.bin` | _cập nhật_ | _cập nhật_ |
| `coldguard_firmware.elf` | _cập nhật_ | _cập nhật_ |
| `bootloader.bin` | _cập nhật_ | _cập nhật_ |
| `partition-table.bin` | _cập nhật_ | _cập nhật_ |

## 4. Quan hệ với `firmware_commit`

- `firmware_commit` ghi trong `firmware-tooling-verification.md` trỏ tới commit firmware
  W03 (chứa `cg_pzem.c`, `cg_crc16.c`, `cg_rs485.c`, `cg_power.c`, `cg_actuator.c`,
  `cg_safety.c`, `app_main.c`, `coldguard_config.h` grammar 2). `validate_w03.py` xác minh
  bằng `git cat-file`/`git show`, không chỉ so chuỗi.
- Run đầu tiên được kích hoạt bởi chính commit đó (push nhánh). Nếu build lại (dù cùng
  commit), byte có thể đổi (đường dẫn/timestamp trong ELF) — khi đó phải cập nhật lại bảng
  §3, không dán lại số cũ.

## 5. Giới hạn của tuyên bố này (không giấu)

1. Đây là **COMPILE PASS + HOST CHECKS PASS**, không phải hardware pass. Firmware W03
   **chưa** nạp và **chưa** chạy lần nào; không có dòng `#CG PZEM*` nào là thật.
2. Không bài test vật lý nào chạy trong CI: RS-485 vẫn chờ duyệt mức logic (CR-A-W01-01),
   PZEM vẫn `PENDING_READBACK`, OFF envelope vẫn `MEASUREMENT REQUIRED`, IBT-2 vẫn chờ D
   duyệt tie-off + cold-boot log.
3. Lớp test hành vi vẫn là mô hình Python + kiểm tra tĩnh; compile pass **không** thay thế
   golden-run trên target.
4. Nhánh `CG_RS485_DIR_MODE 1` (MANUAL, MAX3485 canonical) là nhánh **compile-time không
   được build trong CI** (mặc định là AUTO theo phần cứng as-built). Nếu D/leader chọn mua
   module MAX3485 đúng freeze, cần thêm build variant (đổi macro) trước khi tin nhánh đó.
   Ghi ở đây để không ai đọc code MANUAL như đã được compile.
