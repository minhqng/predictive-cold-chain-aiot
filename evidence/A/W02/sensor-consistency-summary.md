# W02 sensor consistency summary — Member A

**Test mapping:** `SEN-H1-03` (`docs/03 §15`) · **Issue:** `A-W02-05` (`docs/05A §11`)
**Nguồn:** `w02_ds18b20_600_samples_summary.png` (ảnh gốc do người dùng cung cấp) · **Ngày session:** 2026-10-18 (ngày nhận ảnh; sketch tự báo `# W02 TEST FINISHED`)

> **Cập nhật (2026-10-18) — dữ liệu thô 620 mẫu đã được nhập tại `ds18b20/`.** Một phiên bench **mới** (sketch Arduino standalone, COM4 @ 115200): 620 mẫu liên tục 1–620, `uptime_ms` 42 014 → 661 014 (tổng **619 000 ms**, 619 khoảng × 1000 ms), 4 vai trò **620/620 hợp lệ**, 0 trùng/0 thiếu/0 sentinel; thống kê tính lại từ log gốc: T1 29.878528 °C (sd 0.021467), T2 30.187903 (0.016275), T3 29.568347 (0.023374), SPARE 29.921774 (0.028058); chênh lệch trung bình cặp lớn nhất **0.6196 °C (T2–T3)**; CSV khớp log từng dòng (chi tiết + SHA-256: `ds18b20/ds18b20-verification.md`). **Giới hạn ROM:** raw log **0 dòng ROM** — cảnh báo `ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG` được giữ nguyên (không chèn dòng ROM, không tắt cảnh báo); ROM được xác nhận bằng **bằng chứng độc lập phiên khác** (`w02_rom_enumeration_4_devices.png`, 4 PRESENT=1) và phần ROM **cùng một boot** sẽ được xác minh trong bài 5 reboot firmware ESP-IDF (`A-W02-03`). Phần dưới đây mô tả **phiên 600 mẫu cũ vẫn ở mức `RAW_EVIDENCE_PENDING`** (thiếu dữ liệu thô của chính phiên ấy) — hai phiên **không** hợp nhất thống kê.

## 1. Kết quả được hiển thị (số liệu nguyên văn từ ảnh)

Bảng `# W02 SUMMARY` trong ảnh kết thúc bài test:

| Kênh bench | Vai trò bench | valid | mean (°C) | sd (°C) | min (°C) | max (°C) | range max−min (°C) |
|---|---|---:|---:|---:|---:|---:|---:|
| S1 | DS1 | 600/600 | 29.882 | 0.028 | 29.81 | 29.94 | 0.13 |
| S2 | DS2 | 600/600 | 30.214 | 0.031 | 30.19 | 30.25 | 0.06 |
| S3 | DS3 | 600/600 | 29.611 | 0.026 | 29.56 | 29.62 | 0.06 |
| S4 | DS4 | 600/600 | 29.935 | 0.018 | 29.88 | 30.00 | 0.12 |

- **Tổng mẫu hợp lệ: 600/600 cho cả 4 đầu dò** (2 400 giá trị hợp lệ, 0 giá trị bị đánh dấu không hợp lệ trong cửa sổ hiển thị).
- Ảnh còn hiển thị 9 dòng CSV cuối (mẫu `592`–`600`) với dạng:
  `index,giây,DS1,DS2,DS3,DS4,valid,<cột cuối>`, ví dụ `600,600,29.88,30.25,29.62,29.94,4,1`.

## 2. Đại lượng dẫn xuất (tính từ bảng trên, không phải từ dữ liệu thô)

Chênh lệch **trung bình từng cặp** (mean khác biệt, đơn vị °C):

| Cặp | Δ mean (°C) | \|Δ mean\| |
|---|---:|---:|
| DS1 − DS2 | −0.332 | 0.332 |
| DS1 − DS3 | +0.271 | 0.271 |
| DS1 − DS4 | −0.053 | 0.053 |
| DS2 − DS3 | **+0.603** | **0.603** |
| DS2 − DS4 | +0.279 | 0.279 |
| DS3 − DS4 | −0.324 | 0.324 |

- **Chênh lệch trung bình cặp lớn nhất (maximum disagreement of means): 0.603 °C — DS2 vs DS3.**
- Dải giữa các mean: 29.611 °C (S3) → 30.214 °C (S2), tức 0.603 °C.
- Dải toàn bộ giá trị đã thấy: 29.56 °C → 30.25 °C (0.69 °C).

## 3. Độ ổn định ngắn hạn

- SD từng đầu dò: **0.018 – 0.031 °C**. Toàn bộ 4 giá trị SD **nhỏ hơn một bước lượng tử 12-bit của DS18B20 (0.0625 °C)**.
- Vì mỗi SD nhỏ hơn 1 LSB, các biến động mức này **không nên được diễn giải thành cấu trúc vật lý**; nó tương thích với một điều kiện nhiệt ổn định, sai số hoá của ADC 12-bit và làm tròn hiển thị (2 chữ số thập phân).
- Kết luận hợp lệ ở đây là **tính ổn định ngắn hạn và tính lặp của chuỗi đọc (600/600 hợp lệ)**, không phải độ chính xác tuyệt đối.

## 4. Cách diễn giải 0.603 °C — ĐỌC KỸ

