# W02 acceptance — Member A

Tệp này là **nguồn trạng thái duy nhất** cho nghiệm thu W02 của Member A. Các file khác trong `evidence/A/W02/` chỉ cung cấp bằng chứng và **không** lặp lại checklist.

**Snapshot:** 2026-10-18 (cập nhật 2: build CI) · **Phiên bản hồ sơ:** W02 · **hardware_config_id:** `NOT_ASSIGNED` · **firmware commit (repo):** `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` · **build ESP-IDF thật (CI):** `SUCCESS — esp32s3` (`build-report-w02.md`) · **firmware sketch bench (nguồn 3 ảnh):** `NOT_IN_REPO`

**Trạng thái tổng: `W02 NOT PASS` — `W02_PARTIAL_EVIDENCE`.** Việc mở PR **không** đồng nghĩa W02 đã PASS. Việc firmware **biên dịch thành công trên CI** (§10) cũng **không** thay đổi trạng thái tổng: firmware chưa được nạp và chưa chạy trên board.

---

## 1. Acceptance matrix — A-W02-01 … A-W02-07 (`docs/05A §11`)

| ID | Hạng mục canonical | Tiêu chí | Bằng chứng hiện có | Trạng thái | Phần còn thiếu |
|---|---|---|---|---|---|
| **A-W02-01** | Mechanical H0 (`HW-H0-01`, `HW-H0-02`) | V1/TEC gắn chắc, không cấp nguồn TEC; đóng băng vị trí T1/T2/T3, BME, MC-38; không linh kiện lỏng, không hướng mơ hồ | **Không có** | **`DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING`** | Ảnh H0, checklist lắp ráp, sketch vị trí tương đối; quyết định lịch của leader |
| **A-W02-02** | DS18B20 enumeration | Phát hiện đúng ROM mong đợi, ghi ánh xạ chính xác | `w02_rom_enumeration_4_devices.png`, `sensor-rom-map.yaml`, ROM map **đã được ghi cứng vào firmware** (`coldguard_config.h`, đối chiếu tự động với YAML + CRC8) | **`ROM→ROLE FROZEN — PHYSICAL LABEL PENDING_USER_LABELING`** | Canonical mong đợi **3** ROM, thực tế **4**; lệch số lượng cần leader xác nhận (kế thừa `CR-A-W01-04`). Đầu dò chưa được dán nhãn vật lý → `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` |
| **A-W02-03** | Reboot identity proof | ≥5 chu kỳ reboot/discovery giữ nguyên ROM→role | **Không có log thật.** Đã implement cơ chế: `#CG BOOT boot_id=… boot_count=…` (NVS) + khối `#CG ROM` mỗi lần boot + công cụ `firmware/tools/cg_verify_reboots.py` (đã test tự động: 5 boot ổn định + `boot_id` phân biệt + `boot_count` tăng dần → PASS; đổi ROM/thiếu vai trò/khối lặp/`boot_count` không tăng → FAIL) | **`IMPLEMENTED — HARDWARE RUN PENDING`** | Chạy 5 lần reset trên board và lưu log. **Không** được suy ra từ ảnh enumeration một phiên; **không** đánh dấu PASS trước khi có log thật |
| **A-W02-04** | Acquisition implementation | Shared conversion → đọc từng ROM; snapshot ~1 Hz; xử lý lỗi đọc | Log bench (shared-conversion quan sát được: một khối in chứa cả 4 đầu dò + `Valid: 4/4`) · **firmware W02 đã được implement trong repo**: `firmware/main/cg_ds18b20.c` (broadcast `SKIP_ROM`+`CONVERT_T`, đọc theo ROM cố định, `nan` khi lỗi) · **đã biên dịch thật trên CI** (ESP-IDF v6.1, `esp32s3`, SUCCESS, 0 cảnh báo — `build-report-w02.md`) | **`IMPLEMENTED — COMPILE VERIFIED (CI) — HARDWARE RUN PENDING`** | 1) Cần một lần chạy thật để có log `#CG SAMPLE` có `uptime_ms` (nhịp ~1 Hz sẽ **đo được**, không còn là suy luận) — build đã xong, chỉ còn nạp/chạy; 2) **nguồn sketch bench** sinh ra 3 ảnh vẫn không nằm trong repo ⇒ shared conversion của *phiên bench cũ* vẫn `RAW_EVIDENCE_PENDING` |
| **A-W02-05** | Inter-sensor consistency | ≥10 phút ở ~1 Hz; có mean, SD, chênh lệch cặp, chênh lệch lớn nhất | `w02_ds18b20_600_samples_summary.png`, `sensor-consistency-summary.md` (thống kê đã được reviewer độc lập tính lại: khớp 100%) · công cụ `firmware/tools/cg_build_sensor_csv.py` (đã test: 600 mẫu → CSV + mean/SD/pairwise/max; `nan` → ô rỗng; dưới `--min-samples` → `WINDOW NOT USABLE` + exit 1) | **`STATISTICS_VERIFIED_FROM_SCREENSHOT — RAW CSV MISSING`** | Thiếu `sensor-consistency.csv` thô của **phiên cũ** ⇒ không thể tính lại độc lập từ dữ liệu gốc; thiếu timestamp ⇒ nhịp/độ dài của phiên cũ vẫn là suy luận (phiên mới sẽ có `uptime_ms`). Điều kiện đặt đầu dò không được ghi lại. **Không** phải calibration (không có chuẩn truy vết) |
| **A-W02-06** | BME280 | I²C address, T/RH hợp lý, không bị ESP32/V1 sấy nóng | **Không có** | **`PENDING_TEST — USER PLANS TO COMPLETE TONIGHT`** | Toàn bộ: chip-ID, I²C, T/RH, vị trí gá. Member A sẽ **bổ sung commit mới vào cùng PR** sau khi test thật |
| **A-W02-07** | MC-38 | ≥20 chu kỳ mở/đóng; semantic OPEN/CLOSED khớp vật lý; transition tin cậy (debounce) | `w02_mc38_24_cycles.png`, `door-test-summary.md` · đã implement: `firmware/main/cg_door.c` (debounce cấu hình được `CG_DOOR_DEBOUNCE_MS=50`, đếm `raw_edges`/`discarded_edges`, ghi `#CG DOOR_EDGE` theo µs) + `firmware/tools/cg_build_door_csv.py` (bắt buộc `--open-level`; không có thì mọi `state=UNVERIFIED` và exit 1; capture trải nhiều boot bị từ chối cho tới khi chọn `--boot N`) | **`PARTIAL`** | Số chu kỳ **đạt** (24 ≥ 20, tính theo **bộ đếm của sketch bench cũ** — sketch `NOT_IN_REPO`, số hiển thị trên Serial Monitor của phiên đó). Còn thiếu: (1) `raw → OPEN/CLOSED` chưa được quan sát vật lý (`PENDING_POLARITY_CONFIRMATION`); (2) bằng chứng debounce trên phần cứng thật (số cạnh thô/chu kỳ) |

