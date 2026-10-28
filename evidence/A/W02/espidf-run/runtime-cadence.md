# Runtime firmware verification — `#CG SAMPLE` cadence ~1 Hz (A-W02-04)

Ngày: 2026-10-18, firmware ESP-IDF W02 thật (commit `1b93f572`, artifact run
`39134178842`) trên ESP32-S3 MAC `e0:72:a1:bc:cf:4c`, COM4 @ 115200.

Input: cùng raw log `serial-reboot-original.log` của lần thu 5 reboot (không thu riêng
— phiên runtime là segment `runtime` 200 s không reset, sau cùng 6 boot block).

## 1. Tổng quan mẫu thu được

| Mục | Giá trị |
|---|---|
| Dòng `#CG SAMPLE` | **252** |
| Khoảng cách giữa hai mẫu liên tiếp (`uptime_ms` delta) | **246** |
| min / max | **990 / 1000 ms** |
| mean / median | **999.756 / 1000.0 ms** |
| Đúng bằng 1000 ms | 240/246 (97.6%) |
| Trong [900, 1100] ms | **246/246 (100%)** |
| `thermal` quality | **VALID 252/252** (không có lần chuyển quality nào khác) |
| `t1/t2/t3` cờ valid | 252/252 đều `1` |
| SPARE | giá trị luôn có (grammar v1: có số tức được coi là valid) |
| `nan` / sentinel (85 °C, −127) | **0** |

⇒ **Nhịp lấy mẫu ~1 Hz đo được thật** (deadline pacing của firmware: nếu lệch sẻ tăng
`uptime_ms`, không tạo mẫu giả — xem comment deadline pacing ở `app_main.c` (docs/01
§6.7): mọi interval đo được đều ≤ 1000 ms, mean 999.756 ms.
246/246 interval ≤ 1000 ms).

## 2. Giá trị nhiệt trong phiên (4 vai trò, firmware → BUS một nhịp shared-conversion)

Mỗi `#CG SAMPLE` chứa cùng lúc 4 giá trị T1/T2/T3/SPARE (thể hiện broadcast
`SKIP_ROM`+`CONVERT_T` — một khối dùng chung hoặc đọc tuần tự theo ROM cố định):

| Vai trò | mean (°C) | min–max (°C) | giá trị phân biệt | mẫu hợp lệ |
|---|---|---|---|---|
| T1 (`287088CA00000051`) | 30.0687 | 29.9375–30.125 | 29.9375, 30.0000, 30.0625, 30.1250 | 252/252 |
| T2 (`28AEBF2200000006`) | 30.3795 | 30.3750–30.4375 | 30.3750, 30.4375 | 252/252 |
| T3 (`28CBE9CA00000072`) | 29.7654 | 29.6250–29.8125 | 29.6250, 29.7500, 29.8125 | 252/252 |
| SPARE (`283BE5C9000000A9`) | 30.1210 | 30.0000–30.125 | 30.0000, 30.0625, 30.1250 | 252/252 |

*(mean/min/max/độ phân biệt đều tính lại từ raw log; độ phân giải DS18B20 12-bit =
0.0625 °C/LSB; mỗi kênh dao động trong khoảng 1–3 LSB trong toàn phiên — cùng cỡ nhiễu
với phiên bench 620 mẫu.)*

Khoảng lệch giữa các vai trò trong phiên runtime ~0.61 °C (giữa T2 và T3) — cùng cỡ với
khoảng lệch của bench 620 mẫu sketch (+0.619556 °C, `ds18b20/ds18b20-verification.md`),
không có gì bất thường khi cả 4 đầu dò com chung một môi trường bench.

## 3. Trạng thái cửa trong phiên runtime

* `door_raw=1` **cố định 252/252** (cửa không bị thao tác), `door=UNVERIFIED` — đúng
  `CG_DOOR_POLARITY_CONFIRMED=0` trong `coldguard_config.h` của commit này.
* Chưa có dòng `#CG DOOR_EDGE` nào trong phiên **(cửa không di chuyển)** — KHÔNG tuyên bố
  MC-38 integration; B3 firmware vẫn `PENDING`, cờ polarity vẫn `0`.

## 4. Lỗi / giới hạn

* Không có dòng `#CG ERR` trong phiên runtime (0 parse error, 0 transfer error, 0
  `probe_state` cảnh báo; dòng này chỉ in khi status đổi).
* Phiên runtime ngắn (~200 s + các boot window, tổng ~4 phút) — **không** thay yêu cầu
  ≥10 phút của A-W02-05 vì mục đó đã được giải bằng 620 mẫu sketch (619 s ≈ 10.3 phút);
  đồng thời `cg_build_sensor_csv.py` với <600 mẫu trả `WINDOW NOT USABLE` — đúng thiết
  kế: log này chỉ để chứng minh cadence + runtime ổn định, không phải consistency window.
* Raw log không bị sửa; các khoảng lặng là do thiết bị/ngủ tick — giữ nguyên byte.

## 5. Phân bố sample theo boot

Mỗi khối boot đều tự chạy sampling thật (đếm lại từ raw log bằng script):

| boot | boot_id | số dòng `#CG SAMPLE` |
|---|---|---|
| 5 | 227e6f67 | 2 |
| 6 | 50313e8c | 10 |
| 7 | c864acea | 10 |
| 8 | 222be57b | 10 |
| 9 | 99b3dcb5 | 10 |
| 10 | ae20928d | 210 |
| **tổng** | | **252** |

Mỗi reboot đều cho thấy sampling **tự chạy lại từ đầu** (`seq=1…` tăng dần trong khối) —
không có sample nào in 2 lần, không có khối nào bị dựng.
