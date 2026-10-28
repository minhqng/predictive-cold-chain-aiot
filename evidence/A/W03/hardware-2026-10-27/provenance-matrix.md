# Provenance matrix — phiên bench 2026-10-27

**Mục đích:** mỗi câu trong bộ hồ sơ W03 phải trả lời được "câu này thuộc loại bằng chứng
nào". Ma trận này là nơi tra cứu duy nhất cho phiên 2026-10-27; nó **không** nâng bất kỳ
nhãn nào trong `../acceptance.md` và **không** thay `acceptance.md`.

## 0. Bốn lớp bằng chứng dùng trong hồ sơ này

| Lớp | Định nghĩa | Được dùng để |
|---|---|---|
| `MEASURED` | Có file gốc trong repo, hash được pin, đọc lại được bằng script | Khẳng định số liệu **trong phạm vi file đó** |
| `OPERATOR-REPORTED` | Chỉ có lời khai/số đọc của người vận hành, không có file gốc | Ghi nhận quan sát; **không** dùng làm điều kiện PASS |
| `INFERRED` | Suy ra bằng toán/độ dài từ dữ liệu `MEASURED` | Giải thích cơ chế; phải ghi rõ là suy luận |
| `NOT MEASURED` | Không có dữ liệu | Giữ nguyên `MEASUREMENT REQUIRED` / `PENDING` |

Nguyên tắc: **không** có phép nâng lớp. Một `OPERATOR-REPORTED` không trở thành `MEASURED`
vì nó "khớp với kỳ vọng", và một `INFERRED` không trở thành phép đo vì nó đúng về mặt số học.

## 1. TEST 132B — OFF envelope (Arduino bench)

File gốc: `raw/test-132b-off-envelope.log` (SHA-256 `0af8a083…`, 20 618 B) và bản trích
`raw/test-132b-off-envelope.csv` (SHA-256 `7eac5f80…`, 600 hàng + header).

| # | Câu | Lớp | Nguồn | Chứng minh được | KHÔNG chứng minh |
|---|---|---|---|---|---|
| P1 | Có 600 hàng CSV, mọi hàng `valid=1`, `status=OK` | `MEASURED` | CSV + parser | Phiên ghi được 600 phản hồi được thiết bị coi là hợp lệ | Không chứng minh nội dung vật lý của phản hồi (không có raw frame) |
| P2 | `V` min/max/mean = `11.94/11.95/11.9483 V` | `MEASURED` | CSV | Điện áp nhánh trong cửa sổ đó nằm ở mức này theo PZEM | Không chứng minh độ chính xác tuyệt đối của PZEM (chưa hiệu chuẩn) |
| P3 | `I=0.00 A`, `P=0.0 W`, `E=0 Wh` ở mọi hàng | `MEASURED` (giá trị hiển thị) | CSV | Dưới độ phân giải hiển thị `0.01 A` / `0.1 W` | **Không** phải "dòng bằng 0 tuyệt đối"; không phát hiện được dòng rò nhỏ |
| P4 | `rx_len = 29` ở mọi hàng | `MEASURED` (độ dài) → `INFERRED` (cấu trúc) | CSV | Độ dài khung nhận là 29 byte | Cấu trúc "21 byte FC04 + 8 byte echo/prefix" là **suy luận từ độ dài**, không đọc raw frame |
| P5 | Cửa sổ mẫu `10 ms` → `599000 ms` = **598.99 s** | `MEASURED` | CSV (cột `elapsed_ms`) | 600 mẫu ở 1 Hz phủ 599 khoảng | Không phải 600.00 s; giây cuối không có mẫu (xem `TD-W03-04`) |
| P6 | `DURATION_MS 600000`, `SUCCESS_RATE 100.00 %` | `MEASURED` | summary trong log | Hằng số thời lượng của test và tỉ lệ hợp lệ do thiết bị tự tính | `DURATION_MS` là **hằng số test**, không phải span timestamp |
| P7 | Gate của log là `RESULT: REVIEW REQUIRED` | `MEASURED` | summary | Thiết bị **không** tự kết luận PASS | Người vận hành gọi là PASS — hồ sơ giữ cả hai, không nâng gate |
| P8 | TEC OFF trong suốt 598.99 s | `OPERATOR-REPORTED` | lời khai vận hành | Người vận hành khẳng định đã tắt TEC | Không có kênh đo độc lập; `I=0.00 A` **không** tự chứng minh TEC không được cấp nguồn |
| P9 | Đây là firmware ESP-IDF W03 | **SAI — không dùng** | log thiếu `#CG PZEM_CFG`/`#CG PZEM_RANGE` | — | Đây là sketch Arduino bench; firmware W03 **chưa** chạy trên board |

