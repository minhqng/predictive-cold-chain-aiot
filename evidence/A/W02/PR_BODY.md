# [A-W02] Sensor Foundation, ROM Mapping and Bench Evidence

> **⚠️ W02 NOT PASS — READ FIRST.** Bộ chứng cứ này là `W02_PARTIAL_EVIDENCE`, **không** phải nghiệm thu W02. Mở PR này **không** đồng nghĩa W02 đã PASS. Bốn lần cập nhật gần nhất: (1) **bằng chứng bench BME280 thật** (ESP32-S3, sketch Arduino/Adafruit, `BME280_INIT=PASS`, chip-ID `0x60`, I²C `0x76`, 403/403 mẫu hợp lệ — `evidence/A/W02/bme280/`): `A-W02-06` → **BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED**; (2) **dữ liệu bench thô MC-38 thật** (log 48 cặp `RAW/STABLE`, GPIO34, debounce 40 ms, 24 chu kỳ, polarity **NEAR=LOW=CLOSED / FAR=HIGH=OPEN** có dấu trong log — `evidence/A/W02/mc38/`): `A-W02-07` → **BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED**; (3) **dữ liệu bench thô DS18B20 620 mẫu thật** (620/620 mẫu hợp lệ × 4 vai trò, 619 s đều 1000 ms, thống kê tái lập từ log, `evidence/A/W02/ds18b20/`): `A-W02-05` → **BENCH DATA VERIFIED — 620 RAW SAMPLES CAPTURED**; và **(4) cập nhật 7 — firmware ESP-IDF đã nạp thật + chạy thật trên board** (`evidence/A/W02/espidf-run/`): flash 3/3 region hash verified, **5 reboot identity PASS** (6 boots thật, `boot_id` phân biệt, NVS `boot_count` 5→10 tăng liên tục, ROM→role ổn định 6/6 gồm cả SPARE — `A-W02-03` → **HARDWARE VERIFIED**), runtime **252 mẫu `#CG SAMPLE` ~1 Hz đo được** (interval mean 999.756 ms, VALID 252/252 — `A-W02-04` → **HARDWARE RUNTIME VERIFIED**). Trong phiên flash đầu thấy được **bug runtime thật** (`vTaskDelay(0)` của door task ở tick 100 Hz — qua fix `1b93f572`). Hạng mục còn treo chính: `A-W02-01` H0 mechanical (`DEFERRED`, chờ trưởng nhóm quyết định lịch), bài cửa firmware `#CG DOOR_EDGE` + `door-test.csv` (`A-W02-07`), CSV consistency ≥600 mẫu từ firmware, dán nhãn vật lý.

**Base:** `main` · **Head:** `feat/a-w02-sensor-foundation` · **Loại:** NORMAL PR (Ready for Review — không phải Draft)
**Issue/pack:** `A-W02-01` … `A-W02-07`
**Parent docs:** `docs/04 §17` (W02), `docs/05A §11` (Member A W02), `docs/03 §14–§15` (`HW-H0-01/02`, `SEN-H1-01…05`), `docs/01 §6.4–§6.6` (identity contract)
**Reviewer bắt buộc:** Member D (`docs/04 §3.3`: physical wiring / pin / sensing)
**Hardware config affected?:** Chưa — `hardware_config_id` vẫn `NOT_ASSIGNED`. PR này ghi nhận danh tính cảm biến, không thay đổi BOM freeze.
**Evidence path:** `evidence/A/W02/`
**Trạng thái W02:** **`W02_PARTIAL_EVIDENCE` — KHÔNG phải W02 PASS.** Firmware W02 trong repo: `1b93f572ed3f06a3030292b2515fa38bcaf75ca7` (fix door-task runtime spin; trước đó `2a5a0dac…`) — **đã biên dịch thật trên CI** (3 run SUCCESS, mới nhất run 39134178842; chi tiết `build-report-w02.md`), **đã nạp thật và đã chạy thật trên board ESP32-S3** (MAC `e0:72:a1:bc:cf:4c`; 5 reboot identity PASS + 252 mẫu ~1 Hz — `espidf-run/`, §9.1).

---

## 1. Member A đã hoàn thành những gì

