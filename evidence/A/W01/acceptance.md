# W01 acceptance — Member A

Bảng này là **nguồn duy nhất** cho trạng thái nghiệm thu W01 của Member A. `hardware-audit-w01.md` không lặp lại checklist.

## Tiêu chí PASS theo `docs/05A §10`

| Tiêu chí canonical | Trạng thái | Bằng chứng / phần còn thiếu |
|---|---|---|
| 24-item list reconciled | **PARTIAL** | `bom-audit.csv` có đủ 24 dòng HW-01..HW-24; nhiều dòng vẫn là `reported` hoặc có khoảng trống xác minh |
| no unexplained core item substitution | **APPROVED — chờ ghi nhận lại bởi evaluator** | Hai thay thế (HW-07 TTL485-V2.0, HW-17 TB4506) đã được **project owner phê duyệt 2026-11-09**; `bom-audit.csv` cập nhật `APPROVED_SUBSTITUTION`, decision log trong `freeze-deviation-review.md`; kết quả FAIL cũ (UNAPPROVED_SUBSTITUTION) trong store là snapshot trước phê duyệt |
| no old architecture carried forward | **PASS (phạm vi repo)** | `legacy-assumption-check.md`: không còn INA226 / IRLB3813 / 2 TEC / 20 L / 40 A PSU trong kiến trúc hoạt động; ghi chú ngoài repo chưa rà hết |
| uncertain module facts explicitly marked unknown | **PASS** | Mọi mục chưa xác minh được ghi rõ `UNKNOWN` / `UNVERIFIED` / `reported` trong `bom-audit.csv` và `pin-candidates-v0.md` |

## Deliverables theo `docs/05A §10` và `docs/04 §16`

| Deliverable | Trạng thái | File |
|---|---|---|
| BOM reconciliation | DRAFT | `bom-audit.csv` |
| Photo inventory | DRAFT (25 ảnh; còn 3 mục không có ảnh) | `photo-inventory.csv`, `photos/` |
| Board pin investigation, không đóng băng GPIO | DRAFT | `pin-candidates-v0.md` |
| Electrical risk ledger | DRAFT, cần D review | `physical-risk-ledger.md` |
| Legacy assumption purge | DRAFT | `legacy-assumption-check.md` |
| Hardware audit summary (`docs/04 §16`) | DRAFT | `hardware-audit-w01.md` |
| Risk register (`docs/04 §16`) | DRAFT | `physical-risk-ledger.md` |
| TEAM-W01-01 member summary | DRAFT, chưa có chữ ký team | `team-w01-member-a-summary.md` |

## A-W01-02 — Đối chiếu danh sách ảnh canonical (`docs/05A §10`)

Danh sách dưới đây là **nguyên văn yêu cầu canonical**. Đây là **12 hạng mục ảnh**, **không phải** yêu cầu "mỗi dòng BOM phải có ảnh":

| # | Canonical yêu cầu (`docs/05A §10` A-W01-02) | Ảnh | Trạng thái |
|---|---|---|---|
| 1 | both sides of dual ESP32 board | `20`, `21` | **PASS** |
| 2 | DS18B20 labels/probes | `12` | **PARTIAL** — có đầu dò; chưa có nhãn/ROM |
| 3 | BME | `25`, `26` | **PASS** |
| 4 | MC-38 | `13` | **PASS** |
| 5 | PZEM | `04`, `05` | **PASS** |
| 6 | shunt | `04`, `18` | **PASS** |
| 7 | MAX3485 | `02`, `03` | **PARTIAL** — đúng board; marking chip không đọc được |
| 8 | IBT-2 | `14` | **PASS** |
| 9 | TEC package/SKU marking | `15` | **PARTIAL** — có marking; chưa có bao bì/SKU |
| 10 | V1 | `17`, `10` | **PASS** |
| 11 | PSU | `16`, `09` | **PASS** |
| 12 | fuse/distribution components | `07`, `08`, `01` | **PASS** |

**Kết quả: 9/12 PASS · 3/12 PARTIAL · 0/12 thiếu hoàn toàn.**

Ghi chú phạm vi: HW-19 (dây công suất), HW-22 (header), HW-24 (keo tản nhiệt) **không** nằm trong danh sách canonical này. Việc chúng chưa có ảnh là **khuyến nghị cải thiện**, **không** phải blocker canonical của W01.

## Blocker W01 (canonical — phải xử lý trước khi W01 có thể PASS)

