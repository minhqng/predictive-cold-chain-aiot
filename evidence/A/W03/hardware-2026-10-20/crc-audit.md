# CRC audit — 7 mẫu `INVALID` của phiên OFF10 (2026-10-20)

**Trạng thái: `SUPPLEMENTARY ANALYSIS — NOT A ROOT-CAUSE CONCLUSION`.**
File này chỉ kiểm tra lại CRC của các frame thô đã có trong
`raw/pzem-off-serial.log`. Nó không chứng minh nguyên nhân lỗi, không chứng minh patch
RS-485 sửa được lỗi, và không thay đổi `acceptance.md`.

## 1. Cách kiểm

- Đọc 7 dòng `[MEAS] #RX_RAW n=1 ...` tương ứng 7 mẫu `quality=INVALID` trong
  `raw/pzem-off.csv` (đối chiếu timestamp).
- Cài CRC16/MODBUS độc lập bằng Python: init `0xFFFF`, poly `0xA001`, CRC thấp trước.
- Với mỗi raw frame, thử **mọi cửa sổ** 5, 7, 17 và 21 byte; một cửa sổ chỉ được tính là
  hợp lệ khi CRC của nó khớp hai byte cuối.
- Không sửa byte, không thêm/bớt prefix, không "đoán" frame đúng.

## 2. Kết quả

| `sample` CSV | Timestamp local | Dòng log | Raw bytes | Tail 21 byte (rút gọn) | CRC tail 21 | Cửa sổ CRC hợp lệ (5/7/17/21) |
|---:|---|---:|---:|---|---|---|
| 25 | 10:23:59.426 | 153 | 29 | `01 04 10 04 AC 00 … FB 92` | **FAIL** | 0 / 0 / 0 / 0 |
| 109 | 10:25:23.426 | 659 | 29 | `05 04 10 04 AC 00 … FB 92` | **FAIL** | 0 / 0 / 0 / 0 |
| 164 | 10:26:18.426 | 991 | 29 | `01 04 10 04 AC 00 05 … FB 92` | **FAIL** | 0 / 0 / 0 / 0 |
| 180 | 10:26:34.426 | 1089 | 29 | `01 04 10 04 AB … BC 90` | **FAIL** | 0 / 0 / 0 / 0 |
| 403 | 10:30:17.426 | 2429 | 29 | `01 04 10 04 AC … FB 92` | **FAIL** | 0 / 0 / 0 / 0 |
| 521 | 10:32:15.426 | 3139 | 28 | `01 04 10 04 AC … FB 9A` | **FAIL** | 0 / 0 / 0 / 0 |
| 527 | 10:32:21.426 | 3177 | 29 | `01 04 10 14 AC … FB 92` | **FAIL** | 0 / 0 / 0 / 0 |

Không có cửa sổ 21 byte nào trong cả 7 raw frame có CRC hợp lệ. Vì vậy đây không phải
trường hợp chỉ bị thừa echo/prefix mà tail vẫn là một frame CRC-đúng: **dữ liệu nhận được
đã hỏng ở mức byte/frame**.

## 3. Raw frame đầy đủ

```text
sample 25  (line 153): 01 04 00 00 00 08 F3 CC 01 04 10 04 AC 00 00 00 00 02 00 00 00 00 00 00 00 00 00 FB 92
sample 109 (line 659): 01 04 00 00 00 08 F1 CC 05 04 10 04 AC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FB 92
sample 164 (line 991): 01 04 00 00 00 08 F1 CC 01 04 10 04 AC 00 05 00 00 00 00 00 00 00 00 00 00 00 00 FB 92
sample 180 (line 1089): 01 04 00 00 00 08 F1 CC 01 04 10 04 AB 00 00 00 00 00 00 00 00 00 00 00 40 00 00 BC 90
sample 403 (line 2429): 01 04 00 00 00 08 F1 CC 01 04 10 04 AC 00 00 00 00 00 00 01 00 00 00 00 00 00 00 FB 92
sample 521 (line 3139): 01 04 00 80 08 F1 CC 01 04 10 04 AC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FB 9A
sample 527 (line 3177): 01 04 00 00 00 08 F1 CC 01 04 10 14 AC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 FB 92
```

## 4. Quan sát (không phải nguyên nhân)

1. Sáu frame có prefix 8 byte; trong đó năm frame gần request echo
   `01 04 00 00 00 08 F1 CC`, còn mẫu 25 dùng `F3 CC` ở hai byte CRC của request.
   Mẫu 521 chỉ có prefix 7 byte `01 04 00 80 08 F1 CC` (thiếu một byte và có `0x80`).
   Mẫu 109 có prefix 8 byte nhưng tail bắt đầu bằng `05` thay vì `01`.
2. Sáu tail có shape `01 04 10` (slave 1, FC04, byte count 16); mẫu 109 bắt đầu `05 04 10`,
   mẫu 527 có byte count `0x14` (20) thay vì `0x10` (16).
3. Các byte CRC cuối thay đổi (`FB 92`, `FB 9A`, `BC 90`) nhưng không khớp CRC của bất kỳ
   cửa sổ 21 byte nào. Có thêm byte lạ trong vùng dữ liệu (`00 05`, `00 40`, `01`).
4. Đây là các quan sát trên frame đã nhận; **không** đủ để kết luận lỗi do UART, driver
   RS-485, nhiễu, framing, hay phần mềm. Cần thí nghiệm riêng có kiểm soát.

## 5. Hệ quả cho patch và acceptance

- Patch echo/prefix trong firmware/host được thiết kế để chọn frame **kết thúc ở tail** và
  bỏ echo/prefix; nó **không thể** làm cho một frame CRC-sai trở thành hợp lệ.
- Vì vậy không được tuyên bố patch sửa 7 lỗi này. 594/601 mẫu hợp lệ chỉ là kết quả của
  sketch Arduino V4, không phải firmware ESP-IDF W03.
- Không có raw FC03 success frame cho readback `0x0001`; `raw/w3rstestlogshunt.txt` chỉ là
  log văn bản. A-W03-04 vẫn `PENDING_READBACK`.
- `pzem-off.csv` canonical của W03 vẫn **MISSING**; file trong `raw/` là schema bench.
- Trách nhiệm theo dõi và phân tích nguyên nhân gốc rễ cho 7 frame lỗi này (đặc biệt 2 frame lỗi request echo) được ghi ở mục **`TD-W03-11`** (`evidence/A/W03/team-dependencies.md`).
