# W01 hardware freeze — change-review requests

Theo `docs/00 §3.1/§3.2` và `docs/05A §10`, **BOM đã freeze không được thay đổi âm thầm**. Đây là log review. Mục `APPROVED` **cố ý để trống** đến 2026-11-09; từ ngày này, hai thay thế (CR-A-W01-01, CR-A-W01-02) đã được **project owner phê duyệt** theo chỉ thị của owner ngày 2026-11-09 (duyệt thay thế phần cứng đang lắp). Hai sai lệch số lượng (CR-A-W01-03, CR-A-W01-04) vẫn `PENDING` (quyết định của leader).

W01 ghi nhận **đúng bốn sai lệch** so với BOM đã freeze:

| Change ref | Frozen item | Reported as-built | Loại sai lệch | Decision requested | Current decision |
|---|---|---|---|---|---|
| CR-A-W01-01 | HW-07: MAX3485 module RS485 3.3 V | TTL485-V2.0 cấp 5 V; chip MAX13487ESA do người dùng báo; TXD 5 V qua phân áp 3×10 kΩ vào GPIO37 | Thay đổi linh kiện + miền nguồn (MAJOR) | Mua đúng module đã freeze **hoặc** chấp nhận thay đổi kèm bằng chứng datasheet/marking và tương thích mức logic | **APPROVED — project owner, 2026-11-09.** Chấp nhận thay thế; bằng chứng tương thích mức logic bench đã có (phân áp GPIO37 ≈ 3,314 V đo được; TEST 132B 600/600; xem `evidence/A/W03/rs485-pin-and-compatibility.md`); ảnh marking chip vẫn là mục xác minh mở |
| CR-A-W01-02 | HW-17: TB4504 45 A 4P | TB4506 cầu đấu 6 vị trí | Thay đổi linh kiện (MAJOR) | Chấp nhận kèm định mức được kiểm chứng độc lập và đúng phạm vi dùng **hoặc** thay thế | **APPROVED — project owner, 2026-11-09.** Chấp nhận thay thế cho phạm vi dùng hiện tại (nhánh logic/chia áp, dòng nhỏ); ảnh marking + định mức kẹp TB4506 vẫn là mục xác minh mở trước khi dùng ở phạm vi dòng lớn |
| CR-A-W01-03 | HW-18: PCT218 8 cổng, số lượng 1 | Người dùng xác nhận **4 chiếc** PCT-218 8 cổng | **Chỉ số lượng** (1 → 4); không thay đổi chủng loại | Xác nhận sai lệch số lượng; chốt 1 chiếc dùng chính, phần còn lại là dự phòng hay không | PENDING (leader) |
| CR-A-W01-04 | HW-02: DS18B20 ×3 | Người dùng xác nhận **4 đầu dò**; 4 ROM ID duy nhất đọc được qua GPIO10 | **Chỉ số lượng** (3 → 4); không thay đổi chủng loại | Giữ đúng 3 cảm biến chính T1/T2/T3; cảm biến thứ 4 chỉ là dự phòng/extension, không tạo kênh primary thứ tư khi chưa duyệt | PENDING (leader, B/C tham vấn) |

## Bằng chứng xác minh còn lại sau phê duyệt thay thế (2026-11-09)

Các mục dưới đây **không chặn** phê duyệt thay thế CR-A-W01-01/-02 (owner đã duyệt), nhưng vẫn phải hoàn thành theo dõi trong `next_action` của `bom-audit.csv`:

- HW-07: ảnh cận marking chip (bộ 25 ảnh hiện hành **vẫn không** đọc được), pinout nhà bán, đo nguồn và mức vào/ra tại GPIO trước lần đấu lại.
- HW-17: ảnh marking `TB4506`, tài liệu định mức kẹp/tiết diện và nhánh thực tế đang dùng.
- HW-18: **đã có** ảnh 22/23/24 chứng minh khắc nổi `PCT-218` và cấu hình 8 cổng cho **một chiếc**; **còn thiếu** ảnh đếm đủ 4 chiếc.
- HW-02: **đã có** ảnh 12 chứng minh một đầu dò DS18B20 chống nước; **còn thiếu** ảnh đếm đủ 4 đầu dò và bảng ROM ID 64-bit → vai trò.

## Khoảng trống xác minh KHÔNG phải sai lệch BOM

Các mục dưới đây là thiếu bằng chứng, **không** được tính là thay thế BOM. Chúng được theo dõi trong cột `next_action` của `bom-audit.csv`:

- HW-16: mới xác nhận 1 × 5 A trong khi frozen yêu cầu `>=2 × 5 A`; cầu chì 1 A là bổ sung ngoài BOM.
- HW-23: 3 × 10 kΩ **người dùng báo là đã đo** (linh kiện ngoài BOM) và 4.7 kΩ do người dùng báo đủ nhưng chưa có ảnh/đo — agent **chưa** tái lập cả hai con số.
- HW-06: nhãn **in** `50A 75mV` đã đọc được ở ảnh 18 (phần khắc trên phần tử điện trở là `FL-2 0.5`, ảnh 04); cấp chính xác và profile 50 A trong PZEM vẫn chưa xác minh.
- HW-09: ảnh 15 đọc rõ marking `TEC1-12715 SR`; seller/SKU vẫn chưa xác minh.
- HW-19: chưa xác minh được `2 × 2.5 mm² ~2 m`; vẫn không có ảnh.
- HW-24: keo tản nhiệt vẫn chưa có ảnh riêng (ảnh 17 chỉ cho thấy hộp kit V1).

## Watchlist — thiếu hụt cấu hình & danh tính chưa chốt (**KHÔNG** phải substitution)

Các mục này **không** phải thay thế BOM, nhưng là **sự kiện cấu hình** mà leader cần biết khi quyết định freeze. Đây là watchlist, **không** phải yêu cầu substitution, và **không** mục nào được tự động coi là đã phê duyệt.

| Mục | Loại | Thực tế quan sát | Vì sao leader cần biết |
|---|---|---|---|
| HW-16 Fuse phụ | **Thiếu hụt số lượng** so với baseline (`docs/00 §3.1` ghi `5 A`, `≥2`) | Chỉ xác nhận `1 × 5 A`; thêm `1 × 1 A` là bổ sung **ngoài** BOM | Nếu cần ≥2 nhánh 5 A thì cấu hình hiện tại **không** đạt baseline; đây là sự kiện cấu hình, không chỉ là thiếu bằng chứng |
| HW-03 BME280 | **Danh tính chưa chốt** — substitution tiềm tàng (mất cảm biến độ ẩm) | Ảnh silkscreen đọc `GY-BM[P/E] 280`; có `CSB`/`SDO` nên **không** loại trừ BMP280 | Nếu là BMP280 thì mục "BME280" của BOM không được đáp ứng; chỉ đọc được chip-ID I²C ở W02 |
| HW-11 Chamber | **Danh tính chưa chốt** | Ảnh chỉ chứng nhận đã nhận kiện; HS2 và 6 L là lời khai của người vận hành | Mục no-substitution của chamber chưa được chứng minh bằng ảnh/đo |
| HW-09 TEC1-12715 | **Danh tính chưa chốt** | Marking `TEC1-12715 SR` đã có ảnh; seller/SKU chưa xác minh | Sai SKU dẫn tới sai dòng/nhiệt; **không** suy dòng định mức từ marking |
| HW-13 XL4015 | **Danh tính chưa chốt** | Marking chip bị cắt ở mép ảnh; danh tính theo người dùng báo | Ảnh hưởng passport module; thấp về an toàn |

## Decision log

- Date: `2026-11-09`
- Decision-maker: `Project owner` (chỉ thị của owner gửi Member A ngày 2026-11-09: phê duyệt các quyết định thay thế phần cứng hiện tại; không yêu cầu phê duyệt lại)
- Phạm vi phê duyệt: thay thế linh kiện CR-A-W01-01 (HW-07: TTL485-V2.0 thay MAX3485) và CR-A-W01-02 (HW-17: TB4506 thay TB4504) cho cấu hình đang lắp CG-HW-001
- Không thuộc phạm vi phê duyệt này: CR-A-W01-03, CR-A-W01-04 (sai lệch số lượng — vẫn chờ leader); định mức độc lập của TB4506; rating liên tục của TEC (`TEC1-12715` vẫn "part number, not a rating")
- Approved hardware_config_id/revision: `CG-HW-001` (bản ghi Member A; không đổi phần cứng vật lý, chỉ ghi nhận quyết định)
- Required Docs 00/01 revisions: `PENDING — SYNC_REQUIRED` — `docs/00 §3.5`/BOM và `docs/01` tham chiếu MAX3485 cần được owner/team cập nhật đồng bộ theo quy trình change-policy của docs/00; Member A không tự sửa Docs 00–01
- Ghi chú: status `APPROVED_SUBSTITUTION` chỉ định nghĩa cho dòng BOM có thay thế đã duyệt; validator (`validate_w01.py`) và bảng từ vựng (`README.md`) đã cập nhật theo
