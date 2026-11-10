# A-W03-02 — RS-485 pin and compatibility assessment (Member A)

> **Cập nhật 2026-10-28:** chân RS-485 trong map v2 không đổi (`TX=GPIO36`,
> `RX=GPIO37`, AUTO, 9600 8N1, slave 0x01). GPIO35 **không còn** là DE/RE của
> map (nó là MC-38); `CG_RS485_DIR_MODE=0` và MANUAL+GPIO35 bị `#error`. Khác biệt
> TTL485-V2.0 vs MAX3485 (`CR-A-W01-01`) **vẫn mở** — đây là change review, không
> phải điều kiện phê duyệt chéo thành viên.

**Trạng thái: `PARTIAL` — `MEASUREMENT REQUIRED` cho mức logic (CR-A-W01-01).**
Hạn chế an toàn điện: module dùng rail 5 V, **không** nối thẳng vào GPIO37.

Nguồn duy nhất của "phần cứng thật" trong W03 là ảnh W01 + báo cáo người dùng; agent **không** đo lại và **không** cấp nguồn. File này thay cho deliverable `rs485-wiring.png`: **không vẽ lại sơ đồ từ trí nhớ** — sơ đồ chỉ được vẽ khi có ảnh thật + phép đo mức logic nằm trong change review `CR-A-W01-01` (khai báo MISSING ở `acceptance.md §3`).

## 1. Module thật (đọc từ ảnh W01)

| Quan sát | Ảnh | Ý nghĩa |
|---|---|---|
| Header 4 chân `GND / RXD / TXD / VCC`; cầu đấu `D+/A`, `D-/B`, `GND`; điện trở **120 Ω có jumper** | `02-rs485-front.jpg`, `03-rs485-back.jpg` | **Không có DE//RE** → auto-direction; kết cuối 120 Ω đóng/mở bằng jumper |
| Silkscreen `TTL485-V2.0` | `02-rs485-front.jpg` | Không phải MAX3485 (HW-07 freeze) |
| Chip | không ảnh nào đọc được marking | Không được ghi "MAX13487ESA" như sự thật đã xác minh; đó là **báo cáo người dùng** |

## 2. Ánh xạ chân (đề xuất pin map v1 — docs/01 §11.7) và những điều cấm

| Chức năng | ESP32 (pin map v1) | W01 bench (báo cáo) | Trạng thái W03 |
|---|---|---|---|
| UART TX → module `RXD` | **GPIO36** | 3.3 V trực tiếp vào RXD; đã "quan sát hoạt động", chưa chứng minh mức cao theo datasheet | Giữ nguyên pin; **không** chạy bài phần cứng |
| UART RX ← module `TXD` | **GPIO37** | TXD idle **5 V**; phân áp tạm 10k/10k/10k → **3.314 V đo được** (tính ≈ 3.33 V) | Giữ nguyên pin; **không** đo lại; mức logic `MEASUREMENT REQUIRED` |
| DE//RE | **GPIO35** | Module thật **không có chân DE//RE** | Build mặc định `CG_RS485_DIR_MODE 0` = AUTO → **GPIO35 không bị chạm**; MANUAL chỉ là compile-time option cho module MAX3485 canonical |
| VCC module | 5 V rail (XL4015) | — | Đúng theo module 5 V; xem `hardware-deviation-and-safety.md` |
| A/B | bus RS-485 tới PZEM | — | Chưa kiểm tra có điện; 120 Ω đầu cuối chỉ 1 vị trí |

## 3. Vì sao các bài UART phần cứng của W03 đang bị chặn

