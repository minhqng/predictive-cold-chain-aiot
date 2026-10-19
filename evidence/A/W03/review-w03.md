# W03 review tĩnh — một vòng đối kháng nội bộ (Member A)

**Ngày:** 2026-10-19 · **Phạm vi:** phần không cần phần cứng của A-W03-02…07.
**Thực hiện bởi:** Member A (vòng tự review đối kháng trước khi mở PR).

> **Giới hạn thẩm quyền (đọc trước):** đây **không** phải review độc lập của người thứ
> ba, **không** thay thế Member D, và **không** phải phê duyệt an toàn. Review độc lập
> của D/leader vẫn là điều kiện bắt buộc của CR-A-W01-01 và các mục `SAFETY REVIEW
> PENDING` trong `acceptance.md`. File này chỉ ghi lại *những gì đã được kiểm tra bằng
> máy/đọc code trong vòng này, kết quả ra sao, và cái gì còn tồn dư*.

## 1. Cách làm

Một vòng đọc code + chạy công cụ thật trên máy hiện tại, tập trung vào 5 vùng dễ sai nhất
theo yêu cầu review của W03: **CRC/scaling, UART/hướng truyền, tương thích mức logic
(phía firmware), IBT-2 default-OFF, và regression W02**. Mỗi mục dưới đây ghi *kiểm gì ·
bằng gì · kết quả*. Không mục nào được nâng thành hành vi phần cứng.

## 2. Kết quả từng mục

### R1 — CRC + scaling (A-W03-03/04)

- **Kiểm:** thuật toán CRC16/MODBUS (init `0xFFFF`, poly `0xA001`, low-byte-first), tính
  parity giữa firmware và host codec, thứ tự word của P/Wh, scaling từng đại lượng.
- **Bằng chứng chạy:** vector độc lập từ sketch bench W01 được tái tạo bằng code host:
  `crc16(010400000001) = 0xCA31`; `build_read_input(1) = 0104000000067008`;
  `build_read_range(1) = 010300030001740A`. Khung trả lời tự dựng
  (`append_crc`) được decode đúng: input `04AB` → 11.95 V; range `0001` → profile `50A`.
  Kiểm tra tĩnh W03 xác nhận **mọi hằng số register/scaling của firmware khớp
  `cg_modbus.py`** và không có literal FC ghi (`0x05/0x06/0x0F/0x10`).
- **Kết quả:** PASS. Thứ tự low-word-first của P/Wh có test đảo word chứng minh; scaling
  nằm trong `coldguard_config.h` và bị kiểm chéo, không rải rác trong code.

### R2 — Frame parser + timeout/retry (A-W03-03)

- **Kiểm:** phân loại lỗi, khung ngắn/khung nhiễu, dòng timeout (`rx=` rỗng), mẫu lỗi có
  lọt vào thống kê không, retry có bị chặn trên.
- **Bằng chứng chạy:** capture tổng hợp 1 dòng `TIMEOUT` (rx rỗng) + 1 dòng `OK` được
  parse sạch: dòng timeout cho `v=None`, `rx=''` (không crash, không tự bịa số); thống kê
  power chỉ tính **1/2 mẫu** (`n_valid=1/2`); link stats tách đúng `timeout_count=1`.
  Trong firmware, timeout/CRC/short-frame là các trạng thái **được phân loại**, vòng retry
  bounded bởi `CG_PZEM_MAX_ATTEMPTS` (static check khẳng định có bound).
- **Kết quả:** PASS. `nan` không bao giờ bị thay bằng giá trị cũ (đọc code `cg_power.c`
  `poll_once`: `values_valid` chỉ bật khi parse OK).

### R3 — Readback CLI (A-W03-04)

- **Kiểm:** công cụ `cg_pzem_readback.py` có thực sự từ chối dữ liệu bị sửa không.
- **Bằng chứng chạy:** capture CRC-đúng → `PZEM READBACK: DECODED` (exit 0). Sửa **1 byte
  CRC** của dòng range → `crc firmware/host: 1/0` + `PZEM READBACK: INCONSISTENT` (exit 1).
  Công cụ **không mở cổng serial** (chỉ đọc capture) nên không thể vô tình ghi register.
- **Kết quả:** PASS. Không có đường ghi register trong firmware lẫn công cụ (đã quét tĩnh).

### R4 — Ngân sách độ dài dòng log (rủi ro tràn buffer)

- **Kiểm:** dòng `#CG PZEM` dài nhất có vượt buffer `char line[256]` của `cg_log_line`
  không, và nếu vượt thì chuyện gì xảy ra.
