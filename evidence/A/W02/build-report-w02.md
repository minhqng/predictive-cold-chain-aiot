# W02 build report — biên dịch ESP-IDF thật trên GitHub Actions (Member A)

Tệp này ghi **kết quả biên dịch thật** của firmware W02 bằng ESP-IDF chính thức
(image `espressif/idf:v6.1`, target `esp32s3`) và cố định các tham chiếu (run, log,
artifact, SHA-256). Nó **không** phải bằng chứng phần cứng: firmware **chưa** được nạp,
**chưa** được chạy, không có cổng serial nào được mở, không có tải/TEC nào được cấp nguồn.

## 1. Bối cảnh

- Máy cục bộ của Member A **không có** ESP-IDF, Docker hay trình biên dịch C (giới hạn đã
  khai báo ở `firmware-implementation.md` §5.1 trước lần cập nhật này).
- Vì vậy build thật chạy trên **GitHub Actions**, dùng đúng image mà README gốc repo chỉ
  định cho việc verify firmware: `espressif/idf:v6.1` (linux/amd64).
- Workflow: `.github/workflows/a-w02-espidf-build.yml`. Workflow mô phỏng đúng quy trình
  README: copy `firmware/` sang thư mục scratch (giữ `build/` + `sdkconfig` khỏi cây repo)
  rồi chạy `idf.py set-target esp32s3 && idf.py build`. Trigger: push lên nhánh
  `feat/a-w02-sensor-foundation`, PR vào `main` chạm `firmware/**` hoặc chính file
  workflow, và `workflow_dispatch`.
- Job **không** flash, **không** mở serial, **không** chạy bất kỳ tải nào, **không** dùng
  secret nào; chỉ biên dịch và upload log + artifact.

## 2. Kết quả

| Mục | Giá trị (từ log/artifact thật) |
|---|---|
| Kết quả | **SUCCESS — COMPILE PASS (ESP32-S3)** |
| Commit được build | `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` (`environment.txt`: `source_commit=…`) |
| Run (push) | https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117530768 (id `39117530768`) |
| Run (pull_request, cùng commit) | https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117534103 (id `39117534103`) |
| Runner | `ubuntu-latest`, job container `espressif/idf:v6.1` |
| ESP-IDF | `ESP-IDF v6.1` (`idf.py --version`) |
| Toolchain | `xtensa-esp-elf-gcc (crosstool-NG esp-15.2.0_20251204) 15.2.0` |
| Python / CMake | `Python 3.12.3` / `cmake version 4.0.3` |
| Target | `esp32s3` |
| Cảnh báo compiler trong toàn bộ log build | **0** (đếm bằng `Select-String -Pattern warning -CaseSensitive:$false` trên `20-idf-py-build.log`) |
| Kích thước | `coldguard_firmware.bin` = `0x31360` (201 568) bytes; partition app `0x100000`; **81% trống** (`0xceca0`); bootloader `0x5280` (36% trống) |
| Dòng cuối log build | `Project build complete. To flash, run: …` |
| Artifact | `a-w02-espidf-build-report` (2 021 244 bytes) — chứa environment, log, sdkconfig, firmware + checksum |

## 3. SHA-256 của artifact firmware (nguyên văn từ `30-artifacts.txt` của job)

| File | Bytes | SHA-256 |
|---|---|---|
| `coldguard_firmware.bin` | 201 568 | `9227ce45461916469fd6dd23ab5aae708c7f736c0eaaeaefa0546e7d15e395c8` |
| `coldguard_firmware.elf` | 4 427 488 | `5b95f5302892db35baf15aa704a29a54341967264408cc116257eb3c28f88fa6` |
| `coldguard_firmware.map` | 3 739 419 | `977d5ef145a4dd1b6699415d393512f700ca2e3717be4d08498c1c491405ee85` |
| `bootloader.bin` | 21 120 | `59c6bfa9a606d39bfbe073f9da6e37162b0c977c1ae6f5fbae9b9165709b98fe` |
| `partition-table.bin` | 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| `flasher_args.json` | 927 | `e145340bd24e90bc2881eb0debbf65c80d3c25048aa194239576d2981edceb9f` |
| `sdkconfig` | 92 884 | `15607c6fd88332fbfe2e6e62036b152477382a6df54f9d97926755d38f14a335` |

