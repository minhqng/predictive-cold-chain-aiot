# W02 MC-38 bench report — dữ liệu thô thật (Member A)

**Test mapping:** `SEN-H1-05` (`docs/03 §15`) · **Issue:** `A-W02-07` (`docs/05A §11`)
**Bench nguồn:** sketch Arduino standalone trên ESP32-S3 (GPIO34, `DEBOUNCE_MS=40`) — **KHÔNG** phải firmware ESP-IDF W02. Nguồn sketch: `NOT_IN_REPO`.

## 1. Bằng chứng đã nhập (giữ nguyên byte)

| File | Bytes | SHA-256 |
|---|---:|---|
| `mc38-bench-original.txt` | 2 401 | `38cdeef5f9bd6fb1e13b7183d0903ad48035dc15fdbc0a9c57e7c0b5c9fb4595` |
| `mc38-bench.csv` | 1 994 | `27690ac7a05d21dcc673dfa188e256ba5cb8e3c9e74d0d53e328f20929279619` |

Log gốc giữ nguyên dạng Serial Monitor (CRLF); CSV là bản **dẫn xuất** từ log, LF. Thư mục này có `.gitattributes` (`* -text !eol`) để git không chuẩn hoá line-ending — hai hash trên đúng cả khi clone lại.

## 2. Cấu hình bench ghi sẵn trong log

```text
# COLDGUARD W02 MC38 TEST
# DEBOUNCE_MS=40
# GPIO=34
ms,type,raw,stable,raw_edges,stable_edges
1010,START,1,1,0,0
```

- MCU: ESP32-S3; chân MC-38: **GPIO34**; thời gian chống dội sketch bench: **40 ms**.
- Trạng thái khởi tạo (dòng `START`): `raw=1 stable=1` — nhất quán với dòng `MC38 initial: HIGH` trong ảnh `w02_rom_enumeration_4_devices.png`.
- Khác biệt cần khai báo: firmware ESP-IDF W02 dùng `CG_DOOR_DEBOUNCE_MS=50` và đếm cạnh thô theo µs; bài bench này dùng **40 ms theo sketch**. Giá trị 40 ms là cấu hình của **phiên bench**, không phải của firmware trong repo.

## 3. Xác minh từ log gốc (tính lại độc lập, không dùng lại con số phiên trước)

| Kiểm tra | Kết quả |
|---|---|
| Sự kiện `RAW` | **48** |
| Sự kiện `STABLE` | **48** |
| Cặp RAW/STABLE tương ứng (mỗi `RAW` kèm 1 `STABLE` đúng +40 ms, cùng mức `raw`) | **48/48 — không cặp thiếu, không cặp lệch** |
| Thời gian debounce đo được | **40 ms cho cả 48 cặp** (tập giá trị {40}) |
| `raw_edges` luỹ tiến 1..48, không nhảy/bỏ/thiếu | **YES** |
| `stable_edges` luỹ tiến 1..48, không nhảy/bỏ/thiếu | **YES** |
| Mỗi `STABLE` tăng đúng 1 `stable_edges` so với `RAW` cùng cặp (không gộp/dội) | **YES** |
| Chuyển trạng thái xen kẽ đều `HIGH→LOW`/`LOW→HIGH`, không có chuyển trùng hướng | **YES** (`HIGH→LOW` ở cạnh lẻ, `LOW→HIGH` ở cạnh chẵn) |
| Bộ đếm cuối phiên | `raw_edges=48`, `stable_edges=48` |
| Tổng thời lượng (từ `START` 1010 ms đến `STABLE` cuối 509 010 ms) | 508 000 ms (~8,5 phút) |
| Khoảng cách giữa hai sự kiện `RAW` liên tiếp | min 476 ms · max 75 620 ms · mean ≈ 3 034 ms |

## 4. Polarity — quan sát vật lý có dấu trong log

Log có **hai dòng chú thích vật lý do người vận hành ghi tại thời điểm test**:

```text
# PHYSICAL=NEAR raw=0 stable=0
# PHYSICAL=FAR  raw=1 stable=1
```

Nghĩa là: đưa nam châm **lại gần** MC-38 ⇒ mức thô `0` (mức ổn định `0`); **kéo ra xa** ⇒ mức thô `1` (mức ổn định `1`). Tất cả 48 cặp đều nhất quán với ánh xạ này (mỗi `STABLE` của cạnh `HIGH→LOW` có `stable=0`, mỗi cạnh `LOW→HIGH` có `stable=1` — kiểm tra tự động: khớp 48/48).

Ánh xạ ghi nhận của phiên bench: **NEAR = LOW = CLOSED** · **FAR = HIGH = OPEN**.

**Giới hạn tường minh:** đây là polarity của **phiên bench sketch Arduino** (T1 vị trí "gần cửa" trong ảnh enumeration thuộc bài đo riêng). Firmware W02 trong repo giữ nguyên `CG_DOOR_POLARITY_CONFIRMED=0` — hồ sơ này **không** sửa firmware và **không** đóng cờ trong firmware; ánh xạ trên là dữ liệu để review/freez sau khi firmware ESP-IDF chạy thật.

## 5. Chu kỳ

- **24 cặp chu kỳ hoàn chỉnh NEAR→FAR** (`LOW→HIGH` 24 lần sau `HIGH→LOW` 24 lần) — đạt tiêu chí `>=20 open/close cycles`.
- Các khoảng cách chờ dài (75,6 s / ~17 s) đúng là hai đoạn có dòng chú thích `PHYSICAL` — dấu hiệu các biên được tạo do thao tác vật lý có chủ đích, không phải dội ngẫu nhiên.
- Khoảng cách ngắn nhất giữa hai cạnh thô liên tiếp là **476 ms** — lớn hơn nhiều so với cửa sổ debounce 40 ms ⇒ không phát hiện dội tiếp điểm nào bị **gộp sai** trong 48 cạnh này.

## 6. Đời bằng chứng so với ảnh cũ

| Nguồn | Nội dung | Còn lại |
|---|---|---|
| Ảnh `w02_mc38_24_cycles.png` (phiên cũ, timestamp OFF) | Bộ đếm luỹ tiến 21→24, không có thời gian sự kiện | Chỉ còn vai trò truy vết phiên cũ; **không** phải nguồn bằng chứng debounce/polarity |
| `mc38/` (phiên này) | Log thô **48 cặp RAW/STABLE** có mốc ms cố định từ boot, chú thích vật lý, CSV dẫn xuất | Bằng chứng chính của `A-W02-07` ở mức bench |

Hai nguồn là **hai phiên khác nhau**; bộ đếm 48 trong log thô không trừ suy ra bộ đếm 21→24 trên ảnh.

## 7. Điều bằng chứng này KHÔNG chứng minh

- Hành vi chạy bằng **firmware ESP-IDF W02**: chưa nạp/chạy ⇒ mức nghiệm thu của `A-W02-07` là **`BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`**.
- `door-test.csv` đúng schema của công cụ `cg_build_door_csv.py` (bắt buộc `--open-level`): chưa dựng, do chưa có capture từ firmware W02 có dòng `#CG DOOR_EDGE`/`#CG DOOR_STATE`.
- Hoạt động trong cụm lắp cuối (H0 vẫn `DEFERRED`), ví dụ rung/EMI thời gian dài.
- Hiệu chuẩn hoặc ngưỡng chất lượng chuyển đổi — đây là bằng chứng chức năng tiếp điểm.
