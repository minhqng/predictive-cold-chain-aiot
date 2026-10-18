# W02 acceptance — Member A

Tệp này là **nguồn trạng thái duy nhất** cho nghiệm thu W02 của Member A. Các file khác trong `evidence/A/W02/` chỉ cung cấp bằng chứng và **không** lặp lại checklist.

**Snapshot:** 2026-10-18 · **Phiên bản hồ sơ:** W02 · **hardware_config_id:** `NOT_ASSIGNED` · **firmware commit:** `NOT_RECORDED`

**Trạng thái tổng: `W02 NOT PASS` — `W02_PARTIAL_EVIDENCE`.** Việc mở PR **không** đồng nghĩa W02 đã PASS.

---

## 1. Acceptance matrix — A-W02-01 … A-W02-07 (`docs/05A §11`)

| ID | Hạng mục canonical | Tiêu chí | Bằng chứng hiện có | Trạng thái | Phần còn thiếu |
|---|---|---|---|---|---|
| **A-W02-01** | Mechanical H0 (`HW-H0-01`, `HW-H0-02`) | V1/TEC gắn chắc, không cấp nguồn TEC; đóng băng vị trí T1/T2/T3, BME, MC-38; không linh kiện lỏng, không hướng mơ hồ | **Không có** | **`DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING`** | Ảnh H0, checklist lắp ráp, sketch vị trí tương đối; quyết định lịch của leader |
| **A-W02-02** | DS18B20 enumeration | Phát hiện đúng ROM mong đợi, ghi ánh xạ chính xác | `w02_rom_enumeration_4_devices.png`, `sensor-rom-map.yaml` | **`PARTIAL`** | Canonical mong đợi **3** ROM, thực tế **4**; lệch số lượng cần leader xác nhận (kế thừa `CR-A-W01-04`). Đầu dò chưa được dán nhãn vật lý → `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` |
| **A-W02-03** | Reboot identity proof | ≥5 chu kỳ reboot/discovery giữ nguyên ROM→role | **Không có** | **`RAW_EVIDENCE_PENDING`** | Log thật của 5 chu kỳ. **Không** được suy ra từ ảnh enumeration một phiên |
| **A-W02-04** | Acquisition implementation | Shared conversion → đọc từng ROM; snapshot ~1 Hz; xử lý lỗi đọc | Log bench hiển thị một khối in chứa cả 4 đầu dò + `Valid: 4/4` | **`PARTIAL`** | Nguồn firmware của sketch bench **không có trong repo** ⇒ chưa kiểm chứng được shared conversion bằng code. Nhịp ~1 Hz là **suy luận**, không có timestamp. Chưa có bài test một đầu dò lỗi/mất để chứng minh error handling |
| **A-W02-05** | Inter-sensor consistency | ≥10 phút ở ~1 Hz; có mean, SD, chênh lệch cặp, chênh lệch lớn nhất | `w02_ds18b20_600_samples_summary.png`, `sensor-consistency-summary.md` | **`PARTIAL`** | Thiếu `sensor-consistency.csv` thô ⇒ không thể tính lại độc lập; thiếu timestamp ⇒ không chứng minh được nhịp và độ dài; điều kiện đặt đầu dò không được ghi lại. **Không** phải calibration (không có chuẩn truy vết) |
| **A-W02-06** | BME280 | I²C address, T/RH hợp lý, không bị ESP32/V1 sấy nóng | **Không có** | **`PENDING_TEST — USER PLANS TO COMPLETE TONIGHT`** | Toàn bộ: chip-ID, I²C, T/RH, vị trí gá. Member A sẽ **bổ sung commit mới vào cùng PR** sau khi test thật |
| **A-W02-07** | MC-38 | ≥20 chu kỳ mở/đóng; semantic OPEN/CLOSED khớp vật lý; transition tin cậy (debounce) | `w02_mc38_24_cycles.png`, `door-test-summary.md` | **`PARTIAL`** | Số chu kỳ **đạt** (24 ≥ 20). Còn thiếu: freeze `raw → OPEN/CLOSED` (`PENDING_POLARITY_CONFIRMATION`) và bằng chứng debounce |

---

## 2. Tiêu chí PASS canonical (`docs/05A §11`)

| Tiêu chí | Trạng thái | Căn cứ / phần thiếu |
|---|---|---|
| 3 unique stable ROMs | **`PARTIAL`** | Có 4 ROM **phân biệt** (thoả `PHY-DS-001` về tính duy nhất của 3 vai trò), nhưng con số **không khớp** canonical "3" và tính **ổn định** chưa được chứng minh (không có log reboot) |
| no silent remap across reboot | **`NOT VERIFIED`** | Không có log reboot nào. Tài liệu này **không** tuyên bố đã thoả |
| BME responds | **`NOT TESTED`** | `A-W02-06` chờ test tối nay |
| door semantic correct | **`NOT VERIFIED`** | Ảnh chỉ có mức thô `LOW/HIGH`; chưa có ánh xạ `OPEN/CLOSED` |
| mechanical placement reproducible | **`NOT VERIFIED`** | `A-W02-01` hoãn; chưa có ảnh vị trí/đầu dò được dán nhãn |

**Kết luận:** không tiêu chí nào trong hai bảng trên là `PASS` đầy đủ. Mức cao nhất đạt được là `PARTIAL`.

---

## 3. Deliverables canonical (`docs/05A §11`)

| Deliverable | Trạng thái | File / ghi chú |
|---|---|---|
| H0 mechanical photos | **MISSING** | Thuộc `A-W02-01` đang hoãn |
| `sensor-rom-map.yaml` | **PRESENT (DRAFT)** | Có; trạng thái `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` |
| `sensor-placement.png` | **MISSING** | Không có bản vẽ/ảnh vị trí. **Không** được vẽ lại từ trí nhớ |
| H1 serial log | **PARTIAL** | Chỉ có 3 ảnh chụp cửa sổ Serial Monitor, không có file log; timestamp bị tắt |
| `sensor-consistency.csv` | **MISSING** | Chỉ có 9 dòng CSV hiển thị trong ảnh summary |
| `door-test.csv` | **MISSING** | Chỉ có 6 dòng log hiển thị |

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
- [ ] **`A-W02-03`:** log ≥5 chu kỳ reboot/discovery chứng minh ROM→role giữ nguyên.
- [ ] **`A-W02-05`:** `sensor-consistency.csv` thô (hoặc serial log bật timestamp) đủ để tính lại mean/SD độc lập.
- [ ] **`A-W02-07`:** freeze bảng `raw input → OPEN/CLOSED` + ghi lại thời gian chống dội (debounce).
- [ ] **`A-W02-02`:** dán nhãn vật lý T1/T2/T3 (+ SPARE) trên đầu dò thật, có ảnh nhãn; nâng trạng thái khỏi `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`.
- [ ] **`A-W02-01`:** quyết định của leader về H0 (giữ trong W02 hay dời), kèm ảnh/checklist nếu chuyển sang W07.
- [ ] **`A-W02-04`:** đưa nguồn firmware bench (hoặc firmware W02 chính thức) vào repo để kiểm chứng shared conversion và nhịp 1 Hz; ghi `firmware_commit`.
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

**Trạng thái hiện tại: `W02_PARTIAL_EVIDENCE` — không phải `W02_PASS`.**