Các giá trị trên do chính job in ra (`sha256sum` trong bước "Collect firmware artifacts
and checksums"), không sao chép tay; artifact GitHub được giữ 90 ngày.

## 4. Lần build đầu FAIL và cách sửa (giữ lại để truy vết)

- Run đầu tiên — commit `1ba52b2` (khi đó firmware còn khai báo
  `REQUIRES driver esp_timer nvs_flash`): **FAILURE** tại bước build.
  https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117011427
- Lỗi compiler thật trong log:
  - `main/cg_onewire.c:16:10: fatal error: driver/gpio.h: No such file or directory`
  - `main/cg_door.c:8:10: fatal error: driver/gpio.h: No such file or directory`
    (các file khác chưa tới lượt build; `cg_safety.c` cũng include `driver/gpio.h`.)
- Thông điệp của build system: *"… includes driver/gpio.h, provided by esp_driver_gpio
  component(s). … add esp_driver_gpio to PRIV_REQUIRES list of idf_component_register
  call in main/CMakeLists.txt"*.
- Nguyên nhân (đối chiếu mã nguồn ESP-IDF v6.1):
  1. Từ v5.3/v6, GPIO APIs nằm ở component `esp_driver_gpio`; meta-component `driver`
     **không** re-export include path của nó (chỉ để `esp_driver_gpio` trong PRIV_REQUIRES
     — xem `components/driver/CMakeLists.txt` của v6.1).
  2. Trên v6.1, quy tắc "main tự động require mọi component" **chỉ áp dụng khi main không
     tự khai báo REQUIRES/PRIV_REQUIRES** (`tools/cmake/project.cmake`: *"This behavior
     should only be when user did not set REQUIRES/PRIV_REQUIRES manually"*). Vì
     `firmware/main/CMakeLists.txt` có khai báo REQUIRES nên quy tắc đó **không** áp dụng.
- Sửa: commit `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` — `firmware/main/CMakeLists.txt`
  thêm `PRIV_REQUIRES esp_driver_gpio` và bỏ `driver` (không còn API nào của meta-component
  này được dùng).
- Sau sửa: chạy lại toàn bộ kiểm tra cục bộ (`run_all_checks.py`: 57 test + 39 check tĩnh +
  validator = **3/3 PASS**), rồi build lại bằng ESP-IDF thật → **SUCCESS** (mục 2).

## 5. Quan hệ với `firmware_commit` và dữ liệu 3 ảnh

- `firmware_commit` của hồ sơ nay là `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc`.
  Toàn bộ `firmware/main/*.c`/`*.h` giữa commit cũ
  `0eb1f8a9731e4810304332910df168ce30de30b5` và commit được build là **giống hệt từng
  byte**; chỉ `CMakeLists.txt` đổi (kiểm bằng
  `git diff --quiet 0eb1f8a..2a5a0da -- firmware/main/<file>`).
- 3 ảnh bằng chứng vẫn là ảnh của phiên bench cũ (`NOT_IN_REPO`); build này **không** được
  dùng để suy ngược hành vi sketch cũ.

## 6. Giới hạn của tuyên bố này (không giấu)

1. Đây là **COMPILE PASS**, không phải hardware pass. Firmware **chưa** nạp (flash) và
   **chưa** chạy lần nào; không có dòng log `#CG …` nào là thật.
2. Không có bài test vật lý nào **của firmware ESP-IDF** được chạy: MC-38 vẫn chưa xác
   minh polarity, 5 chu kỳ reboot vẫn `HARDWARE_RUN_PENDING`, chưa có `sensor-consistency.csv`
   của phiên mới. (BME280 có bài bench **standalone** bằng sketch Arduino — **không** phải
   firmware ESP-IDF — `acceptance.md §4.1`/`§11`; vị trí gá cuối/self-heating vẫn `PENDING_TEST`.)
3. `A-W02-04` chỉ được nâng phần **compile**; phần "một lần chạy thật để có log `#CG SAMPLE`"
   vẫn `PENDING`.
4. Lớp test hành vi vẫn là mô hình Python + kiểm tra tĩnh; compile pass **không** thay thế
   golden-run trên target (vẫn nên bổ sung trong W03+).
5. SHA-256 ở mục 3 khoá đúng artifact của run ghi ở mục 2; nếu build lại (dù cùng commit)
   thì byte có thể đổi (đường dẫn/timestamp trong ELF), khi đó phải cập nhật báo cáo —
   không được dán lại số cũ.
