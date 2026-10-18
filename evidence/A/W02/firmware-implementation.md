# W02 firmware implementation — Member A

**Phạm vi:** firmware W02 trong repo (`firmware/main/`, 7 module C) + công cụ kiểm chứng
host (`firmware/tools/`). Tệp này ghi **chính xác** cái gì đã implement, cái gì đã được
kiểm chứng tự động, và cái gì **chưa**.

**Nguyên tắc bất di bất dịch:** firmware này **không** phải nguồn của 3 ảnh bằng chứng
trong thư mục này. 3 ảnh đó do một sketch bench riêng mà **nguồn không nằm trong repo**
(`sensor-rom-map.yaml: firmware sketch bench = NOT_IN_REPO`). Firmware trong repo là bản
triển khai chính thức của W02 cho các bước chạy tiếp theo; nó **không** được dùng để suy
ngược hành vi của phiên bench cũ.

---

## 1. Bản đồ module

| File | Trách nhiệm | Ràng buộc canonical |
|---|---|---|
| `coldguard_config.h` | pin (docs/01 §11.7), chu kỳ lấy mẫu, ROM map, ngưỡng debounce, token log | một chỗ duy nhất chứa hằng số |
| `cg_rom_map.c/.h` | ROM→vai trò bằng so khớp 8 byte; tự kiểm CRC8 + trùng lặp khi boot | `PHY-DS-001/002`; §6.5 "thứ tự thư viện không phải định danh" |
| `cg_onewire.c/.h` | bit-bang 1-Wire open-drain (ESP-IDF v6 không có host driver 1-Wire; repo không dùng component registry) | bus DS18B20 trên GPIO10 |
| `cg_ds18b20.c/.h` | broadcast `SKIP_ROM`+`CONVERT_T` → đọc từng ROM; CRC8, 85.0 °C power-on, ngoài dải, mất presence ⇒ `invalid`, in `nan` | `PHY-DS-004/006`, §6.8 `VALID/DEGRADED/INVALID` |
| `cg_door.c/.h` | MC-38 GPIO34: poll 5 ms, debounce 50 ms cấu hình được, đếm cạnh thô / cạnh bỏ đi, mọi cạnh thô có mốc µs, semantic `UNVERIFIED` khi polarity chưa commissioned | docs/01 §8.2/§8.3/§8.4 |
| `cg_safety.c/.h` | ép IBT-2 PWM/EN về mức OFF **trước** mọi khởi tạo khác | docs/01 §11.8 |
| `cg_log.c/.h` | in một dòng nguyên tử (mutex) theo grammar có phiên bản | để máy parse được, không phải để người đoán |
| `app_main.c` | thứ tự boot, NVS `boot_count`, `boot_id`, 2 task (door 6, sensor 5) | `A-W02-03`, `A-W02-04`, `A-W02-07` |

## 2. Grammar log (version 1)

```text
#CG LOG v=1 fw=… hw=CG-HW-001 device=coldguard-001 pin_map=1 grammar=1
#CG SAFETY actuator=OFF pwm=5 en=6
#CG BOOT boot_id=<hex> boot_count=<n>                 ← NVS; PASS đòi boot_id phân biệt + boot_count tăng dần
#CG ROM role=T1 rom=287088CA00000051 present=1 status=ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING
#CG ROMS required_present=3/3 known=4 known_present=4
#CG DOOR_POLARITY state=UNVERIFIED raw_open_level=0
#CG DOOR_EDGE uptime_us=<µs> raw=<0|1>                ← mọi cạnh thô, kể cả dội
#CG DOOR_STATE uptime_ms=<ms> raw=<0|1> state=UNVERIFIED transitions=… cycles=… discarded=…
#CG SAMPLE uptime_ms=<ms> seq=<n> T1=… T2=… T3=… SPARE=… t1=… t2=… t3=… thermal=… door_raw=… door=…
#CG ERR msg=…
```

