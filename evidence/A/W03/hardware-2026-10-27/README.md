# W03 bench evidence — 2026-10-27 (TEST 131 / 132B / 133B + shunt continuity)

**Trạng thái: `SUPPLEMENTARY BENCH EVIDENCE — NOT ESP-IDF W03 RUNTIME`**
Thư mục này **không** phải nghiệm thu W03, không thay `../acceptance.md`, và không chứng
minh firmware ESP-IDF W03 đã chạy trên board.

## 1. Nguồn, ngày và người vận hành

| Trường | Giá trị |
|---|---|
| Ngày nhận bằng chứng | `2026-10-27` (ngày nhận file; log không tự ghi ngày) |
| Người vận hành | Member A (không ghi tên cá nhân trong repo) |
| Thiết bị | PZEM-017 + shunt `50A 75mV`; TTL485-V2.0 5 V; ESP32-S3; IBT-2 (HW-039) |
| Test ID | `TEST 131` (profile), `TEST 132B` (OFF envelope), `TEST 133B` (reset/default-OFF) |
| Firmware chạy test | **Sketch Arduino bench**, không phải firmware ESP-IDF W03 (`#CG PZEM` grammar) |
| `hardware_config_id` | `NOT_ASSIGNED` |
| `firmware_commit` (ESP-IDF W03) | xem `../firmware-tooling-verification.md`; **không** phải firmware đã chạy các test này |
| TEC | OFF theo xác nhận của người vận hành; không có kênh đo độc lập |
| Tải TEC | **Không** chạy tải lớn; chỉ có một lần quan sát ~0.98 A ở PWM 10% thời gian ngắn |

Bằng chứng được người vận hành cung cấp dưới dạng file đính kèm. Repo chỉ lưu những gì
thực sự nhận được; không dựng lại log, không chèn hex, không tạo ảnh.

## 2. File và tính toàn vẹn

| File | Byte | SHA-256 (rút gọn) | Nội dung |
|---|---:|---|---|
| `raw/test-132b-off-envelope.log` | 20.618 | `0af8a083…` | Bản sao **byte-for-byte** của file đính kèm TEST 132B (CRLF giữ nguyên) |
| `raw/test-132b-off-envelope.csv` | 19.157 | `7eac5f80…` | Trích khối `CSV_BEGIN…CSV_END` từ log (600 hàng + header); nội dung dữ liệu trùng khớp từng dòng, chuẩn hóa xuống dòng sang LF (log gốc dùng CRLF) |
| `firmware/ColdGuard_TEST_133B_reset_default_off.ino` | 9.993 | `8986a21c…` | Sketch TEST 133B do người vận hành cung cấp; định nghĩa test, **không** phải firmware W03 |
| `verify_test132b.py` | — | — | Verifier read-only: hash, CSV, summary, cửa sổ mẫu, CRC TEST 131, gate `REVIEW REQUIRED` |
| `test-131-profile-readback.md` | — | — | A-W03-04: frame 50 A + CRC host-side + provenance |
| `test-133b-reset-default-off.md` | — | — | A-W03-07: 120/120 mẫu reset, giới hạn bằng chứng |
| `shunt-continuity.md` | — | — | A-W03-06: continuity + failure mode chờ D |
| `as-built-configuration.md` | — | — | Pin/power/RS-485/shunt as-built và lệch cấu hình GPIO10 |
| `provenance-matrix.md` | — | — | Phân loại từng claim: đo / người vận hành báo / suy ra / chưa đo |
| `SHA256SUMS.txt` | — | — | Hash đầy đủ của 3 file nguồn |

`verify_test132b.py` kiểm tra lại:

```text
py evidence/A/W03/hardware-2026-10-27/verify_test132b.py
```

## 3. Kết quả TEST 132B (A-W03-05, bench)

