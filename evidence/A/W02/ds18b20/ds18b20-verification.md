# W02 DS18B20 bench report — dữ liệu thô 620 mẫu (Member A)

**Test mapping:** `SEN-H1-03` (`docs/03 §15`) · **Issue:** `A-W02-05` (`docs/05A §11`)
**Bench nguồn:** sketch Arduino/OneWire/DallasTemperature standalone trên ESP32-S3 (COM4 @ 115200) — **KHÔNG** phải firmware ESP-IDF W02. Nguồn sketch: `NOT_IN_REPO`.

## 1. Bằng chứng đã nhập (giữ nguyên byte, nguồn: `W02_DS18B20_20261018_194041.zip` từ phía người dùng)

| File | Bytes | SHA-256 |
|---|---:|---|
| `ds18b20-serial-original.txt` | 32 190 | `44228795d48f223b1fdde619c184eccd1c34a56f4dd3d19fdfa12f239289b91c` |
| `sensor-consistency.csv` | 31 533 | `99bdc21cfe1ecbf565b2602a16d7c60871e0efe67f4a2ddb885715b446fefe21` |
| `sensor-consistency-report.md` | 1 323 | `2d53af0983dc5e3035f2ec2e30afdabcf1dce4b0867bdb37b94e9d1cb3b428d7` |

Tệp được sao chép **nguyên byte** từ ZIP (SHA-256 khớp lại sau khi copy); blob được ghim bằng `ds18b20/.gitattributes` (`* -text !eol`) — hash đúng cả khi clone. Báo cáo đi kèm của công cụ capture khai báo: capture bắt đầu 2026-10-18T12:40:41 UTC trên COM4 @ 115200.

## 2. Xác minh độc lập từ log gốc (tính lại toàn bộ, không dùng lại số của phiên trước)

| Kiểm tra | Kết quả |
|---|---|
| Cấu trúc log | 1 × `# W02 START`, 1 × `# W02 DONE samples=620`, 1 dòng header CSV, 620 dòng dữ liệu hợp lệ (0 lỗi parse) |
| Số mẫu | **620**, chỉ số liên tục **1–620**, **0 trùng, 0 thiếu** |
| `uptime_ms` | đầu **42 014** → cuối **661 014** ⇒ **619 000 ms**, tính tăng dần đơn điệu |
| Khoảng cách giữa mẫu | **619/619 khoảng đều đúng 1 000 ms** (min=max=1000 ms) |
| Tổng thời lượng | **619 000 ms** — đạt yêu cầu `≥10 phút` của `docs/05A §11` (với biên 1 s) |
| Valid theo vai trò | T1 **620/620** · T2 **620/620** · T3 **620/620** · SPARE **620/620** — tổng 2 480/2 480 cờ `valid=1`, không có dòng `valid=0` |
| Giá trị bất thường | **0** — không có sentinel 85.0 °C (power-on), không có −127, không có giá trị ngoài dải [−55, 125] °C |
| CSV ↔ log | CSV 620 dòng **khớp từng dòng** với 620 dòng mẫu của log (0 sai lệch) |

## 3. Thống kê tính lại từ log gốc (SD mẫu)

| Vai trò | N | Mean (°C) | SD mẫu (°C) | Min (°C) | Max (°C) |
|---|---:|---:|---:|---:|---:|
| T1 | 620/620 | 29.878528 | 0.021467 | 29.8125 | 29.9375 |
| T2 | 620/620 | 30.187903 | 0.016275 | 30.1250 | 30.2500 |
| T3 | 620/620 | 29.568347 | 0.023374 | 29.5000 | 29.6250 |
| SPARE | 620/620 | 29.921774 | 0.028058 | 29.8125 | 29.9375 |

Chênh lệch mean từng cặp (T1/T2/T3): `T1−T2 = −0.309375 °C`, `T1−T3 = +0.310181 °C`, `T2−T3 = +0.619556 °C`; **chênh lệch trung bình cặp lớn nhất 0.6196 °C (T2–T3)**; chênh lệch tức thời (max−min) lớn nhất trong một mẫu: **0.6875 °C**.

