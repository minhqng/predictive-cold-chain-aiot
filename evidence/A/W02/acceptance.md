# W02 acceptance — Member A

Tệp này là **nguồn trạng thái duy nhất** cho nghiệm thu W02 của Member A. Các file khác trong `evidence/A/W02/` chỉ cung cấp bằng chứng và **không** lặp lại checklist.

**Snapshot:** 2026-10-18 (cập nhật 7: flash firmware ESP-IDF thật + 5 reboot identity PASS + runtime ~1 Hz) · **Phiên bản hồ sơ:** W02 · **hardware_config_id:** `NOT_ASSIGNED` · **firmware commit (repo):** `1b93f572ed3f06a3030292b2515fa38bcaf75ca7` (fix door-task runtime spin; trước đó `2a5a0dac…`) · **build ESP-IDF thật (CI):** `SUCCESS — esp32s3` (`build-report-w02.md`, mới nhất: run `39134178842`) · **flash thật trên board (COM4, ESP32-S3 MAC `e0:72:a1:bc:cf:4c`):** `PASS — 3/3 region hash verified` (`espidf-run/flash-provenance.md`) · **5 reboot identity:** `PASS — 6 boots, ROM→role ổn định, NVS boot_count 5→10` (`espidf-run/reboot-verification.md`) · **firmware runtime:** `252 SAMPLE @ ~1 Hz đo được, VALID 252/252` (`espidf-run/runtime-cadence.md`) · **BME280 bench (ESP32-S3, standalone):** `PASS — 403/403 mẫu` (`bme280/`) · **MC-38 bench thô (ESP32-S3, standalone):** `PASS — 48 cặp RAW/STABLE, 24 chu kỳ` (`mc38/`) · **DS18B20 bench thô (ESP32-S3, standalone):** `PASS — 620/620 mẫu, 619 s, 4 vai trò đều hợp lệ` (`ds18b20/`) · **firmware sketch bench (nguồn 3 ảnh):** `NOT_IN_REPO`

**Trạng thái tổng: `W02 NOT PASS` — `W02_PARTIAL_EVIDENCE`.** Việc mở PR **không** đồng nghĩa W02 đã PASS. Firmware giờ **đã nạp và chạy thật** trên board ESP32-S3 (§14): reboot identity + nhịp ~1 Hz + ROM→role cùng-boot đã có bằng chứng thật; tuy vậy tổng thể vẫn NOT PASS vì: nhãn vật lý chưa dán (`A-W02-02`), bài cửa bằng firmware và `door-test.csv` cùng cờ polarity chưa đóng (`A-W02-07`), H0 deferred (`A-W02-01`), vẫn thiếu deliverable canonical (ảnh vị trí, ảnh setup, CSV consistency dựng từ firmware ≥600 mẫu) và sketch bench nguồn 3 ảnh vẫn `NOT_IN_REPO`.

---

## 1. Acceptance matrix — A-W02-01 … A-W02-07 (`docs/05A §11`)