- **Bằng chứng chạy:** dựng chuỗi với biên "thực tế xấu" (uptime 1 ngày, seq 5 chữ số,
  status `BAD_FUNCTION`, P/Wh max, `ok/fail` 6 chữ số, rx hex đầy 32 byte):
  **227 ký tự** — thừa margin 28 ký tự. Với giá trị vô lý (uptime 10¹³ ms ≈ 317 năm,
  `ok/fail` 10⁹) thì độ dài 267 > 255, nhưng khi đó `cg_log_line` **không cắt cụt** —
  nó thay cả dòng bằng `#CG ERR msg=log_line_overflow` (thiết kế sẵn trong `cg_log.c`),
  nên không bao giờ có dòng bị cắt ngầm hiểu sai.
- **Kết quả:** PASS (ghi chú tồn dư ở §4).

### R5 — UART / điều khiển hướng (A-W03-02 phía firmware)

- **Kiểm:** framing lấy từ macro; mặc định 8N1; không có chỗ hard-code 8N2; đường AUTO
  (as-built) không chạm GPIO35; nhánh MANUAL chỉ tồn tại sau `#if`; DE chỉ bật trong lúc
  tx và trả về RX trước khi đọc; timeout tx có giới hạn.
- **Bằng chứng:** đọc code `cg_rs485.c` + static check (framing macro, `UART_PIN_NO_CHANGE`
  cho RTS/CTS, guard `#error` cho data bits/parity/stop bits ngoài dải). Parser host chấp
  nhận token `framing=<8N1|8N2|8E1|8O1>` và **giữ nguyên** giá trị firmware in, không tự
  chuẩn hoá.
- **Kết quả:** PASS cho phần code. Hành vi vật lý vẫn `SAFETY REVIEW PENDING` (CR-A-W01-01).

### R6 — Tương thích mức logic (phía firmware, A-W03-02)

- **Kiểm:** firmware có hành vi nào có thể đấu 5 V/đẩy xung đột vào GPIO37 không; GPIO35
  trong chế độ AUTO có bị cấu hình gì không; pull nào được bật.
- **Bằng chứng:** `cg_rs485_init()` chỉ cấu hình UART1 trên TX=GPIO36/RX=GPIO37 (đúng pin
  map v1) và **không** cấu hình GPIO35 khi AUTO. Không có chỗ nào set output mức 1 lên bất
  kỳ chân RS-485. Ràng buộc "5 V TXD phải qua phân áp trước GPIO37" là ràng buộc **phần
  cứng**, được ghi trong `rs485-pin-and-compatibility.md` + `hardware-deviation-and-safety.md`.
- **Kết quả:** PASS cho phần "firmware không tạo thêm rủi ro"; quyết định mức logic vẫn
  thuộc **D + leader** (`CR-A-W01-01`, `acceptance.md` §5).

### R7 — IBT-2 default-OFF (A-W03-07)

- **Kiểm:** có nơi nào tạo PWM không; thứ tự ép OFF; guard từ chối đúng điều kiện; boot
  order; ghi mức 1 có tồn tại không.
- **Bằng chứng:** quét toàn bộ `firmware/main/*.c`: **không có** `ledc`/`mcpwm` nào ngoài
  comment/counter; `cg_actuator_force_off()` được gọi **đầu tiên** trong `app_main` (trước
  NVS/task/sensor/PZEM); thân hàm xóa `ENABLE` trước `RPWM`; `cg_actuator_outputs_allowed()`
  từ chối khi quá dải / hai chiều đối nghịch / chưa authorization / `CG_ACTUATOR_ENABLE_ALLOWED=0`.
  Static check W03 khẳng định lại các bất biến này (không có literal ghi 1 lên RPWM/ENABLE).
- **Kết quả:** PASS cho phần code. Phần phần cứng (cold-boot log, tie-off `LPWM`/`L_EN`)
  vẫn `SAFETY REVIEW PENDING (D)`.

### R8 — Regression W02

- **Kiểm:** nhánh W03 không làm hỏng firmware/evidence W02.
- **Bằng chứng chạy:** `cg_check_firmware.py` → **39 check PASS**; `validate_w02.py` →
  **W02 STRUCTURE PASS (9/9 blob hash verified)**; bộ unittest gồm cả các test W02 cũ →
  **113/113 PASS** (57 test W02 không sửa).
- **Kết quả:** PASS. Lệnh W02 (`cg_build_sensor_csv.py`, `cg_verify_reboots.py`…) còn
  nguyên; grammar v2 chỉ **thêm** line kind mới.

## 3. Finding trong vòng này

