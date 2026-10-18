# ColdGuard — Member A — W02 sensor foundation

**Snapshot:** 2026-10-18 · **Role:** Member A (Embedded & Thermal) · **Status:** `DRAFT / REVIEW REQUIRED — W02 NOT PASS` · **hardware_config_id:** `NOT_ASSIGNED` · **Firmware commit:** `NOT_RECORDED` · **Operator:** Member A (không ghi tên cá nhân trong repo)

## Phạm vi và thẩm quyền

- Thứ tự thẩm quyền: `docs/00` → `docs/01` → `docs/02` → `docs/03` → `docs/04` → `docs/05A`; cụ thể `docs/04 §17` (W02), `docs/05A §11` (A-W02-01…07), `docs/03 §14–§15` (`HW-H0-01`, `HW-H0-02`, `SEN-H1-01…05`).
- Bộ này **không** viết lại Docs 00–04, **không** sửa lịch canonical, **không** đánh dấu H0 PASS.
- Bộ này **không** chứa dữ liệu tự tạo. Mọi số liệu trong đây đều bắt nguồn từ ảnh log thật do người dùng cung cấp (W02 bench session), hoặc là đại lượng dẫn xuất được tính lại công khai từ chính các số đó.
- Bộ này **không** phải nghiệm thu vật lý. Nó là hồ sơ bằng chứng để review.

## Provenance của ảnh

- **Archive nguồn:** `ColdGuard_A_W02_Existing_Test_Screenshots.zip` · 81 661 bytes · SHA-256 `383CBB4A323AD4E524C1E76348C30DACA4C161C42E85CD9A20C33586D5B97429`.
- 3 ảnh PNG được sao chép **nguyên byte** vào thư mục này: không crop, không nén lại, không chỉnh màu, không ghi đè chú thích. Kích thước và SHA-256 từng ảnh được khai báo trong `screenshot-provenance.csv` và được `validate_w02.py` kiểm tra lại trên đĩa.
- `source-archive-readme.md` là bản sao **nguyên văn** của `README.md` bên trong archive — chính người dùng viết — dùng làm nguồn truy xuất nguồn và mô tả giới hạn từ phía người tạo ảnh.
- Ảnh là **cửa sổ hiển thị Serial Monitor COM4 @ 115200 baud, `Show timestamp = OFF`**. Việc timestamp bị tắt là một giới hạn thật và được nêu ở mọi file liên quan.

### Ảnh chứng minh gì — và KHÔNG chứng minh gì

| Ảnh | Chứng minh | KHÔNG chứng minh |
|---|---|---|
| `w02_rom_enumeration_4_devices.png` | 4 ROM DS18B20 phân biệt được liệt kê; cả 4 đọc được giá trị trong cùng phiên; firmware tự báo `PASS: 4 DS18B20 detected` | đầu dò vật lý nào là T1/T2/T3; nhãn vật lý; ổn định ROM→role qua reboot; ngữ nghĩa OPEN/CLOSED của MC-38 |
| `w02_ds18b20_600_samples_summary.png` | summary thật với `valid=600/600` và mean/sd/min/max cho từng đầu dò | đủ 600 dòng dữ liệu; timestamp thật; nhịp ~1 Hz; đủ 10 phút theo đồng hồ; ý nghĩa các cột |
| `w02_mc38_24_cycles.png` | bộ đếm chuyển mức đạt 24 chu kỳ | debounce; polarity; timestamp sự kiện; tổng số chu kỳ của phiên |

**Ảnh summary xác nhận rằng kết quả đã được hiển thị. Ảnh không thay thế CSV 600 dòng, không thay thế timestamp thật, và ảnh MC-38 không tự chứng minh debounce hay polarity.**

## Files