- `docs/05A §11` yêu cầu đặt các đầu dò "under as similar a stable condition as practical". Điều kiện bench thực tế **không được ghi lại** trong ảnh (không có ảnh setup, không có mô tả vị trí đặt 4 đầu dò).
- Vì vậy 0.603 °C **không thể** được quy cho sai số cảm biến và cũng **không thể** loại trừ gradient/khác biệt vị trí đặt thật.
- **Không có ngưỡng số nào** cho inter-sensor consistency trong `docs/01`, `docs/03` hay `docs/05A`. Bộ chứng cứ này **không tự đặt ngưỡng** và **không** kết luận PASS/FAIL theo ngưỡng bịa.
- `docs/03 §15` `SEN-H1-03` quy định rõ: nếu không có chuẩn truy vết (traceable reference) thì kết quả phải được gọi là **consistency check**, **không** phải calibration đã chứng nhận. Bộ chứng cứ này tuân thủ đúng quy định đó: **KHÔNG PHẢI CALIBRATION**.

## 5. Quan sát ngoài bài test 600 mẫu (ghi để truy vết, không dùng để tính thống kê)

Trong ảnh `w02_rom_enumeration_4_devices.png` (một lần chạy khác), `DS3` được in là `29.56 C` ở hầu hết khối nhưng có **một khối in `29.50 C`**. Giá trị này:

- **không** thuộc cửa sổ 600 mẫu (min S3 trong summary là 29.56 °C),
- được ghi lại như một quan sát của phiên bench, **không** đủ để kết luận drift hay lỗi đọc.

## 6. Giới hạn — điều bộ chứng cứ này KHÔNG chứng minh

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| Chứng minh nhịp lấy mẫu ~1 Hz | **KHÔNG chứng minh** | Serial Monitor để `Show timestamp = OFF`; không có timestamp tuyệt đối. 600 mẫu ≈ 10 phút ở 1 Hz là **suy luận** từ cột đếm, không phải chứng minh từ đồng hồ. |
| Chứng minh đủ ≥10 phút | **KHÔNG chứng minh** | `docs/05A §11` yêu cầu `>=10 min`. 600 mẫu khớp ~10 phút *nếu* nhịp đúng 1 Hz — chính xác bằng 10 phút, nên không có biên an toàn; cần xác nhận bằng dữ liệu thô. |
| Dữ liệu thô 600 dòng | **KHÔNG có** | Ảnh chỉ hiển thị 9 dòng cuối. Không có `sensor-consistency.csv` → không thể tính lại mean/SD độc lập. |
| Thứ tự cột thứ 2 | **CHƯA xác minh** | Cột 2 trùng giá trị với cột 1 (`592,592`). Có thể là giây trôi qua, nhưng **chưa được chú thích** trong ảnh. |
| Ý nghĩa cột cuối (`…,4,1`) | **CHƯA xác minh** | Hằng số `1` trong các dòng hiển thị. Không có chú thích; **không** được dùng như `door_state` hay bất kỳ ngữ nghĩa nào cho tới khi có nguồn xác nhận. |
| Tính nhất quán dài hạn / drift | **KHÔNG đo** | Chỉ có một cửa sổ ~10 phút trong một phiên. |
| Nguồn firmware đã chạy | **KHÔNG có trong repo** | Sketch bench W02 in ra summary không nằm trong `firmware/` (`NOT_IN_REPO`). Repo nay có firmware W02 chính thức (`firmware/main/`, 7 module C; commit firmware nay `2a5a0da…`, đã build thật trên CI) nhưng bản đó **không** phải nguồn của summary/3 ảnh này. |
| Ảnh setup bench | **KHÔNG có** | Không có ảnh hay ghi chú mô tả vị trí đặt 4 đầu dò trong lần đo này. |

## 7. Điều kiện để đóng `A-W02-05`

- [x] Lưu dữ liệu thô ≥10 phút × 4 kênh — **đã có ở mức bench**: `ds18b20/sensor-consistency.csv` (620 dòng × 4 kênh) + log nguồn, thống kê tính lại 100% khớp; **lưu ý:** đây là phiên sketch Arduino, CSV **không** dựng bằng `cg_build_sensor_csv.py` (schema `#CG SAMPLE` của firmware); phiên chạy bằng firmware ESP-IDF vẫn `PENDING`.
- [ ] Ghi lại điều kiện đặt đầu dò (ảnh setup hoặc mô tả + ngày) cho từng phiên.
- [ ] Ghi `hardware_config_id` và `firmware_commit` đã dùng — `firmware_commit` đã ghi (không phải nguồn của phiên bench); `hardware_config_id` vẫn `NOT_ASSIGNED`.
- [ ] Leader xác nhận không cần chuẩn truy vết cho W02 (consistency check là đủ).
- [ ] Xác minh ROM discovery **cùng một boot** với dữ liệu — sẽ được thực hiện trong bài 5 reboot firmware ESP-IDF (`A-W02-03`).

**Trạng thái hiện tại của `A-W02-05`: `BENCH DATA VERIFIED — 620 RAW SAMPLES CAPTURED` (phiên 620 mẫu, sketch Arduino, giới hạn ROM ghi tường minh) · phiên 600 mẫu cũ vẫn `RAW_EVIDENCE_PENDING`.**