- **Bản đồ ROM → vai trò DS18B20** (`sensor-rom-map.yaml`): T1 gần cửa `287088CA00000051`, T2 trung tâm `28AEBF2200000006`, T3 đối diện cửa `28CBE9CA00000072`, và một đầu dò dự phòng `283BE5C9000000A9`. Trạng thái ghi đúng là `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` — **đầu dò vật lý chưa được dán nhãn**, không tự nhận là đã xong. Bản đồ này nay **đã được ghi cứng vào firmware** và được đối chiếu tự động từng byte + CRC8.
- **Firmware W02 trong repo** (`firmware/main/`, 7 module C): đọc DS18B20 theo ROM cố định (không phụ thuộc thứ tự discovery), một lần chuyển đổi dùng chung cho cả bus, vòng lặp ~1 Hz theo deadline với `uptime_ms` là thời điểm thật, `nan` khi đọc lỗi/mất đầu dò, MC-38 debounce cấu hình được + không đoán polarity, NVS `boot_count` + khối `#CG ROM` mỗi lần boot, và ép IBT-2 OFF ngay đầu `app_main`; nay **đã được biên dịch thật** trên GitHub Actions (ESP-IDF v6.1, `esp32s3`, SUCCESS, 0 cảnh báo — `build-report-w02.md`). Chi tiết: `firmware-implementation.md`.
- **Bằng chứng bench BME280** (`bme280/`): log Serial Monitor gốc (SHA-256 `da24b6f0…6c23`) + CSV 403 mẫu liên tục 1–403, `valid=1` toàn bộ, `uptime_ms` 2 816→404 816 (402 khoảng × 1000 ms) + báo cáo; T 30.27–30.42 °C, RH 68.42–69.14 %RH, P 1011.97–1012.16 hPa — thống kê đã tính lại độc lập từ log, CSV khớp từng dòng; **không** phải firmware ESP-IDF (bài bench standalone).
- **Dữ liệu bench thô MC-38** (`mc38/`): log bench gốc 2 401 bytes (SHA-256 `38cdeef5…f4595`, giữ nguyên CRLF) với **48 cặp** `RAW/STABLE` (GPIO34, `DEBOUNCE_MS=40`, tổng 508 s, mốc ms từ boot) + CSV dẫn xuất (48 dòng, khớp từng dòng với log) + báo cáo. Xác minh máy móc: 48/48 cặp đúng +40 ms, bộ đếm `raw_edges`/`stable_edges` luỹ tiến 1..48 không thiếu/nhảy, chuyển mức xen kẽ đều, **24 chu kỳ NEAR→FAR**, và polarity **có dấu trong log** (`# PHYSICAL=NEAR raw=0 stable=0` / `# PHYSICAL=FAR raw=1 stable=1` ⇒ `NEAR=LOW=CLOSED / FAR=HIGH=OPEN`, khớp 48/48). Firmware vẫn giữ `CG_DOOR_POLARITY_CONFIRMED=0` — cờ chỉ đóng sau khi firmware ESP-IDF chạy thật.
- **Dữ liệu bench thô DS18B20 620 mẫu** (`ds18b20/`): log Serial Monitor gốc 32 190 bytes (SHA-256 `44228795…b91c`, giữ nguyên CRLF) với **620 mẫu liên tục 1–620**, 0 trùng/0 thiếu; `uptime_ms` 42 014→661 014 ⇒ **619 000 ms, 619 khoảng đều 1000 ms**; **4 vai trò 620/620 hợp lệ** (2 480/2 480 cờ), 0 giá trị sentinel; CSV 620 dòng khớp log từng dòng; thống kê tính lại từ log: T1 29.878528 (sd 0.021467), T2 30.187903 (0.016275), T3 29.568347 (0.023374), SPARE 29.921774 (0.028058); chênh lệch trung bình cặp lớn nhất **0.6196 °C (T2–T3)**, chênh lệch tức thời lớn nhất 0.6875 °C. Bài bench là **sketch Arduino standalone** — schema `sample,uptime_ms,…`, **không** phải `#CG SAMPLE` của firmware ⇒ không được dùng để tuyên bố A-W02-04. **Giới hạn ROM:** raw log chứa **0 dòng ROM** — cảnh báo `ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG` được **giữ nguyên**; ROM được xác nhận bằng bằng chứng độc lập phiên khác (`w02_rom_enumeration_4_devices.png`, cả 4 `PRESENT=1`, khớp `coldguard_config.h` từng byte + CRC8) và phần **cùng một boot** sẽ được xác minh trong bài 5 reboot firmware ESP-IDF (`A-W02-03`) — **không chèn dòng ROM, không yêu cầu đo lại 10 phút**.
- **Công cụ kiểm chứng host** (`firmware/tools/`): parser log, xác minh reboot identity, dựng `sensor-consistency.csv`, dựng `door-test.csv` (bắt buộc `--open-level` do người vận hành quan sát), kiểm tra tĩnh firmware, và một lệnh gộp `run_all_checks.py`. 57 test `unittest` + 39 kiểm tra tĩnh đều PASS trên máy hiện tại.
- **Tổng hợp inter-sensor consistency** (`sensor-consistency-summary.md`): bảng 600 mẫu/đầu dò, chênh lệch trung bình từng cặp và chênh lệch lớn nhất (0.603 °C, DS2 vs DS3), kèm phân tích vì sao các SD (0.018–0.031 °C) thấp hơn một bước lượng tử 12-bit. Ghi rõ đây là **consistency check, KHÔNG phải calibration**.
- **Tổng hợp bài test cửa MC-38** (`door-test-summary.md`): đọc bộ đếm thô, kiểm tra số học `cycles = floor(transitions/2)`, và đối chiếu tiêu chí ≥20 chu kỳ (đạt 24).
- **Hồ sơ truy xuất nguồn ảnh** (`screenshot-provenance.csv`) + **kiểm tra cấu trúc tự động** (`validate_w02.py`) + **acceptance matrix A-W02-01…07** (`acceptance.md`) + `README.md` + **quy trình bench còn thiếu** (`bench-procedure-w02.md`).