| Chỉ số | Giá trị trong log | Cách kiểm tra |
|---|---|---|
| Thời lượng lệnh test | `600000 ms` | summary |
| Mẫu | **600** hàng CSV | đếm bằng parser |
| Hợp lệ / lỗi | **600 / 0** (`valid=1`, `status=OK`) | parser |
| Success rate | `100.00 %` | summary + parser |
| Điện áp | min/max `11.94 / 11.95 V`; mean `11.9483 V` | parser; summary ghi `11.948` |
| Dòng | `0.00 A` mọi hàng | parser |
| Công suất | `0.0 W` mọi hàng | parser |
| Energy | `0 Wh` mọi hàng | parser |
| `rx_len` | `29` mọi hàng | parser |
| Cửa sổ mẫu | mẫu đầu `10 ms`, mẫu cuối `599000 ms` → **598.99 s** | parser |
| Gate của log | **`RESULT: REVIEW REQUIRED`** | summary |

**Ba điểm không được che:**

1. **Đây là sketch Arduino bench**, không phải firmware ESP-IDF W03. Log không có
   `#CG PZEM_CFG` / `#CG PZEM_RANGE`, nên không thay thế bài chạy firmware W03.
2. **Log tự kết luận `REVIEW REQUIRED`**, không phải `PASS`. Người vận hành gọi kết quả là
   PASS; hồ sơ này ghi cả hai và **không** tự nâng gate của thiết bị.
3. **Cửa sổ mẫu là 598.99 s**, không phải 600.00 s: 600 mẫu ở 1 Hz phủ 599 khoảng, mẫu cuối
   ở giây thứ 599; giây cuối của test không có mẫu. `DURATION_MS: 600000` là hằng số thời
   lượng của test, không phải span timestamp. Việc chấp nhận "≥10 phút" theo nghĩa nào là
   quyết định của D (xem `../team-dependencies.md`).

`rx_len = 29` nhất quán với một response FC04 8-register dài 21 byte cộng 8 byte
echo/prefix; đây là **suy ra từ độ dài**, không phải đọc raw frame (log không chứa raw frame).

## 4. Quan hệ với archive 2026-10-20

Archive `../hardware-2026-10-20/` là một phiên Arduino khác: **601 mẫu, 594 hợp lệ, 7 lỗi**,
gate `COLLECTED_WITH_ERRORS`. Phiên 2026-10-27 có **600/600 hợp lệ**.

- Phiên mới **không** chứng minh nguyên nhân 7 frame lỗi cũ đã được sửa; đây là phiên khác,
  không có raw frame để so sánh.
- Archive cũ **không bị xóa** và vẫn là provenance của các lần lỗi.
- Không dùng phiên mới để nâng bất kỳ kết luận nào về ESP-IDF W03.

## 5. Điều thư mục này KHÔNG chứng minh

| Hạng mục | Trạng thái |
|---|---|
| Firmware ESP-IDF W03 chạy trên board | **NOT RUN** — không có log `#CG PZEM_*` |
| TEC thực sự OFF trong suốt cửa sổ đo thực tế 598.99 s | **OPERATOR-REPORTED** — không có kênh đo độc lập |
| Dòng/công suất bằng 0 tuyệt đối | **KHÔNG** — chỉ dưới độ phân giải hiển thị `0.01 A` / `0.1 W` |
| Tải 50 A | **KHÔNG** — không có tải lớn |
| Shunt an toàn khi chạy tải lớn | **KHÔNG** — xem `shunt-continuity.md` |
| Cách ly/duyệt mức logic RS-485 5 V | **KHÔNG** — CR-A-W01-01 vẫn PENDING |
| XL4015 ripple/nhiệt | **KHÔNG** — xem `../logic-power-measurement.md` |
| `pzem-off.csv` canonical của W03 | **MISSING** — CSV trong `raw/` là schema bench, không copy lên root |

## 6. Đọc tiếp

- `provenance-matrix.md` — claim nào là đo, claim nào là lời khai.
- `test-131-profile-readback.md`, `test-133b-reset-default-off.md`, `shunt-continuity.md`.
- `../acceptance.md` — nguồn trạng thái duy nhất.
- `../team-dependencies.md` — đầu vào còn thiếu (phép đo, dữ liệu gốc, cấu hình).