| ID | Hạng mục canonical | Tiêu chí | Bằng chứng hiện có | Trạng thái | Phần còn thiếu |
|---|---|---|---|---|---|
| **A-W02-01** | Mechanical H0 (`HW-H0-01`, `HW-H0-02`) | V1/TEC gắn chắc, không cấp nguồn TEC; đóng băng vị trí T1/T2/T3, BME, MC-38; không linh kiện lỏng, không hướng mơ hồ | **Không có** | **`DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING`** | Ảnh H0, checklist lắp ráp, sketch vị trí tương đối; quyết định lịch của leader |
| **A-W02-02** | DS18B20 enumeration | Phát hiện đúng ROM mong đợi, ghi ánh xạ chính xác | `w02_rom_enumeration_4_devices.png`, `sensor-rom-map.yaml`, ROM map **đã được ghi cứng vào firmware** (`coldguard_config.h`, đối chiếu tự động với YAML + CRC8) | **`ROM→ROLE FROZEN — PHYSICAL LABEL PENDING_USER_LABELING`** | Canonical mong đợi **3** ROM, thực tế **4**; lệch số lượng cần leader xác nhận (kế thừa `CR-A-W01-04`). Đầu dò chưa được dán nhãn vật lý → `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` |
| **A-W02-03** | Reboot identity proof | ≥5 chu kỳ reboot/discovery giữ nguyên ROM→role | **Log thật (`espidf-run/serial-reboot-original.log`, 58 271 bytes, SHA-256 `e48977be…`):** firmware ESP-IDF thật đã nạp từ artifact CI (§14) → `#CG ROM` block được phát ra rõ ràng ở boot; 5 lần reset do host tự động triggering qua cổng COM4 (banner `rst:0x15 USB_UART_CHIP_RESET, boot:0x8` 6/6 lần trong raw log); `boot_id` 6 giá trị phân biệt; NVS `boot_count 5→10` tăng liên tục; ROM→role ổn định ở tìm thấy từ cả tool chính thức `cg_verify_reboots.py` (**REBOOT IDENTITY PASS**, output trong `espidf-run/reboot-verification-report.txt` + `.json`) và script độc lập (gồm cả SPARE — 6/6 boot khớp 4/4 ROM bản đồ đóng băng) | **`HARDWARE VERIFIED — 6 BOOT IDENTITY STABLE (ESP-IDF RUN 1b93f572)`** | (1) Không đề cập thuộc vật lý dán nhãn (A-W02-02); (2) Tương tự: không tự động thay thế cho bài bench sketch `w02_rom_enumeration_4_devices.png` — điều kiện tính là *hai phiên bằng chứng riêng biệt* (một firmware một sketch); phương thức "mở cổng + hạ DTR/RTS = USB_UART_CHIP_RESET" được ghi chú để phiên sau tái lập |
| **A-W02-04** | Acquisition implementation | Shared conversion → đọc từng ROM; snapshot ~1 Hz; xử lý lỗi đọc | Firmware nay **đã nạp và chạy thật** trên ESP32-S3 (MAC `e0:72:a1:bc:cf:4c`, artifact run `39134178842` — commit `1b93f572`): log `#CG SAMPLE` với `uptime_ms` thật **252 mẫu** — 246 khoảng thời gian liên tục đều trong [990, 1000] ms (mean 999.756, median 1000); 252/252 `t1=t2=t3=1`, `thermal=VALID`; 4 giá trị cùng khối (shared conversion quan sát trong từng dòng sample); **0 sample sentinel/`nan`**; min–max 4 vai trò 0.0625-°C-LSB tương hợp; `#CG ERR` 0 dòng — `espidf-run/runtime-cadence.md` | **`HARDWARE RUNTIME VERIFIED — 252 SAMPLES @ ~1 HZ (firms ESP-IDF 1b93f572)`** | (1) **CSV consistency từ firmware ≥600 mẫu** (`sensor-consistency.csv` schema `#CG SAMPLE` bằng `cg_build_sensor_csv.py`) vẫn `PENDING` — phiên runtime ngắn (4 phút) đủ để chứng minh nhịp chứ **không** phải consistency window; (2) **nguồn sketch bench** sinh ra 3 ảnh vẫn không nằm trong repo ⇒ shared conversion của *phiên bench cũ* vẫn `RAW_EVIDENCE_PENDING` |
| **A-W02-05** | Inter-sensor consistency | ≥10 phút ở ~1 Hz; có mean, SD, chênh lệch cặp, chênh lệch lớn nhất | **Dữ liệu bench thô mới (`ds18b20/`):** log thật 620 mẫu (sketch Arduino standalone, COM4 @ 115200 — không phải firmware ESP-IDF): liên tục 1–620 (0 trùng/0 thiếu), `uptime_ms` 42 014→661 014 ⇒ **619 000 ms, 619 khoảng đều 1000 ms**; 4 vai trò **620/620 hợp lệ** (2 480/2 480 cờ valid); 0 giá trị sentinel; thống kê tính lại từ log: T1 29.878528 (sd 0.021467), T2 30.187903 (0.016275), T3 29.568347 (0.023374), SPARE 29.921774 (0.028058); chênh lệch cặp: T1−T2 −0.309375, T1−T3 +0.310181, **T2−T3 +0.619556 (lớn nhất)**; chênh lệch tức thời lớn nhất 0.6875 °C; CSV khớp log từng dòng — `ds18b20/ds18b20-verification.md` · bằng chứng phiên cũ (`w02_ds18b20_600_samples_summary.png`, `sensor-consistency-summary.md`) vẫn `RAW_EVIDENCE_PENDING` — hai phiên không hợp nhất | **`BENCH DATA VERIFIED — 620 RAW SAMPLES CAPTURED — ROM SAME-BOOT PROVEN (§14)`** | (1) ~~ROM discovery không nằm trong cùng raw capture~~ **Đã resolve:** kết hợp cùng-boot bằng firmware chính thức — mỗi boot của firmware `#CG ROM` in đủ 4 ROM (`espidf-run/reboot-verification.md` 6/6 boots khớp bản đồ đóng băng); phiên 620 mẫu sketch giữ nguyên không bị chèn ROM; (2) ~~firmware ESP-IDF ~1 Hz still PENDING~~ **Đã đo được:** firmware `#CG SAMPLE` nhịp 1 Hz thật (252 mẫu — `espidf-run/runtime-cadence.md`); **CSV consistency từ firmware ≥600 mẫu vẫn `PENDING`**; (3) ảnh setup của phiên 620 mẫu chưa có; (4) nguồn sketch bench vẫn `NOT_IN_REPO` |
| **A-W02-06** | BME280 | I²C address, T/RH hợp lý, không bị ESP32/V1 sấy nóng | BME280 bench **thật** trên ESP32-S3 (sketch Arduino/Adafruit): `bme280/` — log gốc + CSV 403/403 mẫu `valid=1` + báo cáo; `BME280_INIT=PASS`, chip-ID `0x60`, I²C `0x76` (SDA GPIO21, SCL GPIO33); thống kê tính lại độc lập từ log | **`BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`** | (1) **Tích hợp ESP-IDF:** firmware W02 **không** có driver BME280 (cố ý) — muốn "firmware chính thức đọc BME280" cần task riêng; (2) vị trí gá cuối + không bị ESP32/V1 sấy nóng ⇒ `PENDING_TEST`. **Không** đánh dấu A-W02-06 PASS đầy đủ |
| **A-W02-07** | MC-38 | ≥20 chu kỳ mở/đóng; semantic OPEN/CLOSED khớp vật lý; transition tin cậy (debounce) | **Bench thô mới (`mc38/`):** log thật 48 cặp `RAW/STABLE` (GPIO34, debounce 40 ms, tổng 508 s, mốc ms từ boot, có dòng chú thích vật lý `# PHYSICAL=NEAR raw=0 stable=0`/`# PHYSICAL=FAR raw=1 stable=1`) + CSV dẫn xuất, xác minh máy móc: 48/48 cặp đúng +40 ms, bộ đếm luỹ tiến 1..48 không thiếu/nhảy, 24 chu kỳ NEAR↔FAR, ánh xạ **NEAR=LOW=CLOSED / FAR=HIGH=OPEN** (báo cáo + SHA-256: `mc38/mc38-bench-report.md`) · đã implement firmware: `firmware/main/cg_door.c` (debounce `CG_DOOR_DEBOUNCE_MS=50`, đếm `raw_edges`/`discarded_edges`, `#CG DOOR_EDGE` theo µs) + `cg_build_door_csv.py` (bắt buộc `--open-level`, từ chối capture nhiều boot) · bằng chứng ảnh cũ (`w02_mc38_24_cycles.png`, `door-test-summary.md`) giờ chỉ còn vai trò truy vết phiên cũ | **`BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`** | (1) Firmware ESP-IDF W02 **chưa** nạp/chạy ⇒ chưa có `#CG DOOR_EDGE`/`#CG DOOR_STATE` và chưa dựng `door-test.csv` bằng `cg_build_door_csv.py --open-level`; (2) cờ `CG_DOOR_POLARITY_CONFIRMED` trong firmware vẫn `0` (không sửa firmware trong lần cập nhật này — ánh xạ polarity ở mức hồ sơ bench); (3) bằng chứng debounce trên hardware thật theo cấu hình `CG_DOOR_DEBOUNCE_MS=50` của firmware (bài bench dùng 40 ms — khác biệt đã khai báo) |

---

## 2. Tiêu chí PASS canonical (`docs/05A §11`)

