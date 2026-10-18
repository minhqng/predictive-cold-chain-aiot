# A-W01-05 — Legacy hardware assumption purge

**Nguồn có thẩm quyền:** `docs/00 §3.1` (BOM 24 mục đã freeze) và `docs/05A §10`.

Mục tiêu: các giả định phần cứng cũ không còn được dùng như thẩm quyền thi công. **Không xóa bằng chứng lịch sử**; chỉ đánh dấu obsolete và ngừng dùng làm căn cứ thực thi.

## Checklist bắt buộc theo `docs/05A §10`

| Từ khóa bắt buộc phải rà | Có xuất hiện trong kiến trúc đang hoạt động? | Thay thế có thẩm quyền |
|---|---|---|
| `INA226` | KHÔNG | Một PZEM-017 + một shunt ngoài 50 A/75 mV (HW-05, HW-06) |
| `IRLB3813` | KHÔNG | Một BTS7960 / IBT-2 (HW-08) |
| `two TEC` (2 TEC) | KHÔNG | **Đúng một** TEC1-12715, một nhánh làm lạnh (HW-09) |
| `20L` | KHÔNG | Chamber HS2 6 L (HW-11); người dùng xác nhận 6 L |
| `40A PSU` | KHÔNG | PSU 12 V / 33 A khoảng 400 W (HW-12) |

## Bằng chứng rà soát (tái lập được)

**Phạm vi quét:** cây **đã commit** `HEAD` = `bd76ed90d3d7133d128a61d22d828823f83e4c93` (baseline `main`). Phạm vi này **loại trừ** 37 file W01 đang được thêm — trong đó có chính bảng từ khóa này — để kết quả không tự tham chiếu.

**Lệnh tái lập:** `git grep -n -I -i -e "<từ khóa>" HEAD -- .`

Kết quả nguyên văn:

| Từ khóa | Số lần khớp ở `HEAD` | Vị trí | Bản chất | Trong kiến trúc đang hoạt động? |
|---|---|---|---|---|
| `INA226` | 11 | `backend/src/coldguard_backend/contracts.py` L14, L49, L58 · `docs/00` L852 · `docs/01` L3943 · `docs/02` L14 · `docs/03` L14 · `docs/04` L1401, L3857 · `docs/05A` L205, L762 | Câu **cấm tường minh** (docs/02, docs/03), checklist/policy (docs/01, docs/04), bảng obsolete (docs/00, docs/05A), và **danh sách token bị từ chối** ở tầng code | **KHÔNG** |
| `IRLB3813` | 3 | `docs/04` L3858 · `docs/05A` L206, L763 | Checklist cấm + bảng obsolete | **KHÔNG** |
| `two TEC` | 1 | `docs/05A` L764 | Bảng obsolete | **KHÔNG** |
| `2 TEC` | 2 | `docs/00` L854 (`1 TEC → 2 TECs`) · `docs/01` L2932 (`## 30.2 TEC characterization`) | Bảng obsolete; lần khớp thứ hai là **trùng chuỗi con ở số mục "30.2"**, không phải tham chiếu hai TEC | **KHÔNG** |
| `20L` | 1 | `docs/05A` L765 | Bảng obsolete | **KHÔNG** |
| `40A PSU` | 1 | `docs/05A` L766 | Bảng obsolete | **KHÔNG** |

Ghi chú độ chính xác:

- `docs/04` L1401 ghi `2-TEC` **có gạch nối**, nên chỉ khớp mẫu `INA226`, **không** khớp mẫu `2 TEC`.
- `docs/02` L14 và `docs/03` L14 là các câu **cấm tường minh** việc tái nhập kiến trúc cũ — bằng chứng ủng hộ việc thanh lọc, **không** phải mô tả kiến trúc đang hoạt động.
- Bảng này chỉ liệt kê các lần khớp của **sáu từ khóa bắt buộc**. Nó **không** khẳng định đã quét mọi biến thể chính tả khác (ví dụ `2-TEC`, `second TEC`).

**Kiểm tra phạm vi con:** `git grep -n -I -i -e "<từ khóa>" HEAD -- firmware ml control infra` → **không có lần khớp nào** (exit 1) cho cả sáu từ khóa.

Ghi nhận bổ sung: `backend/src/coldguard_backend/contracts.py` chứa `"ina226"` trong **danh sách token bị từ chối** (L58), kèm chú thích chính sách ở L14 và L49. Đây là **thực thi chống tái nhập do Member C sở hữu** — là bằng chứng ủng hộ, **không** phải artifact của Member A và **không** được tính vào phạm vi W01 của Member A.

## Các giả định cũ khác đã bị loại

| Giả định cũ | Thay thế có thẩm quyền | Kiểm chứng |
|---|---|---|
| Hai node ESP32-S3 N16R8 riêng biệt | Một board dual ESP32-S3R2 + W25Q32 + CH343G (HW-01) | Docs 00/05A; ảnh 20 xác nhận silkscreen `MAKDRIVERONE`; marking từng chip vẫn chưa đọc được |
| Hai nhánh làm lạnh, 4 quạt 120 mm | Một cụm tản V1 và đúng một nhánh làm lạnh (HW-10) | Ảnh quạt có, phạm vi theo Docs 00 |
| `current_1`, `current_2`, `power_1`, `power_2` | Quan sát điện của **một nhánh làm lạnh đã định nghĩa** | Docs 00/02 và schema backend |

## Phạm vi rà soát và giới hạn

- Đã rà soát: toàn bộ `docs/00`–`docs/05A` trong baseline hiện tại và **25 ảnh** trong `photo-inventory.csv`.
- **Chưa rà soát:** ghi chú vật lý cũ nằm ngoài repository. Người dùng có báo một tài liệu khóa học cũ (`[IoT - N01] ColdGuard...docx`) có thể chứa thiết kế INA226/IRLB3813; tài liệu này **không có trong bộ chứng cứ này**, nên chỉ được ghi nhận ở mức *user-reported*.
- Memo này **không** khẳng định đã tìm hết mọi tài liệu bên ngoài repository. Leader cần xác nhận phần ghi chú ngoài repo trước khi ký.