- [x] CR-A-W01-01 (HW-07) và CR-A-W01-02 (HW-17): **project owner phê duyệt 2026-11-09**; ghi trong decision log `freeze-deviation-review.md`; dòng BOM chuyển `APPROVED_SUBSTITUTION`. CR-A-W01-03/04 (số lượng) vẫn chờ leader.
- [ ] Leader xác nhận sai lệch số lượng CR-A-W01-03 (PCT-218 ×4) và CR-A-W01-04 (DS18B20 ×4).
- [ ] HW-07: marking chip chưa đọc được trong bất kỳ ảnh nào → cần ảnh cận/datasheet nhà bán (hạng mục canonical 7 còn PARTIAL).
- [ ] Xác minh `>=2 × 5 A` (HW-16 — canonical yêu cầu `≥2`, hiện mới 1 × 5 A) và tiết diện `2 × 2.5 mm²` (HW-19) bằng ảnh/đo, **không** suy diễn.
- [ ] Hạng mục canonical 9 (TEC package/SKU) còn PARTIAL: có marking nhưng chưa có bao bì/SKU.
- [ ] Member D rà soát `physical-risk-ledger.md` và xác nhận không phê duyệt chạy tải dòng lớn trong W01.
- [ ] Gán `hardware_config_id`, firmware commit, operator và ngày review.
- [ ] Hoàn tất TEAM-W01-01..04 và lấy chữ ký team cho `team-w01-member-a-summary.md`.
- [ ] `docs/04 §16` liệt kê `sensor labels` trong hoạt động W01 của Member A; hiện **chưa có artifact nhãn cảm biến riêng** — cần xác nhận phạm vi với leader.

## TEAM_DEPENDENCY — phân loại cần leader/D xác nhận

- **HW-11 (chamber HS2 / 6 L):** `docs/04 §16` L1316 ghi "Verify all 24 purchased items physically" và L1400 ghi `exact BOM physically reconciled`; hai câu này **có thể** được đọc là đưa xác minh HS2 / dung tích 6 L vào phạm vi W01. Bộ chứng cứ này **hoãn** việc đó sang W02 vì kiện chưa mở. Việc hoãn **không** bị che giấu (đã nêu ở `bom-audit.csv` HW-11 và bảng `Watchlist` trong `freeze-deviation-review.md`), nhưng **cần leader hoặc D xác nhận** đây là cách phân loại đúng — hoặc chuyển HW-11 vào danh sách blocker canonical ở trên.
- **Bảng `Watchlist`** trong `freeze-deviation-review.md` (HW-16, HW-03, HW-11, HW-09, HW-13) là các **sự kiện cấu hình** cần leader biết khi quyết định freeze — **không** phải substitution và **không** phải blocker canonical.

## Chuyển tiếp sang W02/W03 — **KHÔNG** phải tiêu chí nghiệm thu W01

Các mục dưới đây **không** chặn W01. Chúng được ghi lại để không mất dấu, và **không** được dùng để đánh giá W01 PASS/FAIL:

- [ ] W02: hàn header, cấp 3.3 V và **đọc chip-ID I²C (0x58 BME280 / 0x60 BMP280)** để kết luận die — **không thể** xác minh bằng ảnh.
- [ ] W02: lưu bảng ROM ID 64-bit → vai trò T1/T2/T3 (A-W02-02), kèm ảnh đếm đủ 4 đầu dò.
- [ ] W02: lắp cụm tản V1 hoàn chỉnh (A-W02-01) rồi chụp kèm keo và lực ép.
- [ ] W02: đếm và chụp đủ 4 chiếc PCT-218 trong một khung.
- [ ] W02: mở kiện, chụp tem HS2/dung tích chamber — dung tích 6 L hiện chỉ là lời khai của người vận hành.
- [ ] W03: readback cấu hình shunt 50 A trong PZEM và xác minh thanh ghi.
- [ ] Khuyến nghị (không thuộc danh sách ảnh canonical): bổ sung ảnh cho HW-19, HW-22, HW-24 (`photo_ref = NONE`).

## Reconcile bộ ảnh 25 (2026-10-18)

- **Nguồn ảnh hiện hành:** `ColdGuard_W01_All_25_Real_Photos_OpenCode.zip` (25 ảnh, SHA-256 `9EB77E77CC1C1436B927E4307B0B14738C4A8EE2F4D7959D0C66A144212986CB`). 10 ảnh trước đó là tập con byte-identical (đã xác minh bằng SHA-256 khi hợp nhất).
- **Đã bổ sung 15 ảnh:** `12`, `13`, `14`, `15`, `16`, `17`, `18`, `20`, `21`, `22`, `23`, `24`, `25`, `26`, `27`. Không có số `11` và `19`.
- **Đã sửa truy xuất nguồn ảnh 18:** `50A 75mV` là **nhãn in** trên thân shunt, **không phải khắc**; phần khắc trên phần tử điện trở là `FL-2 0.5` (ảnh 04).
- `photo-inventory.csv` được **merge theo tên file**, không ghi đè: giữ mô tả đã kiểm chứng cho 10 ảnh gốc.
- **Ảnh nói `hiện diện`, không nói `đủ`.** Gói 25 ảnh **không** biến W01 thành PASS: W01 vẫn `W01_PENDING_REVIEW`.

## Ngoài phạm vi W01

Các hạng mục thuộc W02–W04 (ví dụ liệt kê ROM → vai trò, bài test sensor kéo dài, cấu hình PZEM, chạy tải TEC) **không** là tiêu chí nghiệm thu W01 và không được dùng để đánh giá W01 PASS/FAIL.

**Current gate: `W01_PENDING_REVIEW` — không phải `W01_PASS`.**