1. `CG_RS485_DIR_MODE 0` (AUTO) mới chỉ được xác nhận từ **ảnh** (không có DE//RE). Nếu chip thật không auto-direction đúng như giả định, khung truyền sẽ không bao giờ nghe thấy phản hồi — hoặc tệ hơn, mức RX vượt ngưỡng.
2. Mức RX phụ thuộc phân áp tạm **chưa được đo lại**; 3.314 V là số người dùng báo từ W01, không phải phép đo của phiên W03.
3. Cực tính A/B với PZEM chưa từng được kiểm tra có điện (PZEM chưa từng được firmware W03 poll).
4. Module có jumper 120 Ω — chưa xác định jumper đang đóng hay mở trong ảnh.

**Bổ sung 2026-10-27:** sketch Arduino bench (TEST 132B) trao đổi được **600/600** phản hồi
ở `9600 8N1`, slave `0x01`, qua đúng module TTL485-V2.0 as-built. Điều này chứng minh
**đường UART bench hoạt động ở cấu hình đã dùng** — hữu ích cho việc rà framing — nhưng
**không** chứng minh mức logic an toàn, **không** phải firmware ESP-IDF W03, và **không**
thay thế CR-A-W01-01. Bốn điểm chặn ở trên giữ nguyên.

## 4. Nội dung còn mở trong change review `CR-A-W01-01`

- Chấp nhận TTL485-V2.0 + phân áp tạm cho **bench**, kèm giới hạn thử nghiệm; **hoặc** yêu cầu mua module 3.3 V đúng freeze trước khi chạy.
- Xác nhận cách đấu đất (single reference) giữa ESP32, TTL485 và PZEM trên bench.
- Checklist "powered UART first-run": đo `RO`/`TXD` mức cao/thấp **bằng đồng hồ trước khi nối GPIO37**, chỉ nối sau khi có số đo ≤3.3 V.

## 5. Khi có phép đo, bằng chứng phải sinh ra (dự kiến)

- Log thật từ firmware: `#CG PZEM_CFG` (framing thật) + `#CG PZEM` OK đầu tiên + `#CG PZEM_RANGE` — tất cả vào `pzem-register-readback.txt` (hiện PENDING).
- Ảnh/ghi chú mức logic đo trước khi nối (đồng hồ), kèm tên người đo.
- Cập nhật `acceptance.md` A-W03-02 khỏi `MEASUREMENT REQUIRED` chỉ khi có cả hai điều trên.

Cho tới lúc đó: **không** bài UART thật nào được chạy, **không** trạng thái nào được nâng.

---

## 6. Cập nhật 2026-11-09 — thay thế được phê duyệt; bằng chứng giao tiếp trên ESP32 thật

**CR-A-W01-01 đã được phê duyệt:** project owner phê duyệt thay thế MAX3485 → **TTL485-V2.0** ngày 2026-11-09 (decision log `evidence/A/W01/freeze-deviation-review.md`; dòng BOM HW-07 chuyển `APPROVED_SUBSTITUTION`). Module TTL485-V2.0 là linh kiện as-built hợp lệ của CG-HW-001.

### 6.1 Nhận diện module (đọc từ ảnh W01 `02-rs485-front.jpg`, `03-rs485-back.jpg`)

- Silkscreen `TTL485-V2.0`; header 4 chân `GND / RXD / TXD / VCC`; cầu `A / B / GND`; điện trở 120 Ω có jumper.
- Chip `MAX13487ESA` do người dùng báo — **chưa đọc được trong ảnh**, vẫn là mục xác minh mở (không bị xóa bởi phê duyệt thay thế).

### 6.2 Yêu cầu nguồn và mapping chân (tương đương DI / RO / DE//RE / A / B)

| Chức năng canonical | Tương đương trên TTL485-V2.0 | Ghi chú |
|---|---|---|
| DI (driver in — ESP TX) | `RXD` | nhận 3.3 V trực tiếp từ GPIO36; hoạt động thực tế 600/600 bench + production |
| RO (receiver out — ESP RX) | `TXD` | TTL 5 V idle → phân áp 3×10 kΩ → **~3.314 V đo được tại GPIO37** (báo cáo bench W01) |
| DE//RE | **không có** — auto-direction trong chip | firmware mặc định `CG_RS485_DIR_MODE 0` (AUTO); GPIO35 (MANUAL) không được chạm |
| A / B | cầu A/B sang bus PZEM-017 | cực tính đã hoạt động trong TEST 131/132B/133B và mọi capture production |
| VCC | `VCC` = rail 5 V (XL4015) | theo đúng thiết kế module 5 V; **không** đấu TXD 5 V trực tiếp vào GPIO — chỉ qua phân áp |

### 6.3 Tương thích ESP32 — bằng chứng đã ghi

- TX ESP32 → `RXD`: mức 3.3 V; TEST 132B trao đổi **600/600** phản hồi Modbus `9600 8N1`, slave `0x01`, qua đúng module as-built.
- `TXD` → GPIO37: idle 5 V, qua phân áp → ~3.314 V (đo bench W01; agent không đo lại) — thỏa ngưỡng logic ≤3.4 V của evaluator.
- **ESP32 thật, firmware `cg-w06-0.1.0` (grammar 3):** mọi capture production poll PZEM 1 Hz liên tục qua đúng module này:
  - Dataset 2026-11-07 (PR #91, `evidence/A/SOURCES/20261107/datasets/quality_report.md`): 4 run S1 × 600 khung thermal/elec OK 600/600; S2 window OK full.
  - Capture 2026-11-09 (`evidence/A/SOURCES/20261109/s1/s1-20261109T081304Z/`): 600 khung, `electrical_valid_rate` 0.99667, 2 timeout PZEM startup khung đầu sau reset, voltage ổn định 11.95–11.96 V.
  → Chuỗi giao tiếp `PZEM → TTL485-V2.0 → phân áp → GPIO37 → firmware decode` đã hoạt động thực trên ESP32, không chỉ bench.

### 6.4 Giới hạn còn lại (không chặn phê duyệt thay thế)

- Marking chip vẫn do người dùng báo; datasheet MAX13487ESA chưa có trong repo.
- Mức 3.314 V tại GPIO37 chưa đo lại sau thời gian lắp dài; checklist "powered UART first-run" (đo RO/TXD bằng đồng hồ trước khi nối GPIO37) **vẫn bắt buộc cho lần đấu lại mạch kế tiếp**.
- Evaluator store `vcc_3v3` đo "VCC tại module" = 5.0 V (đúng bản chất module 5 V, không phải logic level). Khi chạy lại evaluator với ngữ nghĩa thay-thể-đã-duyệt, phải đối chiếu **mức logic tại GPIO37** (~3.314 V) — không được khai 3.3 V làm VCC module.
