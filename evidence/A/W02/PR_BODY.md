# [A-W02] Sensor foundation: firmware ESP-IDF, pin map v2, công cụ kiểm chứng và bằng chứng bench

> **Ghi chú 2026-10-28 — pin map v2.** PR này chuyển firmware sang map v2
> (`evidence/A/as-built-pinmap-2026-10-27.md`): DS18B20=GPIO33, BME SDA/SCL=21/34,
> MC-38=GPIO35, RS-485 36/37 (AUTO), IBT-2 RPWM/R_EN/L_EN=5/6/10; thêm validator
> quyền sở hữu GPIO (`firmware/tools/cg_gpio_map.py`) và safe-OFF 3 chân. Các số
> `GPIO10/33/34` trong mô tả bench bên dưới là bản ghi lịch sử của sketch Arduino,
> không phải map firmware hiện tại.

**Tóm tắt:** PR thêm firmware W02 (7 module C), công cụ kiểm chứng host, và bộ chứng
cứ bench cho DS18B20/MC-38/BME280. Firmware **đã biên dịch thật trên CI** (ESP-IDF v6.1,
`esp32s3`, 0 cảnh báo) và **đã nạp + chạy thật** trên board ESP32-S3: **6 boot identity
ổn định** (NVS `boot_count` 5→10, ROM→role không đổi) và **252 mẫu `#CG SAMPLE` ~1 Hz**
(mean interval 999.756 ms). Phần còn lại là dữ liệu cần chạy thêm bài vật lý: bài cửa
bằng firmware + `door-test.csv`, CSV consistency ≥600 mẫu từ firmware, dán nhãn đầu dò,
tích hợp BME280 vào ESP-IDF, H0, `hardware_config_id`; sketch bench sinh 3 ảnh cũ vẫn
`NOT_IN_REPO`. Chi tiết trạng thái theo hạng mục: `evidence/A/W02/acceptance.md`.

**Base:** `main` · **Head:** `feat/a-w02-sensor-foundation` · **Loại:** NORMAL PR
**Issue/pack:** `A-W02-01` … `A-W02-07`
**Parent docs:** `docs/04 §17` (W02), `docs/05A §11` (Member A W02), `docs/03 §14–§15` (`HW-H0-01/02`, `SEN-H1-01…05`), `docs/01 §6.4–§6.6` (identity contract)
**Review gợi ý (không phải cổng phê duyệt):** Member D — physical wiring / pin / sensing (`docs/04 §3.3`); phạm vi gợi ý ở §8.
**Hardware config affected?:** Chưa — `hardware_config_id` vẫn `NOT_ASSIGNED`. PR ghi nhận danh tính cảm biến, không thay đổi BOM freeze.
**Evidence path:** `evidence/A/W02/`
**Firmware commit:** `1b93f572ed3f06a3030292b2515fa38bcaf75ca7` (fix door-task runtime spin; trước đó `2a5a0dac…`) — CI SUCCESS (run 39134178842), đã flash lên board MAC `e0:72:a1:bc:cf:4c`.

---

## 1. Thay đổi chính trong PR

- **Firmware W02 mới** (`firmware/main/`, 7 module C): đọc DS18B20 theo ROM cố định
  (không phụ thuộc thứ tự discovery), một lần chuyển đổi dùng chung cho cả bus, vòng lặp
  ~1 Hz theo deadline với `uptime_ms` thật, `nan` khi đọc lỗi/mất đầu dò, MC-38 debounce
  cấu hình được + không đoán polarity, NVS `boot_count` + khối `#CG ROM` mỗi boot, và ép
  IBT-2 OFF ngay đầu `app_main`. Chi tiết: `firmware-implementation.md`.
- **ROM → vai trò DS18B20** (`sensor-rom-map.yaml` + `coldguard_config.h`): T1 gần cửa
  `287088CA00000051`, T2 trung tâm `28AEBF2200000006`, T3 đối diện cửa
  `28CBE9CA00000072`, dự phòng `283BE5C9000000A9`; ROM ghi cứng trong firmware, đối chiếu
  tự động từng byte + CRC8. Trạng thái `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` — đầu dò
  vật lý **chưa** được dán nhãn.