## 2. Bằng chứng thật tương ứng

Ba ảnh log gốc của phiên bench W02, do người dùng cung cấp qua archive `ColdGuard_A_W02_Existing_Test_Screenshots.zip` (81 661 bytes, SHA-256 `383CBB4A…B97429`), được sao chép **nguyên byte** (không crop, không nén lại, không chỉnh sửa):

| Ảnh | Nội dung thật | Ý nghĩa |
|---|---|---|
| `w02_rom_enumeration_4_devices.png` | COM4 Serial Monitor: `DS18B20 found: 4`, 4 ROM hex, `MC38 initial: HIGH`, `PASS: 4 DS18B20 detected`, các khối nhiệt độ `DS1..DS4` với `Valid: 4/4` | 4 ROM phân biệt, cả 4 đọc được giá trị trong cùng phiên |
| `w02_ds18b20_600_samples_summary.png` | 9 dòng CSV cuối (592–600) + `# W02 SUMMARY`: `valid=600/600` và `mean/sd/min/max` cho S1–S4 + `# W02 TEST FINISHED` | Kết quả summary **được hiển thị** cho 600 mẫu/đầu dò |
| `w02_mc38_24_cycles.png` | 6 dòng `MC38: LOW/HIGH \| transitions: 43..48 \| cycles: 21..24`, xen kẽ khối nhiệt độ | Bộ đếm chuyển mức đạt **24 chu kỳ** trong phiên bench |

Số liệu chi tiết (mean 29.882/30.214/29.611/29.935 °C; sd 0.028/0.031/0.026/0.018 °C) được ghi nguyên văn và tính lại công khai trong `sensor-consistency-summary.md`.

**Ảnh xác nhận kết quả đã được hiển thị — ảnh KHÔNG thay thế CSV 600 dòng, KHÔNG thay thế timestamp thật, và ảnh MC-38 KHÔNG tự chứng minh debounce hay polarity.** Không có dữ liệu, log hay kết quả test nào được tạo mới trong PR này.

## 3. BME280 (A-W02-06) — bench verified (standalone), chờ tích hợp ESP-IDF

- **Trạng thái:** `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`.
- **Đã có (phần cứng thật):** bài bench BME280 standalone trên ESP32-S3 bằng sketch Arduino + thư viện Adafruit (COM4 @ 115200): I²C address `0x76`, chip-ID `0x60`, `CHIP_TYPE=BME280`, `BME280_INIT=PASS`; 403 mẫu liên tục 1–403, `valid=1` toàn bộ; `uptime_ms` 2 816→404 816 (402 khoảng × 1000 ms); T 30.27–30.42 °C, RH 68.42–69.14 %RH, P 1011.97–1012.16 hPa. Bằng chứng: `bme280/` (log gốc + CSV + báo cáo; SHA-256 trong `acceptance.md §4.1`/`§11`).
- **Chưa có:** firmware **ESP-IDF W02** đọc BME280 (firmware không có driver I²C/BME280 — cố ý); vị trí gá cuối + xác nhận không bị ESP32/V1 sấy nóng ⇒ vẫn `PENDING_TEST` ở mức nghiệm thu.
- **Cảnh báo vận hành:** sketch Arduino **ghi đè** firmware ESP-IDF trong MCU — **phải nạp lại** firmware chính thức (B0) trước các bài thử W02 khác.
- **Không** đánh dấu toàn bộ W02 PASS; PR vẫn **chưa** đủ điều kiện chốt W02.

## 4. H0 mechanical (A-W02-01) — đề xuất hoãn, cần leader quyết định

- **Trạng thái:** `DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING`.
- **Đề xuất của Member A:** hoãn việc lắp ráp lên thùng sang giai đoạn hoàn thiện cơ khí, hướng tới **W07 geometry freeze**, để các module được test trên bàn trước — lỗi dễ phát hiện hơn và linh kiện dễ thay thế hơn so với khi đã lắp trong thùng.
- **Bốn điểm bắt buộc phải nói rõ:**
  1. **Canonical W02 vẫn yêu cầu H0** — đây là đề xuất, **chưa** được duyệt.
  2. **W07 geometry freeze không tự động thay thế H0 của W02.** Hai mốc khác nhau về thời điểm, mục đích và bằng chứng.
  3. **Trưởng nhóm phải xác nhận điều chỉnh lịch** trước khi đổi bất kỳ trạng thái nào.
  4. **Ảnh hưởng tới W04 thermal commissioning:** W04 cần cụm V1/TEC đã lắp đúng và một plant mô tả được để đo đáp ứng nhiệt/gradient. Nếu H0 chưa xong, W04 chỉ chạy được phần logic/điện (XL4015, MAX3485/PZEM, IBT-2 logic) và **không** tạo được bằng chứng nhiệt có ý nghĩa; **Gate G1** (`docs/04 §19` — Physical/Protocol Preliminary: sensor identity, PZEM valid, IBT-2 default-off, safe first TEC response, real telemetry path, twin separation) có nguy cơ không đạt trong W03–W04 như lịch hiện tại.