---

## 2. Tiêu chí PASS canonical (`docs/05A §11`)

| Tiêu chí | Trạng thái | Căn cứ / phần thiếu |
|---|---|---|
| 3 unique stable ROMs | **`PARTIAL`** | Có 4 ROM **phân biệt** (thoả `PHY-DS-001` về tính duy nhất của 3 vai trò) và ba ROM này **đã được ghi cứng theo vai trò trong firmware** (không phụ thuộc thứ tự discovery); nhưng con số **không khớp** canonical "3" và tính **ổn định qua reboot** vẫn chưa có log thật |
| no silent remap across reboot | **`IMPLEMENTED — HARDWARE RUN PENDING`** | Firmware W02 đọc theo ROM cố định (không dùng chỉ số discovery) và công cụ kiểm tra đã test tự động; **chưa** có log 5 reboot thật ⇒ chưa tuyên bố thoả |
| BME responds | **`NOT TESTED`** | `A-W02-06` chờ test tối nay |
| door semantic correct | **`IMPLEMENTED — POLARITY OBSERVATION PENDING`** | Firmware **không** giả định HIGH/LOW nào là OPEN (`CG_DOOR_POLARITY_CONFIRMED=0` ⇒ `UNVERIFIED`); công cụ **bắt buộc** `--open-level` do người vận hành quan sát. Chưa có quan sát vật lý ⇒ chưa tuyên bố thoả |
| mechanical placement reproducible | **`NOT VERIFIED`** | `A-W02-01` hoãn; chưa có ảnh vị trí/đầu dò được dán nhãn |

**Kết luận:** không tiêu chí nào trong hai bảng trên là `PASS` đầy đủ. Ba tiêu chí đã chuyển từ "chưa có gì" sang **đã implement + có công cụ kiểm chứng đã test tự động**, nhưng **chưa** chạy trên phần cứng.

---

## 3. Deliverables canonical (`docs/05A §11`)