Kết luận về mức độ quy chiếu: SD mọi đầu dò (0.016–0.028 °C) nhỏ hơn một bước lượng tử 12-bit (0.0625 °C) — tương tự bài 600 mẫu, đây là **consistency check**; `docs/03 §15` quy định không có chuẩn truy vết ⇒ **KHÔNG PHẢI calibration**.

## 4. Cảnh báo provenance ROM (phải đọc khi review)

- Công cụ capture của phiên này tự báo **`NOT PASS: ROM_DISCOVERY_NOT_FULLY_CONFIRMED_IN_LOG`** — và xác minh độc lập cho thấy **raw log chứa 0 dòng ROM** (`# ROLE=… ROM=… PRESENT=…`, `# DISCOVERED_COUNT=…`); log chỉ có `# W02 START` và `# W02 DONE samples=620`.
- Nguyên nhân đã nhận diện (không phải suy đoán từ xa): sketch in danh sách 4 ROM **khi khởi động**, nhưng capture Python gọi `port.reset_input_buffer()` khi mở cổng ⇒ các dòng enumeration có thể bị vứt bỏ ngoài capture. Ảnh cửa sổ Serial Monitor của **một phiên khác** (`w02_rom_enumeration_4_devices.png`) hiển thị **T1 = 287088CA00000051 / T2 = 28AEBF2200000006 / T3 = 28CBE9CA00000072 / SPARE = 283BE5C9000000A9, cả 4 `PRESENT=1`** — đây là **bằng chứng độc lập, phiên khác**, không phải của capture 620 mẫu.
- Hành xử đúng: **không chèn dòng ROM đầu log**, không sửa log gốc, không tắt cảnh báo. Bốn ROM này và CRC8 đã được đóng băng vào `firmware/main/coldguard_config.h` và đối chiếu tự động với `sensor-rom-map.yaml` (`cg_check_firmware.py` — PASS). Phần **ROM discovery cùng một boot với capture** sẽ được xác nhận trong bài **5 reboot trên firmware ESP-IDF chính thức** (`A-W02-03`) — log `#CG ROM` của firmware sẽ in đủ 4 ROM ngay đầu mỗi boot; nếu khi đó ROM lệch khỏi 4 giá trị này, hồ sơ sẽ rơi về lại "chưa xác minh".
- Không yêu cầu đo lại 10 phút: dữ liệu 620 mẫu là đủ cho yêu cầu thời lượng; chỉ phần ROM cùng-capture được dời sang bài 5 reboot.

Trạng thái ROM của `A-W02-05`: **`ROM IDENTITY VERIFIED BY SEPARATE EVIDENCE — SAME-CAPTURE CONFIRMATION PENDING (5-reboot run)`**.

## 5. Điều bằng chứng này KHÔNG chứng minh

- Hành vi chạy bằng **firmware ESP-IDF W02** — capture dùng sketch Arduino standalone; dòng dữ liệu `sample,uptime_ms,…` **không** đúng schema `#CG SAMPLE` của firmware W02, **không** để dựng `sensor-consistency.csv` bằng `cg_build_sensor_csv.py`. `A-W02-04` (nhịp ~1 Hz do firmware đo được) vẫn `HARDWARE RUN PENDING`.
- Vị trí vật lý/điều kiện đặt đầu dò của phiên 620 mẫu (không có ảnh setup trong ZIP); lệch nhiệt không quy cho sai số cảm biến, không loại trừ gradient vị trí.
- Độ chính xác/hiệu chuẩn (không có chuẩn truy vết). Không có wall-clock — chỉ `uptime_ms` kể từ lúc boot sketch (mẫu 1 bắt đầu ở uptime 42 014 ms).
- So sánh trực tiếp với bài 600 mẫu cũ: **hai phiên khác nhau** (mean S1–S4 phiên cũ: 29.882/30.214/29.611/29.935); số liệu không hợp nhất thống kê.