| File | Nội dung |
|---|---|
| `sensor-rom-map.yaml` | Ánh xạ ROM → vai trò T1/T2/T3 + SPARE; trạng thái `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`; trạng thái từng test liên quan danh tính |
| `sensor-consistency-summary.md` | `SEN-H1-03` / `A-W02-05`: bảng 600 mẫu/đầu dò, chênh lệch cặp, độ ổn định, và danh sách điều **không** chứng minh được |
| `door-test-summary.md` | `SEN-H1-05` / `A-W02-07`: đọc bộ đếm MC-38, đối chiếu tiêu chí, lý do polarity và debounce còn `PENDING` |
| `screenshot-provenance.csv` | Truy xuất nguồn từng ảnh: kích thước, SHA-256, file nguồn trong archive, nội dung, giới hạn |
| `acceptance.md` | **Nguồn trạng thái duy nhất**: acceptance matrix A-W02-01…07, tiêu chí PASS canonical, blocker, quyết định cần leader |
| `validate_w02.py` | Kiểm tra cấu trúc: file bắt buộc, hash ảnh khớp provenance, YAML parse được, không có CSV thiếu cột. **Không** xác nhận đúng/sai vật lý |
| `PR_BODY.md` | Nội dung mô tả PR đề xuất (bản cục bộ để review trước khi publish) |
| `source-archive-readme.md` | Bản sao nguyên văn README trong archive nguồn |
| `w02_*.png` (×3) | Ảnh log gốc, byte-identical |

## Trường bắt buộc theo `docs/05A §8`

| Trường | Giá trị |
|---|---|
| `date` | 2026-10-18 (ngày nhận và kiểm chứng archive; phiên bench do người dùng thực hiện trước đó) |
| `operator` | Member A (người vận hành vật lý; không ghi tên cá nhân trong repo) |
| `hardware_config_id` | `NOT_ASSIGNED` — chưa được leader gán |
| `firmware commit` | `NOT_RECORDED` — sketch bench W02 **không** có trong repo (repo chỉ có `firmware/main/app_main.c` bootstrap) |
| `test IDs` | `HW-H0-01`, `HW-H0-02` (chưa thực hiện), `SEN-H1-01` (partial), `SEN-H1-02` (not performed), `SEN-H1-03` (partial), `SEN-H1-04` (not performed), `SEN-H1-05` (partial) |
| `setup` | Bench không cấp nguồn TEC; 4 đầu dò DS18B20 trên một bus 1-Wire; MC-38 nối vào board; Serial Monitor COM4 @ 115200, không bật timestamp |
| `result` | ROM map 3 vai trò + 1 spare; 600/600 mẫu hợp lệ × 4 đầu dò; MC-38 24 chu kỳ; BME280 chưa đo |
| `pass/fail` | **`NOT PASS`** — `W02_PARTIAL_EVIDENCE` (chi tiết và blocker ở `acceptance.md`) |
| `anomalies` | Lệch số lượng đầu dò 4 so với canonical 3; **khối `TEMPERATURE` đầu tiên trong ảnh enumeration bị thiếu một dòng có nhãn** (xem §“Bất thường quan sát được”); không có timestamp; không có CSV thô; không có log reboot; chưa freeze polarity MC-38; chưa có H0 |

Bảng này **không** phải nguồn trạng thái; trạng thái canonical nằm duy nhất ở `acceptance.md`.

## Tóm tắt trạng thái W02 (chi tiết ở `acceptance.md`)

| Hạng mục | Trạng thái |
|---|---|
| `A-W02-01` H0 mechanical | `DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING` |
| `A-W02-02` DS18B20 enumeration | `PARTIAL` — 4 ROM phân biệt, lệch canonical 3 |
| `A-W02-03` reboot identity proof | `RAW_EVIDENCE_PENDING` — chưa có log 5 chu kỳ |
| `A-W02-04` acquisition implementation | `PARTIAL` — quan sát gián tiếp từ log; nguồn firmware không có trong repo |
| `A-W02-05` inter-sensor consistency | `PARTIAL` — summary thật, thiếu CSV thô và timestamp |
| `A-W02-06` BME280 | `PENDING_TEST — USER PLANS TO COMPLETE TONIGHT` |
| `A-W02-07` MC-38 | `PARTIAL` — 24 chu kỳ ≥ 20; polarity/debounce chưa chứng minh |

## Bất thường quan sát được (khai báo tường minh)