| Tiêu chí | Trạng thái | Căn cứ / phần thiếu |
|---|---|---|
| 3 unique stable ROMs | **`PARTIAL`** | Có 4 ROM **phân biệt**; ba ROM **ổn định qua reboot đã chứng minh thật** (6 boot firmware ESP-IDF `1b93f572` — `espidf-run/reboot-verification.md`); nhưng con số **vẫn không khớp** canonical "3" và việc dán nhãn vẫn chờ leader + user |
| no silent remap across reboot | **`HARDWARE VERIFIED — 6 REAL REBOOTS`** | Firmware đọc theo ROM cố định; verifier tự động PASS trên log thật (`espidf-run/reboot-verification-report.txt`): `boot_id` phân biệt, NVS `boot_count` 5→10 tăng liên tục (không lặp khối, không reset bộ đếm), 4/4 role + SPARE như nhau 6/6 boots — không còn "chưa tuyên bố" |
| BME responds | **`BENCH VERIFIED (STANDALONE) — ESP-IDF INTEGRATION PENDING`** | Bài bench thật trên ESP32-S3 (sketch Arduino/Adafruit): `BME280_INIT=PASS`, chip-ID `0x60`, I²C `0x76`, T/RH/P đọc hợp lý, 403/403 mẫu hợp lệ — `bme280/`. **Chưa**: firmware ESP-IDF W02 đọc BME280 (firmware không có driver — cố ý) |
| door semantic correct | **`BENCH VERIFIED (SKETCH) — ESP-IDF RUN PENDING`** | Quan sát vật lý **có dấu trong log bench thật** (`mc38/mc38-bench-original.txt`): `# PHYSICAL=NEAR raw=0 stable=0`, `# PHYSICAL=FAR raw=1 stable=1` ⇒ `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` khớp 48/48 cặp trong log. Firmware W02 **không** giả định (cờ `CG_DOOR_POLARITY_CONFIRMED=0` ⇒ `state=UNVERIFIED` cho tới khi chạy ESP-IDF thật); công cụ vẫn bắt buộc `--open-level` khi review log firmware. Chưa freeze `raw → OPEN/CLOSED` trong firmware ⇒ chưa tuyên bố thoả đầy đủ |
| mechanical placement reproducible | **`NOT VERIFIED`** | `A-W02-01` hoãn; chưa có ảnh vị trí/đầu dò được dán nhãn |

**Kết luận:** không tiêu chí nào trong hai bảng trên là `PASS` đầy đủ. Ba tiêu chí đã chuyển từ "chưa có gì" sang **đã implement + có công cụ kiểm chứng đã test tự động**; riêng "BME responds" nay có **bằng chứng bench phần cứng thật** (standalone, sketch Arduino/Adafruit — chưa tích hợp ESP-IDF); toàn bộ vẫn **chưa** từng chạy bằng **firmware ESP-IDF chính thức**.

---

## 3. Deliverables canonical (`docs/05A §11`)

| Deliverable | Trạng thái | File / ghi chú |
|---|---|---|
| H0 mechanical photos | **MISSING** | Thuộc `A-W02-01` đang hoãn |
| `sensor-rom-map.yaml` | **PRESENT (DRAFT)** | Có; trạng thái `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`; nay khớp từng byte với `firmware/main/coldguard_config.h` (kiểm tra tự động) |
| `sensor-placement.png` | **MISSING** | Không có bản vẽ/ảnh vị trí. **Không** được vẽ lại từ trí nhớ |
| H1 serial log | **PRESENT (log có `uptime_ms`, mốc đo thật)** | Trước đây chỉ có 3 ảnh Serial Monitor không timestamp; nay có log thật: `espidf-run/serial-reboot-original.log` — 252 dòng `#CG SAMPLE uptime_ms`, interval mean 999.756 ms (`espidf-run/runtime-cadence.md`) và `ds18b20/ds18b20-serial-original.txt` (620 mẫu, đều 1000 ms). Ảnh Serial Monitor cũ chỉ còn vai trò truy vết |
| Bằng chứng bench BME280 (`bme280/`) | **PRESENT — VERIFIED** | Log gốc + CSV 403/403 mẫu + báo cáo; thống kê tính lại độc lập từ log, CSV khớp từng dòng; SHA-256 ở §4.1/§11. **Không** phải firmware ESP-IDF (bài bench standalone) |
| `sensor-consistency.csv` | **PRESENT (bench 620 mẫu, sketch Arduino) — tool-generated CSV từ firmware vẫn `REAL RUN PENDING`** | `evidence/A/W02/ds18b20/sensor-consistency.csv` (620 dòng, khớp log từng dòng, SHA-256 `99bdc21c…` — `ds18b20/ds18b20-verification.md`): schema `sample,uptime_ms,T1_c,…` của sketch bench, **không** phải schema `#CG SAMPLE` của `cg_build_sensor_csv.py`; **không** có ở root thư mục evidence (validator vẫn kiểm tra "MISSING ở root"). **Note từ phiên runtime firmware (§14):** 252 mẫu `#CG SAMPLE` đủ nhịp (mean interval 999.756 ms) nhưng **không** dựng CSV (validator yêu cầu ≥600 mẫu/window — phiên ngắn chỉ để chứng minh cadence/runtime) |
| `door-test.csv` | **GENERATOR READY — REAL RUN PENDING** | Chưa có file; `firmware/tools/cg_build_door_csv.py` dựng CSV + thống kê dội (bắt buộc `--open-level`) |
| Firmware W02 trong repo | **IMPLEMENTED — CI COMPILE PASS — FLASHED + RUN TRÊN BOARD (§14)** | `firmware/main/` (7 module C) + workflow `.github/workflows/a-w02-espidf-build.yml` (image `espressif/idf:v6.1`, README gốc). Build thật: **SUCCESS**, 0 cảnh báo, artifact + SHA-256 trong `build-report-w02.md`. **Đã flash thật trên board ESP32-S3** (MAC `e0:72:a1:bc:cf:4c`, 3/3 region hash verified + ELF hash khớp — `espidf-run/flash-provenance.md`). Máy cục bộ vẫn không có ESP-IDF/Docker |
| Công cụ + test | **PRESENT, TESTED** | `firmware/tools/` + 57 test `unittest` PASS + 39 kiểm tra tĩnh PASS (`py firmware/tools/run_all_checks.py`) |

**Không** tạo CSV giả để đủ danh sách. Các mục `MISSING` ở lại trạng thái thiếu cho tới khi có dữ liệu thật.

---

## 4. Hạng mục chưa thực hiện (tường minh, không che giấu)

### 4.1 `A-W02-06` — BME280