- PR này **không** sửa lịch canonical và **không** đánh dấu H0 PASS.

## 5. Những gì CHƯA xác minh (nêu tường minh)

| Hạng mục | Trạng thái | Chi tiết |
|---|---|---|
| Log/CSV dữ liệu thô 600 dòng của **phiên cũ** | **`RAW_EVIDENCE_PENDING`** | Chỉ có 9 dòng CSV hiển thị trong ảnh; **không có** `sensor-consistency.csv` của phiên cũ ⇒ không thể tính lại mean/SD độc lập từ dữ liệu gốc. **Phiên 620 mẫu mới đã nhập** (`ds18b20/`) nhưng là sketch Arduino — CSV của firmware dùng `cg_build_sensor_csv.py` vẫn `REAL RUN PENDING` |
| `door-test.csv` thô của **phiên cũ** | **`RAW_EVIDENCE_PENDING`** | Chỉ có 6 dòng log hiển thị; không có file. **Bench MC-38 thô 48 cặp đã nhập** (`mc38/`, schema sketch); CSV theo schema `cg_build_door_csv.py` (firmware) vẫn `REAL RUN PENDING` |
| Tích hợp BME280 vào firmware ESP-IDF | **CHƯA** | Firmware W02 **không** có driver BME280 (cố ý); bằng chứng hiện có là bài bench **standalone** bằng sketch Arduino (`bme280/`) — **không** phải firmware ESP-IDF đọc BME280 |
| Log 5 chu kỳ reboot (A-W02-03) | **`IMPLEMENTED — HARDWARE RUN PENDING`** | Cơ chế + công cụ xác minh đã xong và đã test tự động (5 khối dán lặp ⇒ `BOOT_METADATA_INVALID`, không thể giả 5 reboot); **chưa** chạy 5 lần reset trên board ⇒ `no silent remap across reboot` **chưa** được chứng minh |
| Nhãn vật lý T1/T2/T3 | **PENDING** | Đầu dò chưa được nhận diện/dán nhãn ⇒ leader review "chỉ tay vào T1/T2/T3" chưa thực hiện được |
| Timestamp của **phiên cũ** | **KHÔNG có** | Serial Monitor để `Show timestamp = OFF`; nhịp ~1 Hz và độ dài ≥10 phút của phiên cũ chỉ là **suy luận**. Phiên mới sẽ có `uptime_ms` thật trong từng dòng `#CG SAMPLE` |
| Polarity MC-38 (`raw → OPEN/CLOSED`) | **`BENCH OBSERVED — FIRMWARE FREEZE PENDING`** | Bài bench thô MC-38 có **dấu vật lý trong log** (dòng `# PHYSICAL=NEAR/FAR` do người vận hành ghi tại test) ⇒ `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` (`mc38/`). Firmware W02 **không** đã freeze cờ (`CG_DOOR_POLARITY_CONFIRMED=0` ⇒ `state=UNVERIFIED` cho log của firmware); công cụ `cg_build_door_csv.py` **bắt buộc** `--open-level` do người vận hành quan sát |
| Debounce MC-38 | **`BENCH VERIFIED (SKETCH) — FIRMWARE RUN PENDING`** | Bài bench thô: **48/48 cặp `RAW`/`STABLE` đúng +40 ms**, 48 cạnh thô không gộp sai (lẽ cạnh gần nhất 476 ms ≫ cửa sổ 40 ms) — `mc38/mc38-bench-report.md`. Phiên firmware thật (`CG_DOOR_DEBOUNCE_MS=50`, đếm `raw_edges`/`discarded_edges`) vẫn `PENDING` |
| Nguồn firmware sketch bench (sinh ra 3 ảnh) | **`NOT_IN_REPO`** | Repo nay có **firmware W02 chính thức mới** (`firmware/main/`), nhưng đó **không** phải nguồn của 3 ảnh — không dùng nó để suy ngược hành vi sketch cũ. Sketch nguồn của `mc38/` và `ds18b20/` **cũng** `NOT_IN_REPO` — dữ liệu thô được giữ nguyên byte từ phía người dùng, provenance được ghi tường minh |
| Error handling khi đọc DS18B20 lỗi/mất | **Đã implement — chưa chạy thật** | `nan` khi thiếu/CRC lỗi/85 °C power-on/ngoài dải; `VALID/DEGRADED/INVALID` theo docs/01 §6.8; chưa có bài test phần cứng rút một đầu dò |
| `sensor-placement.png`, ảnh H0 | **MISSING** | Không vẽ lại từ trí nhớ, không tạo ảnh giả |
| Biên dịch firmware | **PASS trên CI (ESP32-S3)** | GitHub Actions, image `espressif/idf:v6.1` + target `esp32s3`: **SUCCESS**, 0 cảnh báo, artifact + SHA-256 trong `build-report-w02.md`; máy cục bộ vẫn không có ESP-IDF/Docker |
| Nạp + chạy firmware | **CHƯA** | Chưa flash, chưa mở serial, chưa có dòng `#CG …` thật nào |
| Lệch số lượng đầu dò | **Chờ quyết định** | Canonical `SEN-H1-01` ghi 3 ROM; thực tế 4 đầu dò (kế thừa `CR-A-W01-04`) |
| `hardware_config_id`, ngày review | **Chưa gán** | Cần leader gán. `firmware_commit` đã ghi SHA thật (xem mục đầu của body này) |

