# W03 Arduino bench archive — 2026-10-20

**Trạng thái: `SUPPLEMENTARY BENCH ARCHIVE — NOT ESP-IDF W03 ACCEPTANCE`**
**W03 tổng thể vẫn `W03 NOT PASS`.** Thư mục này không thay đổi `acceptance.md`, không
thay thế `pzem-off.csv` canonical, và không chứng minh firmware W03 đã chạy trên phần cứng.

## 1. Nguồn và tính toàn vẹn

Bảy file nguồn dưới đây được sao chép **byte-for-byte** từ `C:\Users\dlbac\Downloads` (không
giải nén ZIP, không dựng lại log, không sửa CSV). SHA-256 của bản sao khớp (a) hash tính
lại tại chỗ và (b) **7/7 tiền tố hash** mà audit read-only ngày 2026-10-20 đã ghi; hash
đầy đủ được tính lại và pin trong `SHA256SUMS.txt`. Dòng `ARCHIVE-ONLY-WARNING.txt` chỉ là
cảnh báo, không phải file nguồn và không nằm trong danh sách hash. `.gitattributes` đánh dấu
`raw/**` là `-text` để Git không chuẩn hóa CRLF; nếu thiếu quy tắc này, `git add` có thể đổi
byte của ba file CRLF và làm sai SHA-256. Kiểm tra lại bằng:

```text
py evidence/A/W03/hardware-2026-10-20/verify_capture.py
```

| File trong archive | Byte | SHA-256 (rút gọn) | Nội dung |
|---|---:|---|---|
| `raw/pzem-off.csv` | 46.770 | `2dfdcb…` | 601 dòng dữ liệu + header; schema bench (không phải canonical W03) |
| `raw/pzem-off-serial.log` | 486.205 | `85b3da…` | 3.627 dòng log serial gốc của phiên OFF10 |
| `raw/w3testlog.txt` | 1.212 | `4cb246…` | Log SET50 một lần; có FC06 — **archive-only** |
| `raw/w3rstestlogshunt.txt` | 350 | `3aedc0…` | Log riêng; chỉ có `prefix=8` + `raw=0x0001`, **không có hex FC03** |
| `firmware/ColdGuard_W03_TTL485_V4_8N1_TEST.ino` | 9.474 | `21ff99…` | Sketch Arduino V4 8N1 đã dùng cho phiên OFF10 |
| `firmware/ColdGuard_W03_TTL485_SET50A_ONCE_8N1.ino` | 8.114 | `d4febb…` | Sketch SET50 có FC06 — **archive-only** |
| `firmware/ARCHIVE-ONLY-WARNING.txt` | — | — | Cảnh báo đặt cạnh sketch SET50: **không flash/chạy/FC06** |
| `tools/ColdGuard_W03_PZEM_OFF10_COM4_8N1.py` | 9.631 | `d40aee…` | Collector COM4 read-only dùng cho phiên OFF10 |

## 2. Kết quả phiên OFF10 (Arduino bench, không phải ESP-IDF)

Dòng kết quả cuối trong `raw/pzem-off-serial.log`:

```text
#OFF10_RESULT gate=COLLECTED_WITH_ERRORS samples=601/601 valid=594 invalid=7 sample_span_s=600.000 runtime_s=600.099 csv=pzem-off.csv raw_log=pzem-off-serial.log
```

- 601 mẫu, 594 `CRC_VALID`, 7 `INVALID`, span `600.000 s`.
- Collector tự chốt `COLLECTED_WITH_ERRORS`, **không** phải `PASS`.
- 7 mẫu lỗi có raw frame trong log; không có cửa sổ 5/7/17/21 byte nào có CRC hợp lệ
  (xem `crc-audit.md`). Đây là quan sát CRC, **không** phải kết luận nguyên nhân gốc.
- 594 mẫu `CRC_VALID` đều ghi `current_a=0.00`, `power_w=0.0`; 7 mẫu `INVALID` để trống.
  Điều này **không** chứng minh TEC OFF, không chứng minh tải 50 A, và không chứng minh
  patch RS-485 sửa được 7 lỗi.

## 3. Ranh giới và cảnh báo

> **ARCHIVE ONLY — DO NOT FLASH OR EXECUTE**
> `firmware/ColdGuard_W03_TTL485_SET50A_ONCE_8N1.ino` và `raw/w3testlog.txt` chứa lệnh
> **FC06** (`01 06 00 03 00 01 B8 0A`). Không nạp sketch, không gửi lại FC06, không mở COM,
> không điều khiển TEC/IBT-2 từ archive này. Log đó chỉ được đọc để điều tra.

- `raw/w3testlog.txt` ghi một lần FC06 SET50 đã được phát (TX) trong phiên bench ngoài W03;
  RX in ra hai khung giống nhau nên tool ghi `#WRITE50_RX_ACK_OR_ECHO_UNTRUSTED`. Sau đó
  có 3 dòng `#READ_PASS ... shunt_reg=0x0001` và `#SET50_VERIFIED PASS`, nhưng **không có
  tx/rx hex của FC03**. Vì vậy đây không phải raw FC03 success frame và không đủ cho
  A-W03-04.
- `raw/w3rstestlogshunt.txt` chỉ xác nhận lại `raw=0x0001` ở mức log văn bản;
  vẫn không có hex tx/rx, CRC, hay decode host-side. Không dùng làm `#CG PZEM_RANGE`.
- FC06 là hành vi **ngoài** hợp đồng read-only của W03. Không được đưa sketch này vào
  firmware, không được chạy lại; D/leader phải xử lý như một sai lệch quy trình bench.
- Nhãn trong log `via_existing_5k_10k_divider` là nhãn do sketch in; **không** được diễn
  giải thành "5 kΩ tương đương" khi chưa kiểm tra topology. Tài liệu W01 mô tả
  10k/10k/10k; đây vẫn là mạch tạm chưa được duyệt.

## 4. Những gì archive này KHÔNG chứng minh

| Hạng mục | Trạng thái sau archive |
|---|---|
| Firmware ESP-IDF W03 chạy trên board | **CHƯA** — không có log `#CG PZEM_*` của ESP-IDF |
| Patch echo/prefix sửa 7 lỗi quan sát | **CHƯA CHỨNG MINH** — 7 frame vẫn CRC-invalid; patch chỉ được test host (Python unittest + static checks) |
| `pzem-off.csv` canonical của W03 | **MISSING** — file trong `raw/` có schema bench khác, không được copy lên root |
| A-W03-04 readback 50 A | **PENDING_READBACK** — chỉ có log văn bản `0x0001`, không có raw FC03 |
| Tải 50 A thật | **CHƯA** — 594 mẫu hợp lệ đều `current_a=0.00`, 7 mẫu lỗi để trống; không có tải |
| TEC OFF envelope | **CHƯA** — TEC OFF chỉ là xác nhận của người vận hành, không được đo độc lập |
| IBT-2 cold-boot/reset | **NOT RUN** — VCC/EN/PWM/disconnected chỉ là số đo tay, không phải boot log |
| CR-A-W01-01 (TTL485 5 V vs MAX3485 3.3 V) | **PENDING** — archive không thay đổi quyết định D + leader |

## 5. Đọc tiếp

- `crc-audit.md` — 7 raw frame, CRC độc lập, không kết luận root cause.
- `../pzem-register-readback.txt` — trạng thái `PENDING_READBACK` và khác biệt canonical.
- `../hardware-deviation-and-safety.md` — ranh giới an toàn và các số đo tay.
- `../acceptance.md` — nguồn trạng thái duy nhất; W03 vẫn `NOT PASS`.