- **Trạng thái:** `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`.
- **Bằng chứng (phần cứng thật, 2026-10-18):** bài bench BME280 **standalone** trên ESP32-S3 bằng sketch Arduino + thư viện Adafruit BME280 (COM4 @ 115200, SDA=GPIO21, SCL=GPIO33); I²C address `0x76`, chip-ID `0x60`, `CHIP_TYPE=BME280`, `BME280_INIT=PASS`; 403 mẫu liên tục 1–403, `valid=1` toàn bộ; `uptime_ms` 2 816→404 816 (402 khoảng, đều 1000 ms, tổng 402 giây); T 30.27–30.42 °C (mean 30.408, sd 0.017); RH 68.42–69.14 %RH (mean 68.513, sd 0.089); P 1011.97–1012.16 hPa (mean 1012.072, sd 0.037).
- **Files:** `bme280/bme280-bench-original.txt` (13 795 bytes, SHA-256 `da24b6f0d487a4d677892e19c1299d18b207f5ad4f01d1b4635a475d8e606c23`), `bme280/bme280-bench.csv` (13 139 bytes, SHA-256 `5ccddec17820dfda06c552407792dbdf2dde45f8c133d4abb0053ee3665cf43a`), `bme280/bme280-bench-report.md` (2 519 bytes, SHA-256 `c587bf6fce926caaa603a04fb7f987d4903e09e64892c3c2643b213fb92d7813`). Nguồn: `ColdGuard_W02_BME280_Evidence.zip` (7 537 bytes, SHA-256 `f243817e6f3d8ebc3747aadad59e58b3324e2af6ebb75fa1accbb86a75082016`). Thống kê đã được **tính lại độc lập từ log gốc** và CSV **khớp từng dòng**.
- **Điều bằng chứng này chứng minh:** thiết bị BME280 **tồn tại và đọc được** — I²C bus, chip-ID, nhiệt độ, độ ẩm, áp suất — với dữ liệu có mốc `uptime_ms` (không phải wall-clock).
- **Điều bằng chứng này KHÔNG chứng minh:** firmware **ESP-IDF W02** đọc BME280 (firmware W02 **không** có driver BME280 — cố ý, xem `firmware-implementation.md` §5.4); độ chính xác/hiệu chuẩn; hoạt động trong buồng lạnh; vị trí lắp cuối. **Vẫn còn `PENDING_TEST`** cho vị trí gá cuối + xác nhận không bị ESP32/V1 sấy nóng.
- **Cảnh báo vận hành:** sketch Arduino đã **ghi đè** firmware trong MCU ⇒ phải nạp lại firmware ESP-IDF (B0) trước các bài B1–B4.
- **Quy tắc:** **không** đánh dấu A-W02-06 hay W02 PASS đầy đủ từ bằng chứng standalone này. Việc review PR này **không** phải là phê duyệt BME280 mức nghiệm thu.

### 4.2 `A-W02-01` — H0 mechanical

- **Trạng thái:** `DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING`.
- **Lý do Member A đề nghị hoãn:** muốn test các module trên bàn trước, để lỗi được phát hiện và linh kiện được thay thế dễ dàng hơn so với khi đã lắp kín trong thùng.
- **Đề xuất:** dời việc lắp ráp lên thùng sang giai đoạn hoàn thiện cơ khí, hướng tới **W07 geometry freeze**.
- **Các điểm bắt buộc phải ghi rõ:**
  1. **Canonical W02 vẫn yêu cầu H0.** Việc hoãn này là **đề xuất**, chưa được duyệt.
  2. **W07 geometry freeze không tự động thay thế H0 của W02.** Đây là hai mốc khác nhau về thời điểm, mục đích và bằng chứng.
  3. **Trưởng nhóm cần xác nhận điều chỉnh lịch** trước khi bất kỳ trạng thái nào được đổi.
  4. **Ảnh hưởng tới W04 thermal commissioning:** W04 cần một cụm V1/TEC đã lắp đúng và một plant có thể mô tả được để đo đáp ứng nhiệt và gradient. Nếu H0 chưa xong, W04 **chỉ có thể** chạy ở mức logic/điện (XL4015, MAX3485/PZEM, IBT-2 logic) và **không thể** tạo bằng chứng nhiệt có ý nghĩa. Kéo theo: Gate G1 (`docs/04 §19` — sensor identity + PZEM valid + IBT-2 default-off + safe first TEC response + real telemetry path + twin separation) có nguy cơ **không** đạt trong W03–W04 như lịch hiện tại.
- **Tài liệu này không** sửa lịch canonical và **không** đánh dấu H0 PASS.

---

## 5. Blocker và điều kiện để W02 được nghiệm thu

Không có blocker nào **chặn việc mở PR** (hồ sơ trung thực, không có tuyên bố sai). Các mục dưới đây **chặn W02 PASS**:

- [ ] **`A-W02-06`:** phần bench BME280 **đã xong** (xem §4.1); còn lại: (a) tích hợp BME280 vào firmware ESP-IDF W02 hoặc chốt phạm vi bằng văn bản với leader; (b) vị trí gá cuối + xác nhận không bị ESP32/V1 sấy nóng (khi lắp) — `PENDING_TEST`.
- [x] **`A-W02-03`:** ~~chạy 5 lần reset trên board và lưu log; xác minh bằng `py firmware/tools/cg_verify_reboots.py <log>`~~ **ĐÃ XONG (cập nhật 7):** 6 boot thật (5 reset host-driven + 1 context), **REBOOT IDENTITY PASS** — `espidf-run/serial-reboot-original.log` + `reboot-verification-report.txt` (verifier chính thức PASS) + xác minh độc lập gồm cả SPARE: 6/6 boot khớp 4/4 ROM bản đồ đóng băng, NVS `boot_count` 5→10 tăng liên tục.
- [ ] **`A-W02-05`:** phần dữ liệu bench 620 mẫu **đã có** (`ds18b20/` — ≥10 phút thật, 620/620 hợp lệ, thống kê tái lập); **phần same-boot ROM đã resolve qua bài 5 reboot firmware (§14)** — còn lại: phiên **chạy bằng firmware ESP-IDF ≥600 mẫu/≥10 phút** để dựng `sensor-consistency.csv` schema `#CG SAMPLE` bằng `cg_build_sensor_csv.py` (+ điều kiện đặt đầu dò/ảnh setup). (Phiên runtime 252 mẫu ở §14 chỉ chứng minh cadence, không là consistency window.)
- [ ] **`A-W02-07`:** phần bench thô MC-38 **đã xong** (48 cặp RAW/STABLE, debounce 40 ms, polarity NEAR=LOW=CLOSED/FAR=HIGH=OPEN, 24 chu kỳ — `mc38/`); còn lại: chạy firmware ESP-IDF thật + dựng `door-test.csv` bằng `cg_build_door_csv.py --open-level` từ log `#CG DOOR_EDGE`; quyết định freeze `CG_DOOR_POLARITY_CONFIRMED` theo cấu hình firmware thật. (Phiên runtime §14: `door_raw=1` bất động suốt phiên — cửa không bị thao tác, **không** có `#CG DOOR_EDGE` nào ⇒ vẫn phải chạy bài cửa riêng.)
- [ ] **`A-W02-02`:** dán nhãn vật lý T1/T2/T3 (+ SPARE) trên đầu dò thật, có ảnh nhãn; nâng trạng thái khỏi `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`.
- [ ] **`A-W02-01`:** quyết định của leader về H0 (giữ trong W02 hay dời), kèm ảnh/checklist nếu chuyển sang W07.
- [x] **`A-W02-04`:** ~~nạp firmware đã build trên CI và chạy thật để có log `#CG SAMPLE`~~ **ĐÃ XONG (cập nhật 7):** flash thật 3/3 region verified (artifact run `39134178842`, commit `1b93f572`) + runtime 252 mẫu `#CG SAMPLE` nhịp ~1 Hz đo được — `espidf-run/`. Còn lại: **CSV ≥600 mẫu từ firmware** và **nguồn sketch bench** sinh 3 ảnh cũ (`NOT_IN_REPO`).
- [ ] Gán `hardware_config_id` và ngày review.
- [ ] Leader xác nhận lệch số lượng đầu dò (4 so với canonical 3, kế thừa `CR-A-W01-04`) là cấu hình được chấp nhận.