## 6. Điều kiện để W02 được nghiệm thu

W02 chỉ có thể chuyển sang PASS khi tất cả các điều kiện sau được đáp ứng (`acceptance.md §5` là nguồn canonical):

1. `A-W02-06`: **đã có** chip-ID/I²C/T·RH thật (bench standalone — `bme280/`); còn lại: tích hợp BME280 vào firmware ESP-IDF (hoặc chốt phạm vi bằng văn bản với leader) + vị trí gá cuối + xác nhận không bị ESP32/V1 sấy nóng.
2. `A-W02-03`: log ≥5 chu kỳ reboot/discovery chứng minh ROM→role giữ nguyên (chạy `cg_verify_reboots.py` trên log thật).
3. `A-W02-05`: **bộ dữ liệu bench 620 mẫu đã có** (`ds18b20/`, ROM cùng-capture dời sang bài 5 reboot); còn lại: **phiên ≥10 phút chạy bằng firmware mới** (nhịp và độ dài khi đó **đo được** qua `uptime_ms`) và `sensor-consistency.csv` theo schema `cg_build_sensor_csv.py`.
4. `A-W02-07`: **phần bench đã có** (`mc38/` — polarity, 40 ms debounce, 24 chu kỳ); còn lại: firmware ESP-IDF chạy thật + `door-test.csv` dựng bằng `cg_build_door_csv.py --open-level` từ log `#CG DOOR_EDGE`, kèm cạnh thô/bị bỏ cho từng chu kỳ.
5. `A-W02-02`: dán nhãn vật lý T1/T2/T3 (+ SPARE), có ảnh nhãn; nâng trạng thái khỏi `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`.
6. `A-W02-01`: quyết định của leader về H0 (giữ trong W02 hay dời sang giai đoạn hoàn thiện cơ khí hướng W07), kèm ảnh/checklist nếu chuyển.
7. `A-W02-04`: đã đưa firmware W02 vào repo + ghi `firmware_commit`, và **build log đã có** (CI ESP-IDF v6.1, `esp32s3`, SUCCESS — `build-report-w02.md`); **còn lại** là một lần nạp/chạy thật. Nguồn sketch bench cũ vẫn `NOT_IN_REPO`.
8. Leader xác nhận lệch số lượng đầu dò và gán `hardware_config_id` + ngày review.

Thêm hai điều kiện về tiêu chí: leader xác nhận `A-W02-05` chỉ cần **consistency check** (không cần chuẩn truy vết) ở W02, và chấp nhận việc merge PR này khi W02 vẫn ở trạng thái `PARTIAL` (PR là để review hồ sơ, không phải để tuyên bố PASS).

## 7. Quyết định cần Team Leader phê duyệt

| Nội dung | Vì sao cần leader |
|---|---|
| Cho phép hoãn H0 hay buộc H0 xong trong W02 | Canonical W02 yêu cầu H0; W07 không tự động thay thế |
| Chấp nhận cấu hình 4 đầu dò (3 vai trò + 1 spare) | Lệch với `SEN-H1-01` ("3 unique ROM IDs"); W01 đã ghi `CR-A-W01-04` |
| Xác nhận `A-W02-05` chỉ cần consistency check | `docs/03 §15` cho phép gọi là consistency check, nhưng cần chốt phạm vi |
| Chấp nhận merge PR khi W02 `PARTIAL` | Để không chặn review kỹ thuật và commit BME280 tiếp theo |

## 8. Trọng tâm review cho Member D

1. Cách đọc số liệu consistency: 0.603 °C chênh lệch trung bình lớn nhất **không** được diễn giải thành sai số cảm biến, và **không** có ngưỡng số nào được tự đặt. Kiểm tra xem cách lập luận này có bị hiểu thành "sensor đã đạt yêu cầu" hay không.
2. Xác nhận rằng `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` là trạng thái **đúng** và chưa có gì bị nâng cấp quá mức.
3. Xác nhận lập luận vì sao `MC38 initial: HIGH` **không** đủ để freeze polarity.
4. Kiểm tra tác động của việc hoãn H0 lên W04 và lên Gate G1 (phần nhiệt).
5. Xác nhận PR này **không** tuyên bố bất kỳ trạng thái an toàn điện nào (không cấp nguồn TEC, không chạm dải dòng lớn).
6. **Firmware W02 mới (lần cập nhật này):** `docs/04 §3.3` yêu cầu Member D review physical wiring/pin/sensing. Đề nghị D kiểm tra: chân GPIO theo `docs/01 §11.7` (GPIO10/21/33/34/35/36/37/5/6), thứ tự reset 1-Wire (≈480/70/410 µs), chọn 12-bit + 750 ms, ngưỡng/đếm debounce MC-38 (`CG_DOOR_DEBOUNCE_MS=50`), và logic `VALID/DEGRADED/INVALID`. **Lưu ý:** firmware **đã** được biên dịch thật trên CI (`esp32s3`, SUCCESS) nhưng **chưa** được nạp/chạy — review này là review mã nguồn + kết quả compile, không phải review kết quả đo.