`nan` = **không có giá trị hợp lệ** (không bao giờ là `0.0`, không bao giờ là giá trị cũ).

- `T1`/`T2`/`T3` có cờ `t1`/`t2`/`t3`; `SPARE` **không** có cờ riêng trong grammar v1 — token `nan` chính là dấu hiệu mất giá trị của nó.
- `#CG ROMS` chỉ đếm tập ROM đã đóng băng (`known=4`); firmware **không** quét bus nên **không** có bộ đếm thiết bị lạ để in (trường `unknown=` đã bị bỏ).

## 3. Ràng buộc đã cài đặt (mỗi dòng có kiểm tra tự động)

| Ràng buộc | Cài đặt | Kiểm tra |
|---|---|---|
| Không phụ thuộc thứ tự discovery | đọc theo ROM cố định bằng `MATCH_ROM` | tĩnh: không `role = …[i]`; ROM khớp YAML từng byte |
| Một lần chuyển đổi dùng chung | `cg_ds18b20_convert_all()` + `read_probe()` | tĩnh: thân hàm đọc **không** chứa bất kỳ token/call `convert` nào (không chỉ `CONVERT_T`) |
| ~1 Hz nhưng không giả 1 Hz | vòng lặp theo `next_deadline_us`, in `uptime_ms` thật | tĩnh + test `effective_rate()` trên log mô phỏng |
| Lỗi đọc không thành 0 °C | `valid=false` ⇒ in `nan` | tĩnh + test parser/CSV (ô rỗng) |
| Không đoán polarity cửa | `CG_DOOR_POLARITY_CONFIRMED 0` ⇒ `UNVERIFIED` | tĩnh: nhánh `#if` phải map raw→`OPEN`/`CLOSED`, nhánh `#else` phải trả `UNVERIFIED` (đảo nhánh bị từ chối); test CLI: không `--open-level` ⇒ mọi dòng CSV `UNVERIFIED` + exit 1 |
| Debounce cấu hình được | `CG_DOOR_DEBOUNCE_MS=50`, cửa sổ ổn định | test mô hình debounce: dội trong cửa sổ ⇒ 1 commit |
| Debounce không xoá khoảng mở có chủ đích | 50 ms ≪ khoảng mở ~1 s | test: mở giữ 1.2 s vẫn thành 2 commit riêng |
| An toàn boot | `cg_safety_force_actuator_off()` gọi đầu tiên | tĩnh: so chỉ số vị trí gọi trong `app_main` |
| "5 reboot" phải là 5 boot thật | công cụ đòi ≥5 khối `#CG BOOT` với `boot_id` phân biệt + `boot_count` tăng dần | test: 5 khối dán lặp ⇒ `BOOT_METADATA_INVALID`; `boot_count=0` ⇒ FAIL |
| Không trộn bộ đếm cửa giữa các boot | capture cửa trải nhiều boot ⇒ từ chối; chỉ phân tích sau `--boot N` | test CLI: capture 2 boot ⇒ exit 1; `--boot 1` ⇒ chỉ lấy cửa của boot 1 |
| Không in số đo không thể đo | `#CG ROMS` bỏ `unknown=` (W02 không quét bus) | tĩnh: `unknown=` không được xuất hiện trong `cg_log.c`/`cg_ds18b20.c` |

## 4. Kết quả kiểm tra trên máy hiện tại

Lần chạy thật cuối cùng (sau commit firmware `1b93f572ed3f06a3030292b2515fa38bcaf75ca7` —
cập nhật 7: fix door-task runtime + tool reboot):

```text
py firmware/tools/run_all_checks.py
[PASS] host tools: unittest suite
[PASS] firmware: static contract checks
[PASS] evidence: W02 dossier validator

W02 CHECKS: 3/3 passed
Reminder: no check here compiles the firmware or touches hardware.
Compile check: Espressif idf docker build (see repository README).
Hardware still pending: 5-reboot ESP-IDF run, firmware consistency run, physical labeling, H0 mechanical.
```