---

## 6. Quyết định cần Team Leader phê duyệt

| Nội dung cần quyết | Vì sao cần leader | Trạng thái |
|---|---|---|
| Cho phép hoãn H0 (`A-W02-01`) sang giai đoạn hoàn thiện cơ khí hướng W07, hay buộc H0 phải xong trong W02 | Canonical W02 yêu cầu H0; W07 không tự động thay thế | **Chờ quyết định** |
| Chấp nhận cấu hình 4 đầu dò DS18B20 (3 vai trò + 1 spare) | Canonical `SEN-H1-01` ghi "3 unique ROM IDs"; W01 đã ghi `CR-A-W01-04` | **Chờ quyết định** |
| Xác nhận không cần chuẩn truy vết cho `A-W02-05` ở W02 (consistency check là đủ) | `docs/03 §15` cho phép gọi là consistency check, nhưng cần xác nhận phạm vi | **Chờ quyết định** |
| Chấp nhận W02 ở trạng thái `PARTIAL` khi merge PR và theo dõi các mục ở §5 | PR tạo ra **không** đồng nghĩa W02 PASS | **Chờ quyết định** |

**Reviewer kỹ thuật bắt buộc:** Member D (đối chiếu `docs/04 §3.3`: "Physical wiring / pin / sensing — Primary A, Required reviewer D").

---

## 7. Phạm vi ngoài W02

- Không cấp nguồn TEC, không chạy tải dòng lớn, không thay đổi BOM freeze.
- Không sửa `docs/00`–`docs/05A`, không sửa lịch canonical.
- Không merge PR, không đóng PR W01, không bắt đầu W03.
- Các hạng mục PZEM/RS-485/IBT-2/first cooling thuộc W03–W04, không đánh giá trong hồ sơ này.

---

## 8. Đã implement bằng code trong PR này (không cần phần cứng)

| Hạng mục | File | Kiểm chứng tự động |
|---|---|---|
| ROM→role cố định, CRC8, không dùng thứ tự discovery | `firmware/main/cg_rom_map.c/.h`, `coldguard_config.h` | `cg_check_firmware.py`: CRC8 từng ROM, đối chiếu YAML, không gán vai trò theo chỉ số vòng lặp |
| Shared conversion + đọc theo ROM + `nan` khi lỗi | `firmware/main/cg_ds18b20.c/.h`, `cg_onewire.c/.h` | kiểm tra tĩnh: broadcast `SKIP_ROM`+`CONVERT_T`, và hàm đọc từng đầu dò không chứa bất kỳ token/call `convert` nào |
| Nhịp ~1 Hz theo deadline, `uptime_ms` là thời điểm thật | `firmware/main/app_main.c` | kiểm tra tĩnh: `CG_SAMPLE_PERIOD_MS=1000`, vòng lặp `next_deadline_us` |
| MC-38: debounce cấu hình được, đếm cạnh thô/bỏ đi, không đoán polarity | `firmware/main/cg_door.c/.h` | kiểm tra tĩnh (đảo nhánh `#if`/`#else` bị từ chối) + 3 test mô hình debounce + test CLI (thiếu `--open-level` ⇒ mọi dòng CSV `UNVERIFIED`, exit 1; capture nhiều boot ⇒ từ chối, cần `--boot N`) |
| An toàn boot: IBT-2 OFF trước mọi khởi tạo | `firmware/main/cg_safety.c/.h` | kiểm tra tĩnh: thứ tự gọi trong `app_main` |
| Log grammar + phân tích, CSV, xác minh reboot | `firmware/tools/` (5 CLI + parser) | 57 test `unittest` (parser, thống kê, CLI end-to-end, exit code) |
| Một lệnh chạy tất cả | `firmware/tools/run_all_checks.py` | 3/3 lớp PASS trên máy này (57 test + 39 check tĩnh + validator hồ sơ, sau commit firmware `1b93f572…`) + **9/9 bench/flash/reboot blob hash verified** |
| Build ESP-IDF thật (CI, không cần máy cục bộ) | `.github/workflows/a-w02-espidf-build.yml` | `espressif/idf:v6.1` + `esp32s3`, **SUCCESS** — run `39117530768` (cập nhật 2), run `39131281315` (cập nhật 5), run `39134178842` (cập nhật 7, firmware `1b93f572`) — chi tiết: `build-report-w02.md` |
| Host-driven reboot tool | `firmware/tools/cg_auto_reboot.py` | 5 reset thật qua USB (mở cổng + hạ DTR/RTS ⇒ `rst:0x15 USB_UART_CHIP_RESET` 6/6 lần trong raw log) — `espidf-run/` |

**Chưa được làm và không được giả vờ đã làm:** dán nhãn vật lý, bài cửa bằng firmware `#CG DOOR_EDGE` + `door-test.csv` (phiên runtime không có thao tác cửa), CSV consistency ≥600 mẫu từ firmware, và **tích hợp** BME280 vào firmware ESP-IDF (bài BME280 đã chạy là sketch Arduino standalone — xem §4.1). (Nạp/chạy firmware ESP-IDF nay **đã làm được** trên board thật — §14.)

**Trạng thái hiện tại: `W02_PARTIAL_EVIDENCE` — không phải `W02_PASS`.**

---

## 9. Phản biện độc lập (vòng 2) và cách xử lý

Vòng phản biện thứ hai — **không do tác giả thực hiện** — đọc trực tiếp lớp firmware/công cụ/hồ sơ của lần cập nhật này và chạy lại các lớp kiểm tra, rồi trả về: **BLOCKER F01–F04**, **MAJOR F05**, các **MINOR F06–F14** và **NOTE N01–N06**. Tất cả đều được đối chiếu với mã nguồn và **xác nhận là đúng**; không finding nào bị bác bỏ. Cách xử lý nằm trong chính PR này:

