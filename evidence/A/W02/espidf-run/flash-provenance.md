# ESP32-S3 real flash — provenance (A-W02-04 / A-W02-03)

Ngày: **2026-10-18** (UTC 14:0x–14:4x). Toàn bộ thao tác nạp/thu đều chạy trên máy
workstation bench do người vận hành chính điều khiển; bản ghi này chỉ viết số liệu đã
xác minh bằng công cụ, không có suy đoán.

## 1. MCU đã xác minh

| Mục | Giá trị | Nguồn xác minh |
|---|---|---|
| Chip | **ESP32-S3 (QFN56) revision v0.2**, 240 MHz, crystal 40 MHz | `esptool chip-id` trước khi flash |
| USB | **native USB-Serial/JTAG** (VID 303A:PID 1001) | `esptool chip-id` + Win32_PnPEntity |
| MAC | `e0:72:a1:bc:cf:4c` — khớp instance USB composite `USB\VID_303A&PID_1001\E0-72-A1-BC-CF-4C`, đúng là MCU bench chính, không phải board khác | `esptool chip-id` + Win32_PnPEntity |
| Cổng | COM4 (`USB Serial Device`) — không có tiến trình nào giữ cổng | `Get-CimInstance Win32_SerialPort` + `Get-Process` |
| Flash | **4 MB thực** (esptool: `Detected flash size: 4MB`) | `esptool flash-id` |
| Layout | `2MB` (dio/80m) do chính `flasher_args.json` của build khai báo — nằm gọn trong 4 MB; **không tự đổi** để không lệch hồ sơ build đã ghi trong `build-report-w02.md` | `flasher_args.json` |

> Ghi chú SPI flash từ log boot: `W (234) spi_flash: Detected size(4096k) larger than the
> size in the binary image header(2048k). Using the size in the binary image header.` —
> firmware tự ghi đúng layout 2 MB như build; firmware chạy bình thường.

## 2. Firmware ở lần nạp này — artifact từ CI

* Run: `39134178842` của workflow *A-W02 ESP-IDF build (esp32s3)* — completed **SUCCESS**,
  head PR `1b93f572ed3f06a3030292b2515fa38bcaf75ca7` (main+PR merge preview).
* Artifact: `a-w02-espidf-build-report`, id `12139526656`, 2 021 252 byte, tạo 14:06Z.
* `environment.txt` ghi `source_commit=44f4643dfb4d04fa34333692c42008678f56ace3` =
  merge commit ephemeral của PR #8 (parents `bd76ed9` + `1b93f572`).
  `git diff --name-only 44f4643… 1b93f572…` **rỗng** — tree hoàn toàn giống nhau, không có
  nào trong main chạm `firmware/main/` ⇔ firmware trong artifact **chính là firmware của
  `1b93f572`** (commit fix door-task runtime spin).
* Container build: `espressif/idf:v6.1`; `idf.py --version` = ESP-IDF v6.1.

### SHA-256 artifact (khớp 100% với `30-artifacts.txt` in ra trong job — 3/3)

| File | Size (byte) | SHA-256 |
|---|---|---|
| `bootloader.bin` | 21 120 | `e393a32204ad9a2dede0c4789d71e9a3ee48ca837be0a674a9eec83c5601c669` |
| `coldguard_firmware.bin` | 201 568 | `9a8f662c9589b62705f361cd9dde12880a3a51a721cfdb260ac46f31d0ae6c60` |
| `partition-table.bin` | 3 072 | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| `flasher_args.json` | 927 | `e145340bd24e90bc2881eb0debbf65c80d3c25048aa194239576d2981edceb9f` |

`ELF file SHA256` do bootloader in lúc boot: `1a47211f4…` — khớp toàn chuỗi
`1a47211f41e0cdb46b28da550ef94557d7aa9c0c91f40c8bf15c7351e44a8252` tính lại từ
`coldguard_firmware.elf` trong artifact ⇒ **rảnh khả thi nhầm artifact**.
`app_init: Compile time: Oct 18 2026 14:06:19` = giờ build artifact.

Trước đó (cùng phiên) firmware `a8f5c58` (run `39131281315`, firmware SHA
`3520e10a0d81c0d7fdbcf0d70ab63255871196b00df4ce97f7dace1c97003bd7`) cũng đã được flash
thật và cho thấy lỗi runtime (task `cg_door` chiếm CPU vì `vTaskDelay(0)` — xem §5);
firmware bị thay bằng `1b93f572` sau khi fix; kết quả A-W02-03/04 bên dưới chỉ dựa vào
firmware `1b93f572`.