| ID | Mức | Nội dung | Trạng thái |
|---|---|---|---|
| — | — | Không phát hiện defect chặn mới nào trong 8 mục trên. Các lỗi tìm thấy trong quá trình phát triển (kỳ vọng test `BAD_LENGTH` vs `BAD_FUNCTION`, check tĩnh yếu, đóng gói thiếu log W02) đã được **sửa trước** vòng review này và được submit kèm PR. | — |

## 4. Ghi chú tồn dư (không phải defect — người sau phải biết)

1. **Margin buffer log (R4):** trong phiên bench thật (giờ), dòng `PZEM` dài nhất ~230 ký
   tự. Chỉ khi vận hành nhiều năm (uptime 10¹¹ ms) hoặc bộ đếm `ok/fail` cỡ 10⁸ thì dòng
   chạm ngưỡng 255 và bị thay bằng `#CG ERR msg=log_line_overflow` — khi đó log nói rõ
   "line overflow", không có dòng cắt cụt. Nếu W04+ chạy dài ngày, cân nhắc nâng buffer
   (một dòng trong `cg_log.c`) — **không** đổi trong W03 để giữ diff tối thiểu.
2. **Nhánh MANUAL (MAX3485 canonical) không được build trong CI:** mặc định là AUTO theo
   phần cứng as-built; nhánh `#if CG_RS485_DIR_MODE == 1` chưa từng được compiler kiểm.
   Đúng như thiết kế (không fake "đã chạy"), nhưng nếu D/leader chọn thay module MAX3485
   đúng freeze thì phải thêm build variant đổi macro trước khi tin nhánh đó.
3. **GPIO35/36/37 và module S3 octal:** trên một số module ESP32-S3 dùng flash/PSRAM
   octal, các chân 33–37 thuộc SPI0/1. Pin map là v1 (đã có từ W02, docs/01 §11.7) và
   các chân này chưa từng được **kiểm tra vật lý trong W03** (UART chưa chạy). Nội dung
   này **thuộc CR-A-W01-01**: khi D/leader duyệt mức logic RS-485, xác nhận luôn board
   as-built cho phép các chân này (board W02 đã chạy thật với GPIO34; GPIO36/37 chưa được
   kiểm trong bất kỳ log nào của repo).
4. **MANUAL DE delay:** nhánh MANUAL dùng `uart_wait_tx_done` + 1 tick trước khi trả RX —
   hợp lý cho 9600 baud, nhưng chưa đo trên phần cứng; thuộc cùng buổi test CR-A-W01-01
   nếu module được thay.

## 5. Không thuộc phạm vi vòng review này

- Mọi hành vi phần cứng (RS-485 thật, PZEM thật, nhiễu điện, nhiệt, EMC).
- `43 A` / thông số IBT-2 trên tải — là câu hỏi định mức module, D trả lời khi duyệt wiring.
- Nghiệm thu W03 (acceptance matrix) — W03 **vẫn NOT PASS**; file này không đổi trạng thái nào.

## 6. Phụ lục — phát hiện sau review: lỗi compile từ CI vòng đầu (2026-10-19)

Vòng review ở trên chỉ dùng được công cụ **không có compiler**; lớp compile thật (CI) đã
bắt thêm một defect mà mọi lớp trước đó đều mù:

- **F1 (đã sửa):** run CI đầu tiên (commit `5a6cb1f`) fail:
  `coldguard_config.h:151:29: error: expected identifier before numeric constant`.
  Nguyên nhân: macro `CG_RS485_DIR_MANUAL` (config) trùng tên enum constant `CG_RS485_DIR_MANUAL`
  trong `cg_rs485.h`; ở TU include config trước header (`cg_power.c`), macro được expand
  ngay trong khai báo enum. Lớp static check + unittest **không** mô hình hoá tiền xử lý C
  nên không thể bắt (và test hành vi là mô hình Python — đúng giới hạn đã khai báo ở
  `firmware-tooling-verification.md` §6).
  **Fix:** commit `b858693` — enum → `CG_RS485_MODE_AUTO/MANUAL`, `cg_rs485.c`/`cg_power.c`
  cập nhật theo; macro compile-time giữ nguyên. Quét bổ sung toàn bộ `firmware/main` cho
  xung đột macro↔enum: **hết**. 5 lớp cục bộ sau fix: **5/5 PASS**. CI được push lại và
  kết quả ghi ở `build-report-w03.md` (kèm cả FAIL đầu tiên để truy vết).

**Bài học ghi lại cho W04:** thêm build variant / compile smoke test cho các nhánh macro
không mặc định; và không đặt enum constant trùng tên macro config trong cùng codebase.