| Finding | Nội dung tóm tắt | Cách xử lý trong PR |
|---|---|---|
| F01–F04 (BLOCKER) | Hồ sơ in "3/3 PASS"/output kiểm tra không tái lập được khi `firmware_commit` còn là placeholder | Đã commit firmware thật (`0eb1f8a9…`; nay là `2a5a0da…` — xem §10), ghi SHA vào hồ sơ và dán lại output thật của lần chạy cuối (`firmware-implementation.md` §4) |
| F05 (MAJOR) | Công cụ đảo dấu chênh lệch cặp so với quy ước hồ sơ (DS1 - DS2 = -0.332) | Sửa công cụ sang `a - b`, thêm test khoá đúng quy ước |
| F06 | Công cụ reboot có thể đếm 5 khối dán lặp thành "5 reboot" | Yêu cầu `boot_id` phân biệt + `boot_count` tăng dần; thêm verdict `BOOT_METADATA_INVALID` |
| F07 | Parser SPARE dùng cờ `te` không tồn tại trong grammar v1 | SPARE hợp lệ ⇔ token khác `nan`; thêm test |
| F08 | Dòng `#CG ROMS` in `unknown=0` như một số đo | Bỏ `unknown=`; in `known=CG_ROLE_COUNT`; thêm kiểm tra tĩnh chống tái xuất hiện |
| F09 | Quy trình bench B1 không đủ thời lượng capture cho 5 reboot | Đổi thành `--seconds 90` |
| F10 | README công cụ ghi sai chữ in thật (`WINDOW NOT PROVEN`; quy kết `OPEN`/`CLOSED` cho cả stdout) | Cập nhật đúng chữ in: `WINDOW NOT USABLE`; chỉ khẳng định **dòng CSV** không mang `OPEN`/`CLOSED` |
| F11 | Kiểm tra tĩnh có thể bị lách bằng biến thể tương đương | Thêm kiểm tra ngữ nghĩa: thân hàm đọc không chứa `convert`; nhánh polarity đảo bị từ chối; quét BME280 mọi `.c`/`.h` |
| F12 | Validator chỉ cần một file firmware tồn tại trong commit | Commit firmware phải chứa đủ 5 module W02 + ROM bytes khớp `coldguard_config.h`; thiếu `git` ⇒ FAIL |
| F13 | Test hành vi là mô hình, không phải C đã biên dịch | Khai báo là giới hạn cục bộ (`firmware-implementation.md` §5.6) |
| F14 | `sensor-consistency-summary.md` mô tả sai hiện trạng repo ("chỉ có app_main.c bootstrap") | Cập nhật đúng: repo nay có firmware W02 đầy đủ, nhưng sketch bench cũ vẫn `NOT_IN_REPO` |
| N01 | Ghi "bộ đếm firmware" cho phiên cũ dù đó là sketch bench | Sửa thành "bộ đếm của sketch bench cũ" |
| N02 | Capture cửa trải nhiều boot có thể trộn bộ đếm | Công cụ từ chối (exit 1) trừ khi chọn `--boot N` (N sai → exit 2) |
| N03 | `sd` trả giá trị khi chỉ có một mẫu | Trả `None` khi n nhỏ hơn 2; thêm test |
| N04 | Trường chết `last_commit_us`/`last_edge_us` trong struct cửa | Đã xoá |
| N05 | Dòng log tràn bị cắt cụt | Thay bằng `#CG ERR msg=log_line_overflow` |
| N06 | Claim review trong PR body chưa phản ánh vòng 2 | Đã viết lại mục tương ứng trong `PR_BODY.md` |

**Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.**

---

## 10. Cập nhật lần 2 (2026-10-18): biên dịch thật trên CI

- Thêm workflow `.github/workflows/a-w02-espidf-build.yml`: chạy `idf.py set-target esp32s3 && idf.py build` bằng image `espressif/idf:v6.1` như README gốc, **không** flash / **không** serial / **không** chạy tải; upload log + artifact.
- Run đầu **FAIL** — lỗi thật, đã xử lý: `fatal error: driver/gpio.h: No such file or directory` (ESP-IDF v6.1: `esp_driver_gpio` không nằm trong requirements của `main`, và meta-component `driver` không re-export header này). Sửa `firmware/main/CMakeLists.txt` — commit firmware mới `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` (`PRIV_REQUIRES esp_driver_gpio`).
- Chạy lại toàn bộ kiểm tra cục bộ (**57 test + 39 check tĩnh + validator = 3/3 PASS**) rồi build lại: **SUCCESS**, 0 cảnh báo, `coldguard_firmware.bin` = 0x31360 bytes (81% trống).
- Bằng chứng đầy đủ (run URL, log, artifact, SHA-256, giới hạn): **`build-report-w02.md`**.
- Toàn bộ `firmware/main/*.c`/`*.h` giữa `0eb1f8a…` và `2a5a0da…` là **giống hệt từng byte**; chỉ `CMakeLists.txt` đổi.
- **Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.** Phần nạp + chạy thật vẫn `PENDING`; BME280 khi đó vẫn `PENDING_TEST` (nay đã bench-verified standalone — xem §11); 5 reboot vẫn `HARDWARE_RUN_PENDING`; CSV thô vẫn thiếu; nhãn vật lý vẫn `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`; H0 vẫn `DEFERRED`.

---

## 11. Cập nhật lần 3 (2026-10-18): bằng chứng bench BME280 thật

- Nhập 3 tệp bằng chứng bench BME280 vào `bme280/`: `bme280-bench-original.txt` (log Serial Monitor gốc; 13 795 bytes; SHA-256 `da24b6f0d487a4d677892e19c1299d18b207f5ad4f01d1b4635a475d8e606c23`), `bme280-bench.csv` (403 dòng dữ liệu; 13 139 bytes; SHA-256 `5ccddec17820dfda06c552407792dbdf2dde45f8c133d4abb0053ee3665cf43a`), `bme280-bench-report.md` (2 519 bytes; SHA-256 `c587bf6fce926caaa603a04fb7f987d4903e09e64892c3c2643b213fb92d7813`) — nguồn: `ColdGuard_W02_BME280_Evidence.zip` (7 537 bytes; SHA-256 `f243817e6f3d8ebc3747aadad59e58b3324e2af6ebb75fa1accbb86a75082016`). Tệp gốc được sao chép **nguyên byte** (SHA-256 khớp lại sau khi copy) và blob trong repo được ghim bằng `bme280/.gitattributes` (`* -text !eol`) để git không chuẩn hoá line-ending — các hash trong bảng trên đúng cả khi clone.
- Phương pháp (theo phiên test của người dùng): ESP32-S3, sketch Arduino + thư viện Adafruit BME280, COM4 @ 115200; SDA=GPIO21, SCL=GPIO33; I²C address `0x76`; chip-ID `0x60`; `CHIP_TYPE=BME280`; `BME280_INIT=PASS`.
- Xác minh độc lập từ **log gốc** (đọc trực tiếp, tính lại toàn bộ thống kê + đối chiếu CSV từng dòng): 403 mẫu liên tục 1–403, **0 trùng/0 thiếu**, `valid=1` toàn bộ (không có dòng `valid=0`); `uptime_ms` 2 816 → 404 816 (402 khoảng, **đều 1000 ms**, tổng **402 giây**); T 30.27–30.42 °C (mean 30.408, sd mẫu 0.017); RH 68.42–69.14 %RH (mean 68.513, sd 0.089); P 1011.97–1012.16 hPa (mean 1012.072, sd 0.037) — **khớp 100%** với báo cáo đi kèm; CSV **khớp từng dòng** với log (0 sai lệch).
- **`A-W02-06` → `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`.** Đây là bài test **BME280 standalone** trên bàn, **không** phải firmware ESP-IDF W02 (firmware W02 **không** có driver BME280 — cố ý). Phần vị trí gá cuối + xác nhận không bị ESP32/V1 sấy nóng vẫn `PENDING_TEST`; hồ sơ **không** tuyên bố firmware ESP-IDF đã đọc BME280.
- Giới hạn (khai báo tường minh): không chứng minh độ chính xác/hiệu chuẩn (không có chuẩn truy vết); không chứng minh hoạt động trong buồng lạnh hay tại vị trí lắp cuối; **không có wall-clock** — chỉ `uptime_ms` (thời gian từ lúc boot), không được suy diễn thành giờ thực; log chỉ mang `# TEST_STATUS=RUNNING` và **không** có dòng kết thúc — capture kết thúc tại mẫu 403; chưa có ảnh đấu dây/ngày giờ trong gói log.
- **Cảnh báo vận hành:** sketch Arduino đã **ghi đè** firmware trong MCU ⇒ phải **nạp lại** firmware ESP-IDF chính thức (B0) trước các bài B1–B4.
- **Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.**