## 9. Cập nhật lần này: firmware W02 + công cụ kiểm chứng (không cần phần cứng)

Đây là phần `A-W02-03`, `A-W02-04` (phần code) và `A-W02-07` (phần code) mà trước đó **chưa hề có trong repo**. Tất cả đều nằm trong phạm vi Member A.

| Hạng mục | Nơi | Trạng thái thật |
|---|---|---|
| ROM→role cố định, CRC8, không dùng thứ tự discovery | `firmware/main/cg_rom_map.c/.h`, `coldguard_config.h` | Đã implement + kiểm tra tĩnh |
| Shared conversion, `nan` khi lỗi, `VALID/DEGRADED/INVALID` | `firmware/main/cg_ds18b20.c/.h`, `cg_onewire.c/.h` | Đã implement + kiểm tra tĩnh |
| Nhịp ~1 Hz theo deadline, `uptime_ms` thật, `seq` | `firmware/main/app_main.c` | Đã implement + kiểm tra tĩnh |
| Boot identity ≥5 reboot (NVS `boot_count`, `boot_id`, khối `#CG ROM`) | `firmware/main/app_main.c` | Đã implement + công cụ đòi `boot_id` phân biệt & `boot_count` tăng dần; cần 5 lần reset thật |
| MC-38 debounce cấu hình được + cạnh thô `µs` + không đoán polarity | `firmware/main/cg_door.c/.h` | Đã implement + 3 test mô hình + test công cụ |
| IBT-2 OFF trước mọi khởi tạo (docs/01 §11.8) | `firmware/main/cg_safety.c/.h` | Đã implement + kiểm tra tĩnh |
| Parser log + 4 CLI + kiểm tra tĩnh + 1 lệnh gộp | `firmware/tools/` | 57 test + 39 check PASS |

**Giới hạn đã khai báo, không giấu:** (1) firmware **đã được biên dịch thật trên CI** (ESP-IDF v6.1, `esp32s3`, SUCCESS — `build-report-w02.md`); máy cục bộ vẫn không có ESP-IDF/Docker nên các test hành vi vẫn là mô hình Python + kiểm tra tĩnh, **chưa** có golden-run trên target; (2) ~~chưa nạp và chưa chạy lần nào~~ **đã cập nhật 7:** đã nạp + chạy thật (§9.1); phần **chưa** chạy là bài cửa (`#CG DOOR_EDGE`) và CSV consistency ≥600 mẫu; (3) **không** cài ROM search ⇒ không phát hiện thiết bị 1-Wire lạ (identity vẫn an toàn vì đọc theo ROM cố định, và dòng `#CG ROMS` không in `unknown=` vì không có gì để đo); (4) BME280 **không** thuộc firmware W02. Quy trình bench còn lại nằm ở `bench-procedure-w02.md`.

## 9.1. Cập nhật 7: flash thật + 5 reboot identity PASS + runtime ~1 Hz

Đề xuất thay đổi PR: fix `firmware/main/app_main.c` (door task) + tool mới `firmware/tools/cg_auto_reboot.py` + toàn bộ thư mục `evidence/A/W02/espidf-run/`.

