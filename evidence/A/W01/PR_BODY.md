# Đề xuất mô tả PR — A-W01 hardware audit (CHƯA PUBLISH)

> Tài liệu review cục bộ. Chưa commit, chưa push, chưa tạo PR. Nội dung dưới đây là đề xuất để con người phê duyệt.

---

## Suggested PR

**Title:** `[A-W01] Physical BOM Audit and Hardware Freeze Review`

**Base:** `main` · **Head:** `feature/A-W01-hardware-audit`

---

## [A-W01] Kiểm kê vật lý BOM, pin candidate, sổ rủi ro điện

**Issue:** `A-W01-01`–`A-W01-05` (chưa xác minh được issue ID thật trong phiên này; cần điền khi tạo PR)
**Tài liệu cha:** `docs/00 §3.1`, `docs/01`, `docs/04 §16`, `docs/05A §10`
**Reviewer:** Member D (bắt buộc) và team leader (quyết định freeze)
**Ảnh hưởng hardware config?:** CÓ — chỉ đề xuất ngoại lệ, **chưa** thay đổi BOM được duyệt.

### Thay đổi

- Một dòng kiểm kê cho mỗi HW ID trong 24 mục đã freeze, kèm số lượng quan sát, marking nhìn thấy, tình trạng, ảnh và mức không chắc chắn tường minh.
- Bộ 25 ảnh (10 ảnh đầu đã crop; 15 ảnh bổ sung), đặt **tên tất định** trong repo (`NN-mo-ta.jpg`) để tham chiếu ổn định; `photo-inventory.csv` giữ `source_upload_filename` của người dùng để truy xuất nguồn. Lưu ý: một số tên gốc **trùng nhau** hoặc chỉ là placeholder (`image.png`), nên tên file trong repo **không** sao chép nguyên văn tên gốc.
- Bảng GPIO candidate (GPIO36 TX / GPIO37 RX qua phân áp bảo vệ, GPIO10 cho 1-Wire, GPIO34 cho MC-38) và danh sách chân còn mở.
- Sổ rủi ro điện/nhiệt và bốn yêu cầu review sai lệch hardware freeze.
- Loại bỏ kiến trúc cũ và checklist nghiệm thu.

### Bằng chứng và phạm vi claim

- Kết quả bench là **do Member A báo cáo**, **không** được tái lập trong PR này: XL4015 ~5 V, PZEM Modbus CRC hợp lệ và 11.95 V, logic BTS7960, 4 ROM ID DS18B20 qua GPIO10, MC-38 24 chu kỳ qua GPIO34.
- **Không** claim PASS cho dòng/công suất TEC, cho shunt, cho quạt hay cho BME280.
- **Không** claim đã xác nhận vật lý đầy đủ 24 mục hay W01 đã PASS.

### Bằng chứng

`evidence/A/W01/` (`README.md`, `bom-audit.csv`, `photo-inventory.csv`, `photos/`, `pin-candidates-v0.md`, `physical-risk-ledger.md`, `legacy-assumption-check.md`, `hardware-audit-w01.md`, `freeze-deviation-review.md`, `acceptance.md`, `team-w01-member-a-summary.md`).

### Trọng tâm review

1. Sai lệch MAX3485 3.3 V đã freeze ↔ TTL485-V2.0 5 V thực tế; an toàn mức logic GPIO.
2. Thay thế TB4504 ↔ TB4506 và định mức đầu nối.
3. Sai lệch số lượng PCT-218 (×4) và DS18B20 (×4); `>=2 × 5 A` fuse và điện trở 4.7 kΩ.
4. Đúng SKU TEC (marking `TEC1-12715 SR` đã có ảnh), cấp chính xác/profile shunt 50 A, vỏ bảo vệ phần AC và cos đúng dải dây.
5. Chấp nhận W01 là **bằng chứng draft một phần**; **không** đánh dấu W01 DONE cho tới khi hết checklist.

### Quyết định bắt buộc trước khi merge

| Người quyết định | Nội dung cần quyết |
|---|---|
| **Member D** | Rà soát rủi ro vật lý/điện trong `physical-risk-ledger.md`; xác nhận không phê duyệt chạy tải dòng lớn trong W01; chấp nhận hay từ chối cách đấu tạm RS485 và trạng thái boot của IBT-2 |
| **Team Leader** | Phê duyệt hoặc bác bỏ CR-A-W01-01 (HW-07) và CR-A-W01-02 (HW-17); xác nhận sai lệch số lượng CR-A-W01-03 (PCT-218 ×4) và CR-A-W01-04 (DS18B20 ×4); quyết định có yêu cầu mua lại đúng linh kiện đã freeze hay không |

### Giới hạn / ngoài phạm vi

Không cấp nguồn dòng lớn, không sửa hardware freeze, không chạy thử TEC, không đổi firmware. Ảnh do người dùng tải lên (25 ảnh) và **không** phải bộ passport linh kiện đầy đủ: ảnh chứng minh *hiện diện*, không chứng minh *số lượng* hay *chất lượng lắp đặt*.

### Blocker khi merge

**Blocker W01 (canonical):**

- CR-A-W01-01 và CR-A-W01-02 chưa được quyết định.
- HW-07: marking chip MAX3485 chưa đọc được trong bất kỳ ảnh nào → hạng mục canonical 7 còn PARTIAL.
- Chưa xác minh `>=2 × 5 A` (HW-16 — canonical yêu cầu `≥2`, hiện mới 1 × 5 A) và tiết diện `2 × 2.5 mm²` (HW-19).
- Hạng mục canonical 9 (TEC package/SKU) còn PARTIAL.
- Chưa gán `hardware_config_id` và firmware commit.

**Chuyển tiếp sang W02/W03 — KHÔNG phải blocker W01:** đọc chip-ID BME280/BMP280, bảng ROM ID DS18B20, lắp cụm V1 hoàn chỉnh, đếm đủ 4 PCT-218, mở kiện chụp tem HS2, readback profile shunt 50 A trong PZEM. Chi tiết ở `acceptance.md`.

**Khuyến nghị (không thuộc danh sách ảnh canonical):** ảnh cho HW-19, HW-22, HW-24 — cả ba đang `photo_ref = NONE`.