Số lượng thật của chính lần chạy này: `Ran 57 tests … OK` (57 unittest công cụ),
`STATIC FIRMWARE CHECK: PASS (39 checks)`, và validator in `W02 STRUCTURE PASS: 14 required
files; …; 9/9 bench/flash/reboot evidence blobs verified by size + SHA-256 (mc38, ds18b20,
espidf-run); ROM map 3 roles + 1 spare + firmware_commit (W02 modules + ROM bytes); …`.
Các con số này lấy từ output thật, không sao chép từ lần chạy cũ.

Lịch sử các trạng thái công cụ (để truy vết): khi nhập BME280 (cập nhật 3) dòng
"Hardware still pending" chưa được sửa (nguyên văn cũ `BME280, physical sensor labeling, H0
mechanical`); tại cập nhật 5 dòng được sửa thành `5-reboot ESP-IDF run, firmware consistency
run, physical labeling, H0 mechanical`; sau khi 5 reboot + runtime firmware hoàn tất
(cập nhật 7), dòng này sẽ được sửa tiếp khi nhập evidence mới — nội dung dòng luôn là
**nguyên văn công cụ**, không được tự tay đổi mà không đi cùng thay đổi của công cụ.

Build ESP-IDF thật (ESP-IDF v6.1, target `esp32s3`) nay đã chạy trên GitHub Actions:
**SUCCESS** (3 run: `39117530768`, `39131281315`, `39134178842`) — chi tiết ở
`build-report-w02.md`. **Và firmware `1b93f572` giờ đã được nạp + chạy thật trên ESP32-S3**
(MAC `e0:72:a1:bc:cf:4c`): flash 3/3 region hash verified, 5 reboot identity PASS, 252 mẫu
`#CG SAMPLE` ~1 Hz — toàn bộ ở `espidf-run/` (`acceptance.md` §14).

## 5. Giới hạn đã khai báo (không giấu)

1. **Đã biên dịch thật trên CI và đã nạp + chạy thật trên board — phần nào đó vẫn là giới hạn.**
   Máy cục bộ không có ESP-IDF, không có Docker, không có trình biên dịch C; vì vậy build chạy
   trên GitHub Actions bằng đúng image README gốc (`espressif/idf:v6.1`,
   `idf.py set-target esp32s3 && idf.py build`). Kết quả: **SUCCESS** 3 run — chi tiết ở
   `build-report-w02.md`. **Cập nhật 7:** firmware `1b93f572` đã flash thật (3/3 region hash
   verified) và chạy thật (5 reboot identity PASS + 252 mẫu `#CG SAMPLE` ~1 Hz) —
   `espidf-run/`. Phần **chưa** chạy thật trên firmware: bài cửa (`#CG DOOR_EDGE`) và CSV
   consistency ≥600 mẫu.
2. ~~**Chưa nạp, chưa chạy.** Không có log `#CG SAMPLE` / `#CG DOOR_EDGE` nào là thật.~~
   **Đã cập nhật (2026-10-18):** `#CG SAMPLE`/`#CG ROM`/`#CG BOOT`/`#CG DOOR_POLARITY`,
   `#CG SAFETY` đều có log thật (`espidf-run/serial-reboot-original.log`);
   `#CG DOOR_EDGE`/`#CG DOOR_STATE` **vẫn chưa có thật** (cửa không bị thao tác trong phiên).
3. **Không cài ROM search.** Bus không được quét để phát hiện thiết bị 1-Wire lạ; identity
   vẫn an toàn (đọc theo ROM cố định) nhưng "có thiết bị thứ 5 trên bus" sẽ **không** bị
   phát hiện ở W02. Vì vậy dòng `#CG ROMS` **không** in số thiết bị lạ: trường `unknown=`
   đã bị bỏ vì con số đó không thể đo được, và một con số không đo được sẽ trông như đã đo.
   Đây là giới hạn có chủ đích, không phải bất ngờ.