| Deliverable | Trạng thái | File / ghi chú |
|---|---|---|
| H0 mechanical photos | **MISSING** | Thuộc `A-W02-01` đang hoãn |
| `sensor-rom-map.yaml` | **PRESENT (DRAFT)** | Có; trạng thái `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`; nay khớp từng byte với `firmware/main/coldguard_config.h` (kiểm tra tự động) |
| `sensor-placement.png` | **MISSING** | Không có bản vẽ/ảnh vị trí. **Không** được vẽ lại từ trí nhớ |
| H1 serial log | **PARTIAL** | Chỉ có 3 ảnh chụp cửa sổ Serial Monitor, không có file log; timestamp bị tắt. Firmware mới in `uptime_ms` nên phiên sau sẽ có log có mốc thời gian thật |
| `sensor-consistency.csv` | **GENERATOR READY — REAL RUN PENDING** | Chưa có file; `firmware/tools/cg_build_sensor_csv.py` dựng CSV từ log thật (đã test tự động, `nan` → ô rỗng, dưới `--min-samples` → `WINDOW NOT USABLE` + exit 1) |
| `door-test.csv` | **GENERATOR READY — REAL RUN PENDING** | Chưa có file; `firmware/tools/cg_build_door_csv.py` dựng CSV + thống kê dội (bắt buộc `--open-level`) |
| Firmware W02 trong repo | **IMPLEMENTED — CI COMPILE PASS (ESP32-S3)** | `firmware/main/` (7 module C) + workflow `.github/workflows/a-w02-espidf-build.yml` (image `espressif/idf:v6.1`, README gốc). Build thật: **SUCCESS**, 0 cảnh báo, artifact + SHA-256 trong `build-report-w02.md`. Máy cục bộ vẫn không có ESP-IDF/Docker; firmware chưa được nạp |
| Công cụ + test | **PRESENT, TESTED** | `firmware/tools/` + 57 test `unittest` PASS + 39 kiểm tra tĩnh PASS (`py firmware/tools/run_all_checks.py`) |

**Không** tạo CSV giả để đủ danh sách. Các mục `MISSING` ở lại trạng thái thiếu cho tới khi có dữ liệu thật.

---

## 4. Hạng mục chưa thực hiện (tường minh, không che giấu)

### 4.1 `A-W02-06` — BME280

- **Trạng thái:** `PENDING_TEST — USER PLANS TO COMPLETE TONIGHT`.
- **Hiện có:** không có kết quả chip-ID, không có kết quả I²C, không có T/RH.
- **Cam kết:** Member A sẽ gửi **commit mới vào cùng PR này** sau khi test thật xong.
- **Quy tắc:** **không** được đánh dấu PASS trước khi có kết quả thật. Việc review PR này **không** phải là phê duyệt BME280.

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

- [ ] **`A-W02-06`:** kết quả BME280 thật (chip-ID, I²C address, T/RH hợp lý, vị trí gá) — commit bổ sung vào cùng PR.
- [ ] **`A-W02-03`:** chạy 5 lần reset trên board và lưu log; xác minh bằng `py firmware/tools/cg_verify_reboots.py <log>` (cơ chế + công cụ đã xong, chỉ còn lần chạy thật).
- [ ] **`A-W02-05`:** chạy phiên ≥10 phút và dựng `sensor-consistency.csv` bằng công cụ (phiên cũ vẫn thiếu CSV thô ⇒ không tính lại được từ dữ liệu gốc).
- [ ] **`A-W02-07`:** quan sát vật lý "cửa mở → mức thô nào" rồi chạy công cụ với `--open-level`; ghi lại số cạnh thô/chu kỳ làm bằng chứng debounce.
- [ ] **`A-W02-02`:** dán nhãn vật lý T1/T2/T3 (+ SPARE) trên đầu dò thật, có ảnh nhãn; nâng trạng thái khỏi `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`.
- [ ] **`A-W02-01`:** quyết định của leader về H0 (giữ trong W02 hay dời), kèm ảnh/checklist nếu chuyển sang W07.
- [ ] **`A-W02-04`:** nạp firmware **đã build trên CI** (`build-report-w02.md`) và chạy thật để có log `#CG SAMPLE`; **nguồn sketch bench** sinh ra 3 ảnh cũ vẫn cần nếu muốn truy nguyên chính xác phiên cũ.
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
| Một lệnh chạy tất cả | `firmware/tools/run_all_checks.py` | 3/3 lớp PASS trên máy này (57 test + 39 check tĩnh + validator hồ sơ, sau commit firmware `2a5a0da…`) |
| Build ESP-IDF thật (CI, không cần máy cục bộ) | `.github/workflows/a-w02-espidf-build.yml` | `espressif/idf:v6.1` + `esp32s3`, **SUCCESS**, 0 cảnh báo — run `39117530768` (chi tiết: `build-report-w02.md`) |

**Chưa được làm và không được giả vờ đã làm:** nạp firmware, chạy bất kỳ bài test phần cứng nào, dán nhãn vật lý, test BME280. (Biên dịch firmware nay **đã làm được**: CI thật với ESP-IDF v6.1 — `build-report-w02.md`; máy cục bộ vẫn không có ESP-IDF/Docker.)

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
- **Trạng thái tổng không đổi: `W02_PARTIAL_EVIDENCE` — NOT PASS.** Phần nạp + chạy thật vẫn `PENDING`; BME280 vẫn `PENDING_TEST`; 5 reboot vẫn `HARDWARE_RUN_PENDING`; CSV thô vẫn thiếu; nhãn vật lý vẫn `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`; H0 vẫn `DEFERRED`.
