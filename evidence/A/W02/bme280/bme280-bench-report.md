# ColdGuard — A-W02-06: BME280 bench test evidence

## Nguồn dữ liệu và phương pháp

- Nguồn: log Serial Monitor thực tế do Member A ghi trên ESP32-S3, sketch thử nghiệm Arduino/Adafruit BME280 (không phải firmware ESP-IDF W02 tích hợp).
- Tên file nhận ban đầu: `bme280-bench.txt.txt`.
- SHA-256 file gốc: `da24b6f0d487a4d677892e19c1299d18b207f5ad4f01d1b4635a475d8e606c23`.
- Bus: I²C, SDA=GPIO21, SCL=GPIO33; địa chỉ phát hiện `0x76`.
- Chip ID `0x60` (`BME280`), khởi tạo `BME280_INIT=PASS`.
- Không có thời gian thực (wall-clock) trong log: `uptime_ms` là thời gian tính từ lúc ESP32 khởi động.

## Phân tích tự động từ log gốc

- Số mẫu: **403**, đánh số liên tục 1–403.
- Valid: **403/403 (100%)**; không có dòng `valid=0` hoặc thiếu trường.
- Thời điểm mẫu đầu: **2816 ms**; cuối **404816 ms**.
- Khoảng thời gian giữa hai mẫu đầu/cuối: **402 giây = 6 phút 42 giây**.
- Khoảng lấy mẫu: **1000 ms cho toàn bộ 402 khoảng**, không có mẫu mất hoặc trùng trong log.

| Thông số | Min | Max | Trung bình | Độ lệch chuẩn mẫu | Giá trị đầu | Giá trị cuối |
|---|---:|---:|---:|---:|---:|---:|
| Nhiệt độ (°C) | 30.27 | 30.42 | 30.408 | 0.017 | 30.27 | 30.42 |
| Độ ẩm tương đối (% RH) | 68.42 | 69.14 | 68.513 | 0.089 | 69.14 | 68.48 |
| Áp suất (hPa) | 1011.97 | 1012.16 | 1012.072 | 0.037 | 1012.04 | 1012.12 |

## Kết luận có thể xác minh

**BME280 standalone bench test: PASS** về nhận diện chip, I²C, đọc T/RH/áp suất và tính liên tục của 403 mẫu. Log không cho thấy lỗi đọc hoặc mất mẫu.

**Giới hạn:** Không chứng minh độ chính xác tuyệt đối/hiệu chuẩn; không chứng minh firmware ESP-IDF W02 đã tích hợp và chạy BME280, không chứng minh khả năng hoạt động trong buồng lạnh hoặc vị trí lắp cuối cùng. BME280 thử riêng bằng sketch Arduino có thể ghi đè firmware ESP-IDF trong MCU; nạp lại firmware chính thức trước các bài thử W02 tích hợp. Chưa có bản ghi ngày giờ hay ảnh đấu dây đính kèm trong gói log; có thể bổ sung nếu cần.

**Trạng thái đề xuất cho A-W02-06:** `BENCH_VERIFIED_FROM_REAL_SERIAL_LOG — INTEGRATION/ACCEPTANCE REVIEW PENDING`. Không dùng kết quả này để tự động đánh dấu toàn bộ W02 là PASS hoặc tự merge PR #8.