## 12. Cập nhật lần 4 (2026-10-18): dữ liệu bench thô MC-38 thật

- Nhập 3 tệp bằng chứng bench MC-38 vào `mc38/`: `mc38-bench-original.txt` (log bench gốc, CRLF; 2 401 bytes; SHA-256 `38cdeef5f9bd6fb1e13b7183d0903ad48035dc15fdbc0a9c57e7c0b5c9fb4595`), `mc38-bench.csv` (48 dòng dữ liệu dẫn xuất; 1 994 bytes; SHA-256 `27690ac7a05d21dcc673dfa188e256ba5cb8e3c9e74d0d53e328f20929279619`), `mc38-bench-report.md` (báo cáo + phương pháp xác minh). Blob được ghim bằng `mc38/.gitattributes` (`* -text !eol`, log `whitespace=cr-at-eol`) — hash đúng cả khi clone.
- Phương pháp (phiên test MC-38 của người dùng): ESP32-S3 (sketch Arduino standalone — **không** phải firmware ESP-IDF W02), GPIO34, `DEBOUNCE_MS=40`; log có **dòng chú thích vật lý do người vận hành ghi tại test**: `# PHYSICAL=NEAR raw=0 stable=0`, `# PHYSICAL=FAR raw=1 stable=1`; tổng thời lượng 508 000 ms.
- **Xác minh độc lập từ log gốc** (đọc trực tiếp, tái dựng lại CSV bằng script và đối chiếu từng dòng): **48 cặp `RAW`/`STABLE`**, mỗi `STABLE` đúng **+40 ms** và cùng mức raw với `RAW` cùng cặp (48/48); `raw_edges` và `stable_edges` luỹ tiến **1..48** không thiếu/nhảy/trùng; chuyển mức xen kẽ đều `HIGH→LOW`/`LOW→HIGH`, không có chuyển trùng hướng; **24 chu kỳ NEAR→FAR** hoàn chỉnh; CSV tái dựng **khớp từng dòng** với `mc38-bench.csv` (0 sai lệch); không có cạnh dội bị gộp sai (cạnh thô liên tiếp gần nhất cách 476 ms ≫ 40 ms).
- **Polarity có dấu trong log:** `NEAR = LOW = CLOSED`, `FAR = HIGH = OPEN` — khớp 48/48 cặp với mức ổn định đã commit. **Firmware W02 trong repo vẫn giữ `CG_DOOR_POLARITY_CONFIRMED=0`** — lần cập nhật này **không** sửa firmware (đóng cờ chỉ nên làm sau khi firmware ESP-IDF chạy thật); ánh xạ ở đây là mức hồ sơ bench.
- **`A-W02-07` → `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`.** Giới hạn tường minh: sketch bench `NOT_IN_REPO`; bài bench dùng debounce **40 ms** (sketch) — firmware dùng `CG_DOOR_DEBOUNCE_MS=50` (khác biệt đã khai báo); chưa có `door-test.csv` theo schema `cg_build_door_csv.py` (yêu cầu firmware chạy thật); ảnh `w02_mc38_24_cycles.png` giờ chỉ còn vai trò truy vết phiên cũ (bộ đếm 21→24 của **phiên khác** — không quy đổi giữa hai phiên).
- **Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.**

## 13. Cập nhật lần 5 (2026-10-18): dữ liệu bench thô DS18B20 620 mẫu thật

- Nhập 3 tệp bằng chứng bench DS18B20 vào `ds18b20/` — nguồn `W02_DS18B20_20261018_194041.zip` do người dùng cung cấp: `ds18b20-serial-original.txt` (log Serial Monitor gốc, CRLF; 32 190 bytes; SHA-256 `44228795d48f223b1fdde619c184eccd1c34a56f4dd3d19fdfa12f239289b91c`), `sensor-consistency.csv` (620 dòng dữ liệu; 31 533 bytes; SHA-256 `99bdc21cfe1ecbf565b2602a16d7c60871e0efe67f4a2ddb885715b446fefe21`), `sensor-consistency-report.md` (báo cáo capture gốc; 1 323 bytes; SHA-256 `2d53af0983dc5e3035f2ec2e30afdabcf1dce4b0867bdb37b94e9d1cb3b428d7`), cộng `ds18b20-verification.md` (xác minh độc lập + provenance). Tệp gốc sao chép **nguyên byte** (hash khớp lại sau copy); blob ghim bằng `ds18b20/.gitattributes` (`* -text !eol`) — hash đúng cả khi clone.
- Phương pháp (theo phiên test của người dùng): ESP32-S3, sketch Arduino/OneWire/DallasTemperature standalone (**không** phải firmware ESP-IDF W02), COM4 @ 115200; capture bắt đầu 2026-10-18T12:40:41 UTC.
- **Xác minh độc lập từ log gốc** (đọc trực tiếp, tính lại toàn bộ + đối chiếu CSV từng dòng): 620 mẫu liên tục 1–620 (**0 trùng, 0 thiếu**, 0 lỗi parse); `uptime_ms` **42 014 → 661 014** (619 khoảng, **đều 1000 ms**, tổng **619 000 ms** — đạt "≥10 phút" thật sự theo mốc uptime); **4 vai trò hợp lệ 620/620** (tổng 2 480/2 480 cờ valid=1, không có valid=0); **0 giá trị sentinel** (85 °C power-on, −127, ngoài dải); T 29.8785/30.1879/29.5683/29.9218 °C (sd mẫu 0.021467/0.016275/0.023374/0.028058); chênh lệch cặp T1−T2 −0.309375, T1−T3 +0.310181, **T2−T3 +0.619556 (lớn nhất)**; chênh lệch tức thời (max−min) lớn nhất **0.6875 °C** — mọi số khớp 100% với báo cáo capture đi kèm; CSV **khớp từng dòng** (0 sai lệch).
- **`A-W02-05` → `BENCH DATA VERIFIED — 620 RAW SAMPLES CAPTURED`.** Đây là consistency check trên bàn của **sketch standalone** — **không** phải firmware ESP-IDF (đường `sample,uptime_ms,…`, không phải `#CG SAMPLE`); **không** tuyên bố nhịp/firmware đo được và **không** tuyên bố A-W02-04 hay W02 PASS.
- **Giới hạn ROM (khai báo đúng trạng thái):** công cụ capture tự báo **`ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG`** — raw log chứa **0 dòng ROM** (`# W02 START` và `# W02 DONE samples=620` chỉ là event line); nguyên nhân nhận diện — sketch in enumeration khi khởi động, capture Python gọi `port.reset_input_buffer()` khi mở cổng. **Không chèn dòng ROM đầu log, không bỏ cảnh báo.** Điều kiện đặt: bốn ROM đã đóng băng vào `coldguard_config.h` (đối chiếu tự động CRC8 — `cg_check_firmware.py` PASS) và đã thấy trong **bằng chứng độc lập phiên khác** (`w02_rom_enumeration_4_devices.png`: T1 `287088CA00000051`, T2 `28AEBF2200000006`, T3 `28CBE9CA00000072`, SPARE `283BE5C9000000A9`, cả 4 `PRESENT=1`). Trạng thái ROM: **`ROM IDENTITY VERIFIED BY SEPARATE EVIDENCE — SAME-CAPTURE CONFIRMATION PENDING`**; phần xác minh **cùng một boot** sẽ làm trong bài 5 reboot firmware ESP-IDF (`A-W02-03`, log `#CG ROM` in đủ 4 ROM mỗi boot) — **không yêu cầu đo lại 10 phút**. *(Resolve ở cập nhật 7 — §14.)*
- **Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.**