- **Map chân v2** trong `coldguard_config.h` + validator quyền sở hữu GPIO
  (`firmware/tools/cg_gpio_map.py`, test kèm theo) + safe-OFF 3 chân (RPWM/R_EN/L_EN LOW).
- **Công cụ kiểm chứng host** (`firmware/tools/`): parser log, xác minh reboot identity,
  dựng `sensor-consistency.csv`, dựng `door-test.csv` (bắt buộc `--open-level`), kiểm tra
  tĩnh firmware, gộp bằng `run_all_checks.py`. **74 test `unittest` + 42 kiểm tra tĩnh PASS.**
- **Bộ chứng cứ bench** (`bme280/`, `mc38/`, `ds18b20/`): log gốc + CSV dẫn xuất + báo cáo
  + SHA-256, mỗi blob được `validate_w02.py` ghim lại.
- **Bộ chứng cứ firmware chạy thật** (`espidf-run/`): provenance flash, log serial 6 boot,
  verifier reboot, thống kê cadence.
- **Hồ sơ**: `acceptance.md` (nguồn trạng thái duy nhất), `README.md`,
  `bench-procedure-w02.md`, `screenshot-provenance.csv`, `validate_w02.py`, `PR_BODY.md`.

## 2. Kết quả kiểm chứng

| Lớp | Kết quả | Bằng chứng |
|---|---|---|
| Build ESP-IDF (CI) | **SUCCESS** — image `espressif/idf:v6.1`, target `esp32s3`, 0 cảnh báo, `coldguard_firmware.bin` = 0x31360 bytes | `build-report-w02.md`; run 39134178842 |
| Flash thật | **PASS** — 3/3 region `Hash of data verified`; ELF SHA-256 khớp artifact; backup rollback 4 MB | `espidf-run/flash-provenance.md`, `espidf-run/flash-original-log.txt` |
| Reboot identity | **PASS** — 6 boot (5 reset host-driven + 1 context), `boot_id` phân biệt, NVS `boot_count` 5→10, ROM→role ổn định 6/6 (gồm SPARE) | `espidf-run/reboot-verification-report.txt` + `.json` |
| Runtime ~1 Hz | **ĐO ĐƯỢC** — 252 mẫu `#CG SAMPLE`, 246 interval trong [990, 1000] ms (mean 999.756), VALID 252/252, 0 `#CG ERR`/`nan` | `espidf-run/runtime-cadence.md` |
| Tooling + static | **3/3 PASS** — 74 test + 42 check tĩnh + `validate_w02.py` | `run_all_checks.py` output |
| Native build (ESP-IDF v6.1, working tree map v2) | **PASS** — 1085/1085 bước Ninja, 0 cảnh báo, 0 lỗi; binary `47cf3bb6…` **thuộc dirty-tree build, không thuộc commit** | `firmware-implementation.md` §8 |
| Bench BME280 | **PASS** — 403/403 mẫu, chip-ID `0x60`, I²C `0x76`, T/RH/P hợp lý | `bme280/` |
| Bench MC-38 | **PASS** — 48 cặp RAW/STABLE, +40 ms, 24 chu kỳ, polarity có dấu trong log | `mc38/` |
| Bench DS18B20 | **PASS** — 620/620 mẫu × 4 vai trò, 619 s đều 1000 ms, thống kê tái lập | `ds18b20/` |

**Lỗi thật đã gặp và đã xử lý (không giấu):**
- CI run đầu `39117011427` **FAIL** — `driver/gpio.h: No such file or directory`; nguyên
  nhân thiếu `esp_driver_gpio` trong `PRIV_REQUIRES`; đã sửa trong `CMakeLists.txt`
  (commit `2a5a0dac…`) và build lại SUCCESS.
