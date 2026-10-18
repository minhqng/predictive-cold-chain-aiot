# [A-W02] Sensor Foundation, ROM Mapping and Bench Evidence

> **⚠️ W02 NOT PASS — READ FIRST.** Bộ chứng cứ này là `W02_PARTIAL_EVIDENCE`, **không** phải nghiệm thu W02. Mở PR này **không** đồng nghĩa W02 đã PASS. Hai hạng mục còn treo: `A-W02-06` BME280 (`PENDING_TEST`, sẽ bổ sung bằng commit mới vào chính PR này) và `A-W02-01` H0 mechanical (`DEFERRED`, chờ trưởng nhóm quyết định lịch).

**Base:** `main` · **Head:** `feat/a-w02-sensor-foundation` · **Loại:** NORMAL PR (Ready for Review — không phải Draft)
**Issue/pack:** `A-W02-01` … `A-W02-07`
**Parent docs:** `docs/04 §17` (W02), `docs/05A §11` (Member A W02), `docs/03 §14–§15` (`HW-H0-01/02`, `SEN-H1-01…05`), `docs/01 §6.4–§6.6` (identity contract)
**Reviewer bắt buộc:** Member D (`docs/04 §3.3`: physical wiring / pin / sensing)
**Hardware config affected?:** Chưa — `hardware_config_id` vẫn `NOT_ASSIGNED`. PR này ghi nhận danh tính cảm biến, không thay đổi BOM freeze.
**Evidence path:** `evidence/A/W02/`
**Trạng thái W02:** **`W02_PARTIAL_EVIDENCE` — KHÔNG phải W02 PASS.** Mở PR này **không** đồng nghĩa W02 đã nghiệm thu.

---

## 1. Member A đã hoàn thành những gì

- **Bản đồ ROM → vai trò DS18B20** (`sensor-rom-map.yaml`): T1 gần cửa `287088CA00000051`, T2 trung tâm `28AEBF2200000006`, T3 đối diện cửa `28CBE9CA00000072`, và một đầu dò dự phòng `283BE5C9000000A9`. Trạng thái ghi đúng là `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` — **đầu dò vật lý chưa được dán nhãn**, không tự nhận là đã xong.
- **Tổng hợp inter-sensor consistency** (`sensor-consistency-summary.md`): bảng 600 mẫu/đầu dò, chênh lệch trung bình từng cặp và chênh lệch lớn nhất (0.603 °C, DS2 vs DS3), kèm phân tích vì sao các SD (0.018–0.031 °C) thấp hơn một bước lượng tử 12-bit. Ghi rõ đây là **consistency check, KHÔNG phải calibration**.
- **Tổng hợp bài test cửa MC-38** (`door-test-summary.md`): đọc bộ đếm thô, kiểm tra số học `cycles = floor(transitions/2)`, và đối chiếu tiêu chí ≥20 chu kỳ (đạt 24).
- **Hồ sơ truy xuất nguồn ảnh** (`screenshot-provenance.csv`) + **kiểm tra cấu trúc tự động** (`validate_w02.py`) + **acceptance matrix A-W02-01…07** (`acceptance.md`) và `README.md` của bộ chứng cứ.

## 2. Bằng chứng thật tương ứng

Ba ảnh log gốc của phiên bench W02, do người dùng cung cấp qua archive `ColdGuard_A_W02_Existing_Test_Screenshots.zip` (81 661 bytes, SHA-256 `383CBB4A…B97429`), được sao chép **nguyên byte** (không crop, không nén lại, không chỉnh sửa):

| Ảnh | Nội dung thật | Ý nghĩa |
|---|---|---|
| `w02_rom_enumeration_4_devices.png` | COM4 Serial Monitor: `DS18B20 found: 4`, 4 ROM hex, `MC38 initial: HIGH`, `PASS: 4 DS18B20 detected`, các khối nhiệt độ `DS1..DS4` với `Valid: 4/4` | 4 ROM phân biệt, cả 4 đọc được giá trị trong cùng phiên |
| `w02_ds18b20_600_samples_summary.png` | 9 dòng CSV cuối (592–600) + `# W02 SUMMARY`: `valid=600/600` và `mean/sd/min/max` cho S1–S4 + `# W02 TEST FINISHED` | Kết quả summary **được hiển thị** cho 600 mẫu/đầu dò |
| `w02_mc38_24_cycles.png` | 6 dòng `MC38: LOW/HIGH \| transitions: 43..48 \| cycles: 21..24`, xen kẽ khối nhiệt độ | Bộ đếm chuyển mức đạt **24 chu kỳ** trong phiên bench |

Số liệu chi tiết (mean 29.882/30.214/29.611/29.935 °C; sd 0.028/0.031/0.026/0.018 °C) được ghi nguyên văn và tính lại công khai trong `sensor-consistency-summary.md`.

**Ảnh xác nhận kết quả đã được hiển thị — ảnh KHÔNG thay thế CSV 600 dòng, KHÔNG thay thế timestamp thật, và ảnh MC-38 KHÔNG tự chứng minh debounce hay polarity.** Không có dữ liệu, log hay kết quả test nào được tạo mới trong PR này.

## 3. BME280 (A-W02-06) — chờ test tối nay