## 2. TEST 131 — 50 A profile readback

| # | Câu | Lớp | Nguồn | Chứng minh được | KHÔNG chứng minh |
|---|---|---|---|---|---|
| P10 | Frame `01 03 02 00 01 79 84` xuất hiện | `OPERATOR-REPORTED` | lời khai vận hành | Có một frame được báo là phản hồi thật | Không có file capture gốc → `RAW CAPTURE FILE NOT AVAILABLE` |
| P11 | CRC16/MODBUS của 5 byte đầu = `0x8479` → on-wire `79 84` | `MEASURED` (tính lại host-side) | `verify_test132b.py` | Frame **tự nhất quán** về CRC | Frame tự nhất quán **không** chứng minh nó đến từ module (không có timestamp/transport log) |
| P12 | `0x0001` = profile 50 A | `MEASURED` (tra bảng) | `docs/01 §9.3` + frame | Giá trị register ứng với 50 A theo tài liệu | Không chứng minh register đang được **ghi** đúng trên module ở thời điểm khác |
| P13 | Hai phản hồi đầu không hợp lệ, sau đó ba phản hồi hợp lệ | `OPERATOR-REPORTED` | lời khai vận hành | Chuỗi quan sát có lỗi rồi mới ổn | Không có byte của hai phản hồi lỗi → không suy được nguyên nhân |
| P14 | Đọc bằng firmware ESP-IDF W03 (`#CG PZEM_RANGE`) | `NOT MEASURED` | — | — | A-W03-04 vẫn cần một lần `cg_pzem_readback.py` trên log thật |

## 3. TEST 133B — reset / default-OFF

| # | Câu | Lớp | Nguồn | Chứng minh được | KHÔNG chứng minh |
|---|---|---|---|---|---|
| P15 | Sketch TEST 133B tồn tại và có nội dung như mô tả | `MEASURED` | `firmware/ColdGuard_TEST_133B_reset_default_off.ino` (`8986a21c…`) | Test đã được định nghĩa: 20 s/cửa sổ, 1 Hz, `RPWM=5 / R_EN=6 / L_EN=10` | Sketch là **định nghĩa test**, không phải firmware W03 và không phải bằng chứng đã chạy |
| P16 | 6 cửa sổ × 20 mẫu = **120/120** hợp lệ, `0.00 A`, `0.0 W` | `OPERATOR-REPORTED` | lời khai vận hành | Quan sát điện sau khi firmware chạy: không thấy dòng | Không có log/CSV gốc; số học 6×20 khớp nhưng vẫn là lời khai |
| P17 | 5 lần `ESP.restart()` + cold boot thủ công vẫn OFF | `OPERATOR-REPORTED` | lời khai vận hành | Người vận hành quan sát hệ thống vẫn OFF | Không có bảng đếm/timestamp; không phải log reset |
| P18 | `RPWM: LOW / R_EN: LOW / L_EN: LOW` | **HẰNG CHUỖI DO SKETCH IN — không phải phép đo** | source sketch | Sketch in đúng chuỗi đó | Không đọc lại trạng thái chân, không scope/logic analyzer |
| P19 | Trước `setup()` các chân đã ở 0 | `NOT MEASURED` | — | — | `SCOPE: AFTER FIRMWARE START ONLY` — sketch tự giới hạn phạm vi |
| P20 | `L_EN` nối `GPIO10` trên board as-built | `OPERATOR-REPORTED` | lời khai vận hành | Có khả năng đấu dây như vậy | Xung đột cũ với W02 (`CG_PIN_DS18B20_DATA 10`) **đã giải quyết 2026-10-28** bằng map v2 (DS18B20→GPIO33, L_EN=10); `TD-W03-03` RESOLVED (firmware). Vẫn chờ D đo continuity |

## 4. Shunt / đường dòng