- Flash đầu với firmware `a8f5c58`: board boot nhưng **0 dòng `#CG ROM`/`#CG SAMPLE`**,
  IDLE0 watchdog dội liên tục — `vTaskDelay(pdMS_TO_TICKS(5)) == 0` khi
  `CONFIG_FREERTOS_HZ=100` làm door task quay vô hạn. Fix tối thiểu commit `1b93f572`
  (1 tick tối thiểu), build lại CI rồi flash lại — chạy đúng. Ghi ở
  `firmware-implementation.md` §6, `acceptance.md` §14.

## 3. Bằng chứng bench (rút gọn)

- **BME280** (`bme280/`): log gốc 13 795 bytes SHA-256 `da24b6f0…6c23`, CSV 403 mẫu
  `valid=1` toàn bộ, `uptime_ms` 2 816→404 816; T 30.27–30.42 °C, RH 68.42–69.14 %RH,
  P 1011.97–1012.16 hPa; thống kê tính lại từ log, CSV khớp từng dòng. Bài bench
  **standalone** (sketch Arduino/Adafruit) — **không** phải firmware ESP-IDF.
- **MC-38** (`mc38/`): log gốc 2 401 bytes SHA-256 `38cdeef5…f4595`, 48 cặp `RAW/STABLE`,
  mỗi `STABLE` đúng +40 ms, bộ đếm 1..48 không thiếu/nhảy, 24 chu kỳ; dòng chú thích vật
  lý `# PHYSICAL=NEAR/FAR` ⇒ `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` (48/48). Firmware vẫn giữ
  `CG_DOOR_POLARITY_CONFIRMED=0` cho tới khi chạy bài cửa bằng firmware.
- **DS18B20** (`ds18b20/`): log gốc 32 190 bytes SHA-256 `44228795…b91c`, 620 mẫu liên
  tục, 619 khoảng đều 1000 ms, 4 vai trò 620/620 valid, 0 sentinel; chênh lệch cặp lớn
  nhất 0.6196 °C (T2–T3), chênh lệch tức thời lớn nhất 0.6875 °C. Raw log chứa **0 dòng
  ROM** — cảnh báo `ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG` được giữ nguyên; same-boot
  ROM được xác minh bằng bài 6 boot firmware (§2), không đo lại phiên 10 phút.
- 3 ảnh log cũ (archive `ColdGuard_A_W02_Existing_Test_Screenshots.zip`, 81 661 bytes,
  SHA-256 `383CBB4A…B97429`) được sao chép nguyên byte; ảnh chỉ chứng minh **kết quả được
  hiển thị**, không thay thế CSV/log thô. Sketch bench sinh 3 ảnh: `NOT_IN_REPO`.

## 4. H0 mechanical (A-W02-01) — đề xuất hoãn, cần ghi bằng văn bản

- **Trạng thái:** `NOT IMPLEMENTED` — `DEFERRED` (đề xuất dời sang giai đoạn cơ khí/W07).
- **Lý do:** test các module trên bàn trước để lỗi dễ phát hiện và linh kiện dễ thay thế
  hơn so với khi đã lắp kín trong thùng.
- **Các điểm phải ghi rõ:** (1) canonical W02 vẫn yêu cầu H0 — đây là **đề xuất**;
  (2) W07 geometry freeze **không** tự động thay thế H0 của W02; (3) điều chỉnh lịch cần
  được ghi bằng văn bản trước khi trạng thái `A-W02-01` thay đổi; (4) ảnh hưởng tới W04:
  nếu H0 chưa xong, W04 chỉ chạy được phần logic/điện và **không** tạo được bằng chứng
  nhiệt có ý nghĩa — Gate G1 (`docs/04 §19`) có nguy cơ không đạt trong W03–W04 như lịch
  hiện tại.
- PR **không** sửa lịch canonical và **không** đánh dấu H0 hoàn tất.

## 5. Phần còn lại (ngắn, theo hạng mục)