- **Trạng thái:** `PENDING_TEST — USER PLANS TO COMPLETE TONIGHT`.
- **Hiện có:** không có kết quả chip-ID, không có kết quả I²C, không có T/RH.
- Member A sẽ **bổ sung một commit mới vào chính PR này** sau khi test BME280 thật xong. PR này vì vậy được tạo ở trạng thái **Ready for Review** nhưng **chưa** đủ điều kiện để chốt W02.
- **Không** có bất kỳ dòng nào trong PR này đánh dấu BME280 PASS.

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
| Log/CSV dữ liệu thô 600 dòng | **`RAW_EVIDENCE_PENDING`** | Chỉ có 9 dòng CSV hiển thị trong ảnh; **không có** `sensor-consistency.csv` ⇒ không thể tính lại mean/SD độc lập |
| `door-test.csv` thô | **`RAW_EVIDENCE_PENDING`** | Chỉ có 6 dòng log hiển thị; không có file |
| Log 5 chu kỳ reboot (A-W02-03) | **`RAW_EVIDENCE_PENDING`** | Chưa có log nào ⇒ `no silent remap across reboot` **chưa** được chứng minh |
| Nhãn vật lý T1/T2/T3 | **PENDING** | Đầu dò chưa được nhận diện/dán nhãn ⇒ leader review "chỉ tay vào T1/T2/T3" chưa thực hiện được |
| Timestamp | **KHÔNG có** | Serial Monitor để `Show timestamp = OFF`; nhịp ~1 Hz và độ dài ≥10 phút chỉ là **suy luận**, chưa chứng minh bằng đồng hồ |
| Polarity MC-38 (`raw → OPEN/CLOSED`) | **`PENDING_POLARITY_CONFIRMATION`** | Ảnh chỉ có mức thô `LOW/HIGH`; không suy ra được ngữ nghĩa cửa từ cách đấu dây chưa xác nhận |
| Debounce MC-38 | **Chưa đo** | Không có thời gian giữa các lần đổi mức, không có bộ đếm bounce |
| Nguồn firmware sketch bench (A-W02-04) | **`NOT_RECORDED`** | Repo chỉ có `firmware/main/app_main.c` bootstrap; shared conversion chỉ được **quan sát gián tiếp** qua định dạng log, chưa kiểm chứng bằng code |
| Error handling khi đọc DS18B20 lỗi/mất | **Chưa test** | `Valid: 4/4` cho thấy có bộ đếm validity, nhưng chưa có bài test một đầu dò lỗi |
| `sensor-placement.png`, ảnh H0 | **MISSING** | Không vẽ lại từ trí nhớ, không tạo ảnh giả |
| Lệch số lượng đầu dò | **Chờ quyết định** | Canonical `SEN-H1-01` ghi 3 ROM; thực tế 4 đầu dò (kế thừa `CR-A-W01-04`) |
| `hardware_config_id`, `firmware_commit`, ngày review | **Chưa gán** | Cần leader gán |

## 6. Điều kiện để W02 được nghiệm thu

W02 chỉ có thể chuyển sang PASS khi tất cả các điều kiện sau được đáp ứng (`acceptance.md §5` là nguồn canonical):

1. `A-W02-06`: kết quả BME280 thật (chip-ID, I²C address, T/RH hợp lý, vị trí gá) — commit bổ sung vào PR này.
2. `A-W02-03`: log ≥5 chu kỳ reboot/discovery chứng minh ROM→role giữ nguyên.
3. `A-W02-05`: `sensor-consistency.csv` thô (hoặc serial log bật timestamp) để tính lại thống kê độc lập.
4. `A-W02-07`: freeze bảng `raw input → OPEN/CLOSED` + ghi lại thời gian chống dội.
5. `A-W02-02`: dán nhãn vật lý T1/T2/T3 (+ SPARE), có ảnh nhãn; nâng trạng thái khỏi `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`.
6. `A-W02-01`: quyết định của leader về H0 (giữ trong W02 hay dời sang giai đoạn hoàn thiện cơ khí hướng W07), kèm ảnh/checklist nếu chuyển.
7. `A-W02-04`: đưa nguồn firmware bench (hoặc firmware W02 chính thức) vào repo; ghi `firmware_commit`.
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

## 9. Kiểm tra đã chạy

- `py validate_w02.py` → **W02 STRUCTURE PASS**: 12 file bắt buộc, 4 bản ghi truy xuất nguồn được xác minh bằng kích thước + SHA-256 (3 ảnh gốc + 1 ghi chú archive), ROM map đúng 3 vai trò + 1 spare (mỗi đầu dò đều `physical_label: PENDING`), `acceptance.md` bao phủ `A-W02-01…A-W02-07`.
- Băm lại archive gốc đối chiếu `source_archive_sha256` (xem `README.md` §Reproduction bước 2).
- `git diff --cached --check` → không có lỗi whitespace/conflict marker.
- Independent review độc lập (không do tác giả thực hiện) đã đọc trực tiếp cả 3 ảnh gốc, băm lại archive và tính lại toàn bộ số dẫn xuất: **không có BLOCKER, không có MAJOR**; các finding MINOR đã được xử lý trong commit này.
- Không có test vật lý nào được chạy trong PR này; không có firmware mới được nạp.

## 10. Ngoài phạm vi

Không cấp nguồn TEC, không chạy tải dòng lớn, không thay đổi BOM freeze, không sửa `docs/00`–`docs/05A`, không đổi lịch canonical, không tạo dữ liệu giả, không merge PR, không bắt đầu W03.