## 14. Cập nhật lần 7 (2026-10-18): flash firmware ESP-IDF thật + 5 reboot identity + runtime ~1 Hz

Đầy đủ provenance ở `espidf-run/flash-provenance.md` / `reboot-verification.md` /
`runtime-cadence.md`. Tóm tắt trung thực:

- **MCU xác minh chắc chắn:** ESP32-S3 (QFN56) rev v0.2, native USB-Serial/JTAG, MAC
  `e0:72:a1:bc:cf:4c` (khớp instance USB `VID_303A&PID_1001`), flash thực **4 MB** (build
  layout 2 MB nằm gọn — không tự đổi cấu hình build). COM4; không có capture nào đang giữ cổng;
  backup **đầy đủ 4 MB flash** trước khi flash (SHA-256 `cee6d3f7…ab42`, rollback bằng 1 lệnh
  `esptool write-flash`); người dùng xác nhận flash một lần.
- **Firmware nạp = đúng firmware trong repo:** artifact run `39134178842` (head `1b93f572`,
  merge preview `44f4643` — tree firmware **giống branch**), SHA-256 3/3 file khớp
  `30-artifacts.txt`; `ELF file SHA256` in lúc boot khớp ELF trong artifact
  (`1a47211f41e0cdb46b28da550ef94557d7aa9c0c91f40c8bf15c7351e44a8252`); flash
  `0x0/0x8000/0x10000` đúng `flasher_args.json`, 3/3 `Hash of data verified` —
  `espidf-run/flash-original-log.txt`.
- **Lỗi runtime thật (một lần flash firmware `a8f5c58` trước đó):** board boot nhưng in
  **0 dòng `#CG ROM`/`#CG SAMPLE`** và IDLE0 watchdog dội liên tục — nguyên nhân
  `vTaskDelay(pdMS_TO_TICKS(5)) == 0` khi `CONFIG_FREERTOS_HZ=100` ⇒ task `cg_door` quay
  vô hạn, `cg_sensor` chết đói. Fix tối thiểu commit `1b93f572` (1 tick tối thiểu như
  `sensor_task` đã làm); build lại trên CI rồi flash lại. Bug và fix được ghi tường minh ở
  `firmware-implementation.md` §6.
- **5 reboot thật (host-driven, không bấm nút):** phương thức đã thử nghiệm trên chính
  board: mở cổng rồi hạ DTR/RTS ⇒ `rst:0x15 (USB_UART_CHIP_RESET)` + `boot:0x8` — banner
  xuất hiện **6/6 reset** trong raw log (phương án RTS-only kiểu esptool **không** tác động
  tới app đang chạy — ghi nhận để tránh lặp). Verifier chính thức:
  **`REBOOT IDENTITY: PASS (6 boots, roles stable, boot metadata consistent)`** —
  `boot_id` 6 giá trị phân biệt, NVS `boot_count` **5→10 tăng liên tục**, `mismatches=[]`.
  Script độc lập tự tính lại **gồm cả SPARE**: 6/6 boot in đủ 4 ROM đúng bản đồ đóng băng,
  `#CG ROMS required_present=3/3 known=4 known_present=4`, 4/4 `present=1`.
  → **A-W02-03 → `HARDWARE VERIFIED — 6 BOOT IDENTITY STABLE`**; **ROM same-boot của
  A-W02-05 đã resolve** (mỗi boot firmware in đủ 4 ROM, không cần đo lại sketch 620 mẫu).
- **Runtime firmware thật:** 252 dòng `#CG SAMPLE`, 246 interval đo được đều trong
  [990, 1000] ms (mean **999.756 ms**, median 1000) — nhịp ~1 Hz **đo được**; 252/252
  `t1=t2=t3=1` + `thermal=VALID` + SPARE luôn có giá trị; 0 `#CG ERR`/0 `nan`/sentinel;
  `door_raw=1` bất động suốt phiên (không thao tác cửa) — **không** tuyên bố `#CG DOOR_EDGE`.
  → **A-W02-04 → `HARDWARE RUNTIME VERIFIED — 252 SAMPLES @ ~1 HZ`**; CSV consistency
  ≥600 mẫu từ firmware vẫn `PENDING` (phiên ngắn không là consistency window).
- `firmware_commit` hồ sơ nâng lên **`1b93f572ed3f06a3030292b2515fa38bcaf75ca7`**
  (commit trước đó `2a5a0dac…` vẫn đúng cho map ROM — ROM bytes không đổi).
- **Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.** Lý do còn lại:
  nhãn vật lý (`A-W02-02`), bài cửa firmware + `door-test.csv` + cờ polarity (`A-W02-07`),
  H0 deferred (`A-W02-01`), CSV consistency từ firmware ≥600 mẫu, ảnh setup/đặt đầu dò,
  sketch bench `NOT_IN_REPO`, `hardware_config_id` `NOT_ASSIGNED`.