| Bước | Kết quả thật (2026-10-18) | Evidence |
|---|---|---|
| Xác minh MCU trước flash | ESP32-S3 (QFN56) rev v0.2, USB-Serial/JTAG, MAC `e0:72:a1:bc:cf:4c` khớp instance USB `VID_303A&PID_1001`; flash thực 4 MB (layout 2 MB của build nằm gọn) | `espidf-run/flash-provenance.md` |
| Backup rollback | Full-flash 4 MB trước flash (4 194 304 B, SHA-256 `cee6d3f7…ab42`); rollback = 1 lệnh `esptool write-flash 0x0 <backup>`; **không** `erase-all` | `espidf-run/flash-provenance.md` |
| Artifact CI → flash | Run 39134178842 (head `1b93f572`); SHA-256 3/3 file khớp `30-artifacts.txt`; `ELF file SHA256` lúc boot khớp ELF artifact (`1a47211f41e0…a8252`); flash 3/3 region `Hash of data verified` | `espidf-run/flash-original-log.txt` |
| Bug runtime thật (firmware `a8f5c58`) | Flash đầu: board boot nhưng 0 dòng `#CG ROM`/`#CG SAMPLE` + task watchdog IDLE0 dội — `vTaskDelay(pdMS_TO_TICKS(5))==0` khi `CONFIG_FREERTOS_HZ=100` ⇒ door task (prio 6) spin vô hạn, sensor task chết đói. Fix: 1 tick tối thiểu (`wait_ticks > 0 ? wait_ticks : 1`) — commit `1b93f572`; build lại CI rồi flash lại | `acceptance.md` §14; `firmware-implementation.md` §6 |
| 5 reboot thật (host-driven) | Mỗi reset = mở cổng + hạ DTR/RTS ⇒ banner `rst:0x15 (USB_UART_CHIP_RESET), boot:0x8` **6/6**; verifier `cg_verify_reboots.py`: **REBOOT IDENTITY PASS (6 boots, roles stable)**; `boot_id` 6 giá trị phân biệt; NVS `boot_count` **5→10 tăng liên tục**; kiểm tra độc lập gồm SPARE: 6/6 boot in đủ 4 ROM đúng bản đồ đóng băng. (Phương án RTS-only kiểu esptool **không** reset được app — ghi nhận trong evidence để tránh lặp.) | `espidf-run/serial-reboot-original.log` + `reboot-verification-report.txt` + `reboot-verification.json` |
| Runtime firmware thật | **252 dòng `#CG SAMPLE`**: 246 interval đều trong [990, 1000] ms (mean **999.756**, median 1000); 252/252 `t1=t2=t3=1`, `thermal=VALID`; 0 `nan`/sentinel; 0 `#CG ERR`; mean 4 vai trò ~29.8–30.4 °C; `door_raw=1` bất động suốt phiên (không thao tác cửa — **không** tuyên bố `#CG DOOR_EDGE`) | `espidf-run/runtime-cadence.md` |

→ `A-W02-03` → **`HARDWARE VERIFIED — 6 BOOT IDENTITY STABLE`**; `A-W02-04` → **`HARDWARE RUNTIME VERIFIED — 252 SAMPLES @ ~1 HZ`**; phần same-capture ROM của `A-W02-05` đã resolve (mỗi boot firmware in đủ 4 ROM). **Trạng thái tổng vẫn `W02_PARTIAL_EVIDENCE` — NOT PASS** (còn: bài cửa firmware + `door-test.csv`, CSV ≥600 mẫu từ firmware, dán nhãn vật lý, H0 deferred, sketch bench `NOT_IN_REPO`).

## 10. Kiểm tra đã chạy