1. **Ảnh `w02_rom_enumeration_4_devices.png`, khối `TEMPERATURE` đầu tiên sau dòng `PASS: 4 DS18B20 detected` không đầy đủ:** khối đó in `DS1: 29.81 C` → `29.56 C` (**không có tiền tố nhãn**) → `DS4: 29.88 C` → `Valid: 4/4`, tức **thiếu một dòng có nhãn** so với 6 khối sau (mỗi khối sau đều đủ `DS1`/`DS2`/`DS3`/`DS4`). Bộ chứng cứ này **không** suy đoán nguyên nhân (lỗi in của sketch, mất ký tự trên đường serial, hay hiện tượng ghi đè dòng đều có thể giải thích). Đây là lý do bổ sung để cần **nguồn firmware** và **log thô** trước khi kết luận về hành vi in của sketch.
2. **Khối `TEMPERATURE` cuối cùng của ảnh `w02_mc38_24_cycles.png` bị cắt:** ảnh dừng ở `DS2: 30.19 C`, nên không thấy `DS3`/`DS4`/`Valid` của khối đó.
3. **Một khối trong ảnh enumeration in `DS3: 29.50 C`** trong khi các khối khác in `29.56 C` (đã ghi ở `sensor-consistency-summary.md §5`; nằm ngoài cửa sổ 600 mẫu).

Cả ba điểm trên đều **không** làm thay đổi kết luận của hồ sơ, nhưng được khai báo vì hồ sơ này đặt chuẩn “nêu tường minh”.

## Reproduction / review

1. Chạy `py validate_w02.py` (khuyến nghị trên Windows). Script kiểm tra cấu trúc và SHA-256 ảnh; **không** chạy bất kỳ phép xác minh vật lý nào.
2. Kiểm tra ảnh khớp với `screenshot-provenance.csv`: `Get-FileHash .\w02_*.png -Algorithm SHA256`.
3. Kiểm tra lại **archive gốc** (an toàn hơn kiểm tra ảnh trên đĩa, vì khoá tin cậy không nằm trong repo): `Get-FileHash "$env:USERPROFILE\Downloads\ColdGuard_A_W02_Existing_Test_Screenshots.zip" -Algorithm SHA256` phải trả về `383CBB4A323AD4E524C1E76348C30DACA4C161C42E85CD9A20C33586D5B97429` (81 661 bytes).
4. Đối chiếu từng con số trong `sensor-consistency-summary.md` với ảnh `w02_ds18b20_600_samples_summary.png` (đặc biệt 4 dòng `# S1…S4`).
5. Đối chiếu số học bộ đếm MC-38 trong `door-test-summary.md` §2 với ảnh `w02_mc38_24_cycles.png`.
6. Đọc `acceptance.md` để biết chính xác hạng mục nào PASS/PARTIAL/PENDING và ai cần quyết định gì.

## Handoffs

- **To B:** ngữ nghĩa vị trí sẽ dùng cho feature spatial — nhưng hiện **chưa** có vị trí vật lý đã freeze; `sensor-consistency-summary.md` chỉ là consistency check, **không** phải calibration. Chưa dùng được cho dataset.
- **To C:** fixture JSON cho cảm biến thật **chưa** được cung cấp trong PR này; schema bench (`index,giây,DS1..DS4,valid,…`) **khác** `backend/fixtures/telemetry_v0.json` nên không được nhầm hai thứ này.
- **To D:** chưa có hành vi `physical-quality` trên cảm biến thiếu; `A-W02-04` mới chỉ có bằng chứng gián tiếp nên chưa thể chốt semantics degraded.
- **To leader:** quyết định lệch số lượng đầu dò (kế thừa `CR-A-W01-04`), lịch H0 (`A-W02-01`), và xác nhận tiêu chí nghiệm thu còn thiếu cho W02.

## Cổng chất lượng W02

**Chưa PASS.** Có ba nhóm bằng chứng thật (enumeration, consistency summary, door cycles) và một bản đồ ROM vai trò đã ghi, nhưng thiếu dữ liệu thô, thiếu timestamp, thiếu BME280, thiếu log reboot và thiếu H0 — cộng thêm đầu dò chưa được dán nhãn vật lý. Hồ sơ ở mức **PR-reviewable** với blocker nêu tường minh, không che giấu phần còn thiếu.