4. **BME280 không thuộc firmware W02** — điều này **không đổi**: trong `firmware/main/`
   chỉ có **định nghĩa chân** theo bảng pin canonical, **không** có driver I²C. Thiết bị
   BME280 đã được xác minh phần cứng **bên ngoài firmware** bằng bài bench standalone
   (sketch Arduino/Adafruit — `evidence/A/W02/bme280/`, `acceptance.md §4.1`); firmware
   ESP-IDF **vẫn chưa** đọc BME280 và hồ sơ không được phép nói khác.
5. **Chỉ số `boot_count` phụ thuộc NVS**: nếu xoá NVS/flash thì bộ đếm về lại 1 — log
   vẫn chứng minh được danh tính ROM→vai trò qua từng boot, chỉ là số thứ tự boot không liên tục.
   Công cụ `cg_verify_reboots.py` vì thế đòi `boot_id` phân biệt + `boot_count` tăng dần:
   dán lặp một khối boot 5 lần **không** thể giả thành 5 reboot (`BOOT_METADATA_INVALID`).
6. **Test hành vi là mô hình Python + kiểm tra tĩnh — nay đã có thêm lớp compile thật.** Các
   test parser/thống kê/debounce chạy trên mô hình; ràng buộc của mã C được giữ bằng
   `cg_check_firmware.py`; lớp thứ ba — **biên dịch thật** bằng ESP-IDF v6.1 trên CI — đã
   hoàn tất (`build-report-w02.md`, SUCCESS, 0 cảnh báo). Cái còn thiếu là **golden-run trên
   target** (chạy trên board thật); nên bổ sung trong W03+ để thay thế dần hai lớp mô hình.

## 6. Bài học từ lần chạy thật đầu tiên (bug runtime, đã fix)

Lần flash đầu (firmware `2a5a0da`, artifact run `39131281315`) cho thấy **bug thật** mô hình
test không phát hiện được:

- Hiện tượng: board boot, in `#CG BOOT`, nhưng **0 dòng `#CG ROM`/`#CG SAMPLE`**; task
  watchdog dội liên tục (IDLE0 starved) trong 205 s.
- Nguyên nhân: `app_main.c` `door_task` gọi `vTaskDelay(pdMS_TO_TICKS(CG_DOOR_POLL_MS))`
  với `CG_DOOR_POLL_MS=5` và `CONFIG_FREERTOS_HZ=100` ⇒ `pdMS_TO_TICKS(5)==0`;
  `vTaskDelay(0)` chỉ yield cho task cùng ưu tiên ⇒ task prio-6 quay vô hạn, IDLE0 và
  `cg_sensor` (prio 5) không bao giờ chạy.
- Fix (commit `1b93f572ed3f06a3030292b2515fa38bcaf75ca7`): ghim tối thiểu 1 tick
  (`wait_ticks > 0 ? wait_ticks : 1`) — cùng kiểu bảo vệ `sensor_task` đã có sẵn.
  Debounce không thay đổi (đo bằng `esp_timer` µs); độ phân giải polling nới lên 1 tick
  (10 ms) — không ảnh hưởng đường viền chính xác của bài cửa.
- Bài học ghi vào wishlist W03+: thêm golden-run ngắn trên target vào lớp kiểm sau build
  (đã có một lần — run thực tế phát hiện bug mà 57 test mô hình + 39 kiểm tra tĩnh +
  compile PASS đều không thấy, vì error chỉ xuất hiện ở scheduling thật).

## 7. Bước chạy thật còn lại

Xem `bench-procedure-w02.md` — danh sách ngắn, có lệnh cụ thể cho từng bước và file bằng
chứng phải sinh ra. (B0/B1 đã xong — cập nhật 7; bài cửa B3 và dán nhãn B4 còn lại.)