| # | Câu | Lớp | Nguồn | Chứng minh được | KHÔNG chứng minh |
|---|---|---|---|---|---|
| P21 | `IBT-2 B−` ↔ `GND logic` ≈ `0 Ω` | `OPERATOR-REPORTED` | số đọc DMM | Có đường common thấp trở giữa hai điểm trong trạng thái đã đo | Không phải `0.000 Ω`; không có model đồng hồ/ảnh màn hình |
| P22 | `B−` ↔ `PSU−` ≈ `453 kΩ` khi tách shunt | `OPERATOR-REPORTED` | số đọc DMM | Đường hồi bị tách ở trạng thái đó | Không chứng minh cách ly an toàn dưới tải/điện áp |
| P23 | Continuity `GND logic` ↔ `GND IBT-2` sau khi nối lại | `OPERATOR-REPORTED` | số đọc DMM | Có common ground khi lắp lại | Không chứng minh topology return đúng cho dòng TEC |
| P24 | `VCC logic IBT-2` ↔ `GND logic` ≈ `24–25 kΩ` khi nguồn OFF | `OPERATOR-REPORTED` | số đọc DMM | Không thấy short tĩnh | Không phải kiểm tra dưới tải |
| P25 | Dòng ≈ `0.98 A` ở PWM 10% thời gian ngắn | `OPERATOR-REPORTED` | PZEM/ghi nhận | Đường dòng **có thể** dẫn một ít dòng qua shunt | Không phải thử tải 50 A, không đo nhiệt, không characterization dưới PWM |
| P26 | Failure mode khi shunt hở: dòng hồi có thể đi qua GND logic | `INFERRED` (giả thuyết) | P21 + topology `B−` common GND | Một đường dẫn không định mức **có thể** tồn tại | **Chưa xảy ra sự cố nào**; mức độ phụ thuộc topology/dòng tải. D phải quyết định (`TD-W03-02`) |
| P27 | Đường dòng đúng nhánh, Kelvin sense, đầu cốt chắc | `NOT MEASURED` | — | — | Không nhìn thấy trong ảnh W01; không có pull-test |

## 5. Nguồn / rail / cấu hình

| # | Câu | Lớp | Nguồn | Ghi chú |
|---|---|---|---|---|
| P28 | XL4015 out `5.00 V` (no-load) | `OPERATOR-REPORTED` (W01) | `bom-audit.csv` HW-13 | Ripple/nhiệt/dòng tải `NOT MEASURED` |
| P29 | TB4506 rail `4.99 V` | `OPERATOR-REPORTED` (W01) | `bom-audit.csv` HW-13 | `CR-A-W01-02` PENDING |
| P30 | Phân áp RX `10k/10k/10k` → ~`3.314 V` tại GPIO37 | `OPERATOR-REPORTED` (W01) | lời khai + ảnh | Không đo lại trong phiên này; chưa được D duyệt |
| P31 | Chip RS-485 là `MAX13487ESA` | `OPERATOR-REPORTED` | lời khai | **Không** ảnh nào đọc được marking |
| P32 | Nhãn shunt in `50A 75mV`, khắc `FL-2 0.5` | `MEASURED` (ảnh W01) | `photos/18`, `photos/04` | Chỉ là marking vật lý, **không** phải cấu hình PZEM |
| P33 | Framing `9600 8N1`, slave `0x01` | `INFERRED` từ TEST 132B (600/600 hợp lệ) | CSV + sketch | Hoạt động ở cấu hình đã dùng; không chứng minh an toàn mức logic |
| P34 | `hardware_config_id` | `NOT ASSIGNED` | — | Chưa gán; cần gán (`TD-W03-08`) |

## 6. Cách tái kiểm

```text
py evidence/A/W03/hardware-2026-10-27/verify_test132b.py
```

Script in lại hash, số hàng, min/max/mean, `rx_len`, span, CRC TEST 131 và gate
`REVIEW REQUIRED`. Script **không** mở cổng serial, **không** đọc lại thiết bị, và **không**
có khả năng nâng bất kỳ nhãn nào.

## 7. Điều ma trận này cố ý không làm

- Không gộp `OPERATOR-REPORTED` vào `MEASURED` để làm hồ sơ "đẹp".
- Không biến `INFERRED` thành kết luận an toàn.
- Không tạo raw frame/CSV/ảnh cho ba hạng mục chỉ có lời khai (TEST 131, TEST 133B,
  shunt continuity).
- Không thay `../acceptance.md`: kết luận tổng hợp nằm ở đó (`DONE` / `PARTIAL` /
  `HARDWARE-LIMITED` / `NOT IMPLEMENTED` / `INFRASTRUCTURE-LIMITED`).