| Hạng mục | Trạng thái | Việc còn lại |
|---|---|---|
| `A-W02-01` H0 | `NOT IMPLEMENTED` — `DEFERRED` | Ảnh/checklist H0; phạm vi H0 ghi bằng văn bản |
| `A-W02-02` nhãn vật lý | `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` | Dán nhãn T1/T2/T3 (+ SPARE), ảnh nhãn |
| `A-W02-03` reboot identity | **`DONE` — HARDWARE VERIFIED** | — |
| `A-W02-04` acquisition | **`DONE`** cho phần runtime; `PARTIAL` cho consistency window | CSV ≥600 mẫu từ firmware; nguồn sketch bench `NOT_IN_REPO` |
| `A-W02-05` consistency | `BENCH DATA VERIFIED` (620 mẫu sketch); same-boot ROM resolved | Phiên ≥600 mẫu bằng firmware + `cg_build_sensor_csv.py`; ảnh setup |
| `A-W02-06` BME280 | `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED` | Tích hợp ESP-IDF (hoặc ghi phạm vi bằng văn bản); vị trí gá cuối + xác nhận không bị sấy nóng (`PENDING_TEST`) |
| `A-W02-07` MC-38 | `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED` | Bài cửa bằng firmware (`#CG DOOR_EDGE`) + `door-test.csv`; freeze `CG_DOOR_POLARITY_CONFIRMED` |
| Lệch số lượng đầu dò 4 vs 3 | Chưa có văn bản | Ghi nhận bằng văn bản (kế thừa `CR-A-W01-04`) |
| `hardware_config_id`, ngày review | Chưa gán | Gán khi chốt cấu hình |

Chi tiết bằng chứng/giới hạn của từng hạng mục nằm trong `acceptance.md` (§1, §4.1, §4.2,
§5) — PR body này không lặp lại toàn bộ.

## 6. Lệnh kiểm chứng cục bộ

```
py firmware/tools/run_all_checks.py     # 74 test + 42 static + validate_w02.py
py validate_w02.py                      # trong evidence/A/W02
py firmware/tools/cg_check_firmware.py  # ROM map ↔ coldguard_config.h, CRC8
```

`validate_w02.py` kiểm tra: 14 file bắt buộc, provenance ảnh (kích thước + SHA-256),
`firmware_commit` chứa đủ 5 module W02 + ROM bytes khớp `coldguard_config.h`, 9 blob
bench/flash/reboot ghim hash, và sự hiện diện của nhãn trạng thái trung thực trong
`acceptance.md`. Script **không** xác nhận sự thật vật lý nào.

## 7. Ghi chú tích hợp

- **PR không tự merge**, không đổi lịch canonical, không sửa `docs/00`–`docs/05A`.
- Firmware W02 **không** có driver BME280 (cố ý) — tích hợp là task riêng.
- Không có ROM search: thiết bị 1-Wire lạ không bị phát hiện; identity vẫn an toàn vì đọc
  theo ROM cố định.
- Phạm vi phiên firmware đã chạy: reboot identity + cadence. **Chưa** có bài cửa bằng
  firmware và **chưa** có CSV consistency ≥600 mẫu từ firmware.
- Ngoài phạm vi: cấp nguồn TEC, tải dòng lớn, thay đổi BOM freeze.

## 8. Gợi ý phạm vi review kỹ thuật (không phải cổng phê duyệt)

1. Cách đọc số liệu consistency: 0.603 °C (phiên 600 mẫu cũ) / 0.6196 °C (phiên 620 mẫu)
   chênh lệch trung bình lớn nhất **không** được diễn giải thành sai số cảm biến; không có
   ngưỡng số nào được tự đặt.
2. Vì sao `MC38 initial: HIGH` **không** đủ để freeze polarity.
3. Chân GPIO theo map v2 (`evidence/A/as-built-pinmap-2026-10-27.md`), thứ tự reset 1-Wire
   (≈480/70/410 µs), 12-bit + 750 ms, debounce `CG_DOOR_DEBOUNCE_MS=50`, logic
   `VALID/DEGRADED/INVALID`.
4. Tác động của việc hoãn H0 lên W04 và Gate G1 (phần nhiệt).
5. Xác nhận PR **không** tuyên bố trạng thái an toàn điện nào (không cấp nguồn TEC, không
   chạm dải dòng lớn).
6. Firmware đã được nạp/chạy cho phạm vi §2 — review này vẫn là review mã nguồn + kết quả
   đo đã nêu, không phải nghiệm thu toàn bộ W02.