- `py firmware/tools/run_all_checks.py` → **3/3 PASS**: (a) 57 test `unittest` của công cụ, (b) 39 kiểm tra tĩnh firmware, (c) `validate_w02.py`.
- **Xác minh bằng chứng BME280 (sau khi nhập):** 403/403 mẫu liên tục, `valid=1`, 402 khoảng × 1000 ms; thống kê T/RH/P **tính lại từ log gốc** khớp báo cáo & CSV (0 sai lệch); SHA-256 3 tệp khớp như ghi ở `acceptance.md §4.1`/`§11` (`bme280/`).
- **Xác minh bằng chứng MC-38 (sau khi nhập):** log gốc giữ nguyên byte (SHA `38cdeef5…`); CSV **tái dựng được từ log** bằng script xác minh — 48/48 cặp `RAW`/`STABLE` đúng +40 ms, bộ đếm luỹ tiến 1..48, chuyển mức xen kẽ đều, **24 chu kỳ**, polarity khớp chú thích vật lý 48/48; 0 sai lệch. Chi tiết: `mc38/mc38-bench-report.md`; hash được `validate_w02.py` khoá từ này trở đi.
- **Xác minh bằng chứng DS18B20 620 mẫu (sau khi nhập):** log gốc giữ nguyên byte (SHA `44228795…`); re-check máy móc: 620 mẫu liên tục 1–620 (0 trùng/0 thiếu), uptime 42 014→661 014 (619 khoảng × 1000 ms), 4 vai trò **620/620** cờ valid, 0 sentinel (85 °C/−127/ngoài dải); thống kê tính lại từ log khớp 100% báo cáo capture; CSV **khớp từng dòng** (0 sai lệch); raw log chứa **0 dòng ROM** — cảnh báo `ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG` giữ nguyên, provenance ghi tường minh (`ds18b20/ds18b20-verification.md`). Chi tiết + hash: `acceptance.md §13`; hash được `validate_w02.py` khoá từ này trở đi.
- **Build ESP-IDF thật (CI, không cần phần cứng):** GitHub Actions, image `espressif/idf:v6.1`, target `esp32s3` → **SUCCESS**, 0 cảnh báo, `coldguard_firmware.bin` = 0x31360 bytes — run [39117530768](https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117530768) (push) + [39117534103](https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117534103) (pull_request); chi tiết + SHA-256: `build-report-w02.md`. Run đầu (`39117011427`) **FAIL** vì thiếu `esp_driver_gpio` trong requirements — đã sửa tại commit `2a5a0da…` rồi build lại.
- `py validate_w02.py` → **W02 STRUCTURE PASS**: 14 file bắt buộc, 4 bản ghi truy xuất nguồn được xác minh bằng kích thước + SHA-256 (3 ảnh gốc + 1 ghi chú archive), ROM map đúng 3 vai trò + 1 spare (mỗi đầu dò đều `physical_label: PENDING`), `firmware_commit` trỏ tới commit thật **chứa đủ 5 module W02** (`app_main.c`, `cg_onewire.c`, `cg_rom_map.c`, `cg_ds18b20.c`, `cg_door.c`) và ROM bytes trong `coldguard_config.h` khớp từng byte với `sensor-rom-map.yaml` (đọc từ chính commit bằng `git cat-file`/`git show`), `acceptance.md` bao phủ `A-W02-01…A-W02-07`, firmware static checks PASS.
- Kiểm tra tĩnh firmware gồm: ROM trong `coldguard_config.h` khớp **từng byte** với `sensor-rom-map.yaml` và **CRC8 Dallas hợp lệ** cho cả 4 ROM (bắt lỗi chép sai ký tự); hàm đọc từng đầu dò **không** chứa bất kỳ token/call `convert` nào (không chỉ `CONVERT_T`); nhánh polarity `#if`/`#else` bị kiểm tra **ngữ nghĩa** (đảo nhánh vẫn bị từ chối); không có gán vai trò theo chỉ số vòng lặp; `CG_DOOR_POLARITY_CONFIRMED` vẫn `0`; `CG_DOOR_DEBOUNCE_MS`/`CG_SAMPLE_PERIOD_MS` là macro cấu hình; `#CG ROMS` không in `unknown=`; BME280 bị quét trong **mọi** `.c`/`.h` của `firmware/main`; thứ tự gọi an toàn trong `app_main`; `CMakeLists.txt` liệt kê đủ mọi file `.c`.
- Test CLI end-to-end: thiếu `--open-level` ⇒ **mọi dòng dữ liệu CSV** mang `state=UNVERIFIED`, exit 1; `nan` ⇒ ô CSV rỗng (không bao giờ 0.0); < 600 mẫu hợp lệ ⇒ `WINDOW NOT USABLE` + exit 1; < 20 chu kỳ ⇒ exit 1; 5 khối boot dán lặp hoặc `boot_count=0` ⇒ `BOOT_METADATA_INVALID` + exit 1; capture cửa trải nhiều boot ⇒ từ chối cho tới khi có `--boot N`.
- Băm lại archive gốc đối chiếu `source_archive_sha256` (xem `README.md` §Reproduction bước 4).
- `git diff --cached --check` → không có lỗi whitespace/conflict marker.
- **Phản biện độc lập vòng 2** (không do tác giả thực hiện; đọc trực tiếp firmware/công cụ của lần cập nhật này và chạy lại toàn bộ kiểm tra) đã phát hiện **BLOCKER F01–F04** (hồ sơ in output kiểm tra không tái lập được khi `firmware_commit` còn là placeholder) + **MAJOR F05** (đảo dấu chênh lệch cặp) + các MINOR F06–F14/N01–N06 — **tất cả đã được xử lý trong chính PR này** (F13 ghi nhận là giới hạn: test hành vi vẫn là mô hình + kiểm tra tĩnh; lớp **biên dịch thật** bằng ESP-IDF trên CI nay đã bổ sung — xem `firmware-implementation.md` §5.6). Vòng phản biện trước đó trên **lớp bằng chứng 3 ảnh** (đọc 3 ảnh gốc, băm lại archive, tính lại số dẫn xuất) ghi nhận không có BLOCKER/MAJOR trong phạm vi 3 ảnh.
- **Kiểm tra + chạy thật cập nhật 7:** `run_all_checks.py` 3/3 PASS sau commit `1b93f572` (validator nay **9/9 bench/flash/reboot blob hash verified** — khoá thêm 4 blob `espidf-run/`); flash thật 3/3 region verified (`espidf-run/flash-original-log.txt`); **5 reboot identity thật: PASS** (`espidf-run/reboot-verification-report.txt` — "`REBOOT IDENTITY: PASS (6 boots, roles stable, boot metadata consistent)`") + kiểm tra độc lập gồm SPARE 6/6 boots; runtime 252 mẫu, cadence tính lại từ log (`espidf-run/runtime-cadence.md`). Bug runtime `a8f5c58` → fix `1b93f572` được ghi tường minh (`firmware-implementation.md` §6, `build-report-w02.md` §7).
- **Phạm vi bằng chứng vật lý:** bài bench cảm biến duy nhất là **standalone sketch** (BME280 — §3; MC-38 + DS18B20 sketch); firmware ESP-IDF **đã nạp + chạy thật** nhưng phạm vi phiên đó là **reboot identity + cadence** (§9.1) — **chưa** có bài cửa (`#CG DOOR_EDGE`) và **chưa** dựng CSV ≥600 mẫu từ firmware. Ngoài phạm vi: TEC, tải dòng lớn.

## 11. Ngoài phạm vi

Không cấp nguồn TEC, không chạy tải dòng lớn, không thay đổi BOM freeze, không sửa `docs/00`–`docs/05A`, không đổi lịch canonical, không tạo dữ liệu giả, không merge PR, không bắt đầu W03.