## 3. Thao tác flash thật

```text
py -m esptool --chip esp32s3 --port COM4 --baud 460800 --before default-reset --after hard-reset
  write-flash --flash-mode dio --flash-size 2MB --flash-freq 80m
  0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 coldguard_firmware.bin
```

* Ghi đúng 3 offset theo `flasher_args.json` của build (`0x0` / `0x8000` / `0x10000`).
* **Không** `erase-all`; không flash board thứ hai; không cấp nguồn TEC/IBT-2.
* Kết quả: 3/3 region `Hash of data verified`; `Hard resetting via RTS pin...` — firmware
  mới boot ngay sau lệnh (log: `flash-original-log.txt`, SHA-256
  `8cfaf7a3b67d018020641d739770ad38b71c248b1100263d88a64754759ed351`, 4 180 byte).

### Backup / rollback

* Trước lần flash đầu tiên của phiên: sao lưu **đủ chip 4 MB** bằng `esptool read-flash
  0x0 0x400000` (20.7 s, 1 617.7 kbit/s):
  * File: `C:\Users\dlbac\Downloads\ColdGuard_W02_Backups\esp32s3_full_flash_backup_20261018_pre_w02.bin`
  * 4 194 304 byte, SHA-256 `cee6d3f7944ca5bc04bea2353f181e73d1a0b2425d14c3edf07741c36d44ab42`
  * Chuỗi bên trong file là firmware **sketch Arduino standalone** (bench DS18B20 620 mẫu)
    trước khi nạp firmware ESP-IDF; khôi phục:
    `py -m esptool --chip esp32s3 --port COM4 --baud 460800 --before default-reset --after hard-reset write-flash 0x0 <backup>`
  * Nguồn sketch cũng còn nguyên: `ColdGuard_W02_DS18B20_620_Samples\coldguard_w02_ds18b20_620\coldguard_w02_ds18b20_620.ino`.

## 4. An toàn đã kiểm trước flash (theo yêu cầu hồ sơ)

1. ZIP bench 620 mẫu đã lưu (`W02_DS18B20_20261018_194041.zip`) và **không có capture đang
   chạy** (không tiến trình Python giữ COM4).
2. COM4 = đúng MCU chính (MAC khớp instance USB), board không còn chương trình nào cần
   kết quả cuối (bench sketch đã hoàn thành nhiệm vụ và thu đủ dữ liệu).
3. Đã có phương án rollback đầy đủ ở trên.
4. Người vận hành đã **xác nhận một lần** trước khi ghi đè firmware.

## 5. Lỗi runtime tìm thấy ở lần flash đầu (firmware `a8f5c58`) — ghi lại trung thực

* Khối `#CG BOOT` in đúng, nhưng **0 dòng `#CG ROM`/`#CG SAMPLE`** và **task watchdog
  IDLE0 dội liên tục** trong 205 s.
* Nguyên nhân (đã xác minh trong source): `firmware/main/app_main.c` vòng lặp `door_task`
  gọi `vTaskDelay(pdMS_TO_TICKS(CG_DOOR_POLL_MS))` với `CG_DOOR_POLL_MS=5` và
  `CONFIG_FREERTOS_HZ=100` ⇒ `pdMS_TO_TICKS(5)==0` ⇒ `vTaskDelay(0)` chỉ yield cho task
  cùng ưu tiên ⇔ task `cg_door` (prio 6) quay vô hạn; IDLE0 + `cg_sensor` (prio 5) chết đói.
* Fix tối thiểu ở commit `1b93f572`: ghim 1 tick tối thiểu như chính `sensor_task` đã làm
  (`wait_ticks > 0 ? wait_ticks : 1`). Điều này **không thay đổi** logic debounce (đo bằng
  `esp_timer` microsecond), chỉ nới độ phân giải polling lên 1 tick (10 ms @ 100 Hz).
* Trạng thái cũ của bộ đếm ghi nhận: sau lần flash đầu (sketch vẫn trước đó) log có
  `#CG BOOT boot_count=2` ⇒ NVS phân biệt boot thật.
