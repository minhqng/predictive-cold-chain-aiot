# A-W03-01 — XL4015 logic power measurement (Member A)

**Trạng thái: `VERIFIED BY EXISTING EVIDENCE (W01 user-reported) + MEASUREMENT REQUIRED`.**
File này ghi lại những gì **đã có** (không đo lại), những gì **còn thiếu**, và kế hoạch đo W03. Không có số nào trong mục 2 do agent đo.

## 1. Bối cảnh canonical

`docs/05A §12` A-W03-01: trước khi cấp cho các module nhạy cảm —

- đặt mức ra logic dự kiến;
- đo bằng đồng hồ;
- ghi giá trị no-load/load nếu thực tế;
- target danh nghĩa **~5 V**, trong giới hạn an toàn của module.

## 2. Đã có từ W01 (báo cáo người dùng — KHÔNG đo lại trong W03)

| Nguồn | Nội dung | Ghi chú |
|---|---|---|
| W01 `hardware-audit-w01.md` | XL4015 đặt ~5 V (đo không tải); TB4506 ~4.99 V | Người dùng báo; agent W01 chưa tái lập |
| W01 `physical-risk-ledger.md` R04 | Fuse 5 A cho nhánh XL4015; vị trí fuse chưa được lập sơ đồ | Vẫn OPEN |
| W01 `physical-risk-ledger.md` R10 | Nguồn logic 5 V cấp cho TTL485/PZEM | Đây là lý do tồn tại lệch mức logic; xem `hardware-deviation-and-safety.md` |

**Giới hạn của "đã có":** một giá trị no-load được báo lại. Không có ảnh đồng hồ đo, không có giá trị có tải, không có ripple, không có nhiệt độ, không có dòng logic tổng. Vì vậy W03 **không** ghi đây là W03 VERIFIED.

## 3. Phiên đo W03 còn thiếu (checklist cho người vận hành + D)

> Điều kiện tiên quyết: D có mặt (hoặc ủy quyền) và mục PENDING của CR-A-W01-01 không cản trở — các bước dưới đây **chỉ** đo nhánh nguồn logic với tải module thật, **không** chạm TEC.

1. Ngắt nguồn trước khi đấu; xác nhận fuse 5 A còn tốt; chụp ảnh cách đấu hiện tại.
2. Cấp nguồn, đo **no-load** tại đầu ra XL4015 bằng đồng hồ số: ghi `V_noload = ______ V`.
3. Đấu tải logic thật (TTL485 + PZEM khi được phép theo A-W03-02; nếu chưa được phép thì chỉ đo với tải giả hoặc bỏ qua bước này và ghi rõ lý do).
4. Đo **có tải** tại đầu ra: `V_load = ______ V`; nếu đồng hồ có chế độ đo dòng, ghi `I_logic = ______ mA`.
5. Đo nhiệt độ vỏ XL4015 sau ≥5 phút tải ổn định: `T_case = ______ °C`.
6. Đo ripple bằng scope nếu có (ghi rõ có/không có thiết bị): `Vpp = ______ mV`.
7. Tắt nguồn theo trình tự; ghi mọi bất thường.

**Cách ghi vào hồ sơ:** điền số vào bảng dưới (sửa trực tiếp khi phiên chạy xong) + ảnh đồng hồ; sau đó xóa nhãn `MEASUREMENT REQUIRED` ở `acceptance.md` A-W03-01 kèm ngày/người.

| Chỉ số | Giá trị W03 | Ngày | Người vận hành | Ghi chú |
|---|---|---|---|---|
| V_noload | *(trống — chưa đo)* | — | — | giá trị W01 cũ ~5 V chỉ là tham chiếu |
| V_load | *(trống)* | — | — | cần khi đã được phép đấu tải logic |
| I_logic | *(trống)* | — | — | |
| T_case | *(trống)* | — | — | |
| Vpp | *(trống)* | — | — | |
| Fuse | *(trống — chưa đo)* | — | — | xác nhận 5 A còn tốt (R04) |

**Cập nhật 2026-10-27:** phiên bench TEST 131/132B/133B **không** đo lại nhánh logic này.
Số `11.94–11.95 V` trong phiên đó là điện áp **nhánh TEC** đọc bởi PZEM, không phải đầu ra
XL4015; không được dùng để điền bảng trên. Bảng vẫn trống đúng như nhãn
`MEASUREMENT REQUIRED`.

## 4. Điều KHÔNG được suy diễn

- "XL4015 ~5 V" **không** đồng nghĩa mức logic RS-485 an toàn — TTL485 vẫn nhận rail 5 V và vấn đề `RO` vẫn nằm ở CR-A-W01-01.
- Giá trị no-load **không** đại diện cho điều kiện có tải (drop, ripple, nhiệt đều tăng khi tải).
- W03 **không** cấp tải dòng lớn; việc đo nhánh XL4015 không mở khóa bất kỳ bài TEC nào (việc đó thuộc W04 + H4).
