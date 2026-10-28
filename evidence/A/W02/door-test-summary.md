# W02 door (MC-38) summary — Member A

**Test mapping:** `SEN-H1-05` (`docs/03 §15`) · **Issue:** `A-W02-07` (`docs/05A §11`)
**Nguồn:** `w02_mc38_24_cycles.png` (log chuyển mức) và `w02_rom_enumeration_4_devices.png` (trạng thái khởi tạo) — ảnh gốc do người dùng cung cấp.

> **Cập nhật (2026-10-18) — dữ liệu thô MC-38 đã có tại `mc38/`.** Log bench thật 48 cặp `RAW/STABLE` (GPIO34, debounce 40 ms, tổng 508 s, có dòng chú thích vật lý `# PHYSICAL=NEAR raw=0 stable=0` / `# PHYSICAL=FAR raw=1 stable=1`) + CSV dẫn xuất đã được nhập nguyên byte vào `mc38/` và xác minh máy móc 48/48 cặp, 24 chu kỳ, ánh xạ **NEAR = LOW = CLOSED / FAR = HIGH = OPEN** (chi tiết và SHA-256: `mc38/mc38-bench-report.md`). Ảnh bên dưới giờ **chỉ còn vai trò truy vết phiên cũ**; phần debounce + polarity hiện được chứng minh bởi dữ liệu thô ở mức **bench**, còn việc firmware **ESP-IDF** chạy thật với `CG_DOOR_DEBOUNCE_MS=50` + `--open-level` của công cụ vẫn `PENDING`. Trạng thái: **`BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED`**.


## 1. Nguyên văn dòng log trong ảnh

Ảnh `w02_mc38_24_cycles.png` (COM4, 115200 baud, `Show timestamp = OFF`):

```text
MC38: LOW  | transitions: 43 | cycles: 21
MC38: HIGH | transitions: 44 | cycles: 22
--- TEMPERATURE ---
DS1: 29.81 C
DS2: 30.19 C
DS3: 29.56 C
DS4: 29.88 C
Valid: 4/4
--------------------------
MC38: LOW  | transitions: 45 | cycles: 22
MC38: HIGH | transitions: 46 | cycles: 23
MC38: LOW  | transitions: 47 | cycles: 23
MC38: HIGH | transitions: 48 | cycles: 24
--- TEMPERATURE ---
DS1: 29.81 C
DS2: 30.19 C
```

*Ghi chú về trích dẫn:* giá trị, nhãn và đơn vị `C` được trích nguyên văn. **Chỉ khoảng trắng giữa các trường được chuẩn hoá** cho dễ đọc; không có ký tự nào khác bị sửa. Khối `TEMPERATURE` cuối ảnh bị cắt trong ảnh gốc (dừng ở `DS2`), nên chỉ có `DS1`/`DS2` được trích.

Ảnh `w02_rom_enumeration_4_devices.png` (cùng phiên bench):

```text
MC38 initial: HIGH
```

## 2. Đọc số liệu (chỉ những gì nhìn thấy được)

| Đại lượng | Giá trị quan sát trong ảnh |
|---|---|
| `transitions` (tổng số lần đổi mức, bộ đếm luỹ tiến) | 43 → 48 trong cửa sổ hiển thị |
| `cycles` (bộ đếm thứ hai) | 21 → 24 trong cửa sổ hiển thị |
| Chu kỳ hoàn tất tối thiểu đã đạt | **24** |
| Trạng thái khởi tạo lúc boot | `HIGH` |

**Quan hệ bộ đếm (kiểm tra số học):** `cycles = floor(transitions / 2)` khớp toàn bộ cặp số đã thấy — (43→21), (44→22), (45→22), (46→23), (47→23), (48→24). Nghĩa là `transitions` đếm **mọi** lần đổi mức, còn `cycles` đếm **cặp đổi mức đã hoàn tất**. Với 48 transitions ⇒ 24 cycles, tức **24 cặp chuyển mức theo bộ đếm của firmware** (≈ 24 lần mở/đóng *nếu* giả định không có dội và mỗi lần đổi mức tương ứng đúng một hành động cơ học — giả định này **chưa** được chứng minh, xem §3).

## 3. Đối chiếu tiêu chí canonical

| Yêu cầu (`docs/05A §11` A-W02-07 / `docs/03 §15` SEN-H1-05) | Trạng thái | Căn cứ / phần thiếu |
|---|---|---|
| `>=20 open/close cycles` | **MET trên số đếm** | `cycles: 24` ≥ 20 trong cửa sổ hiển thị. Đây là *số đếm do firmware tự báo*, không phải log sự kiện có timestamp. |
| `semantic OPEN/CLOSED khớp trạng thái vật lý` | **CHƯA CHỨNG MINH — `PENDING_POLARITY_CONFIRMATION`** | Ảnh chỉ cho thấy **mức thô** `LOW`/`HIGH`. Không có dòng log nào in ra `OPEN`/`CLOSED`. Ánh xạ mức thô → ngữ nghĩa cửa **không** suy ra được từ bằng chứng này. |
| `transition reliable` (debounce) | **CHƯA CHỨNG MINH** | Không có thời gian giữa các lần đổi mức, không có bộ đếm bounce/reject, không có timestamp. Chất lượng chống dội (debounce) **không** được chứng minh bởi ảnh này. |

### Vì sao KHÔNG được tự suy ra polarity

- `MC38 initial: HIGH` khi chưa mở/đóng cửa: tuỳ cách đấu (pull-up nội/ngoài, đầu dò dùng tiếp điểm NO hay NC, vị trí nam châm so với tiếp điểm) mà `HIGH` có thể là **cửa đóng** hoặc **cửa mở**. Cả hai đều hợp lý về kỹ thuật.
- Ảnh không chụp được hành vi vật lý tương ứng (không có ảnh nam châm, không có mốc "vừa mở cửa"), nên không có cột mốc nào để neo `LOW`/`HIGH` vào `OPEN`/`CLOSED`.
- Kết luận đúng: cần người vận hành xác nhận **cấu hình đấu dây + loại tiếp điểm**, hoặc một bài test có dấu (đóng cửa rồi in trạng thái), trước khi freeze `raw input → OPEN/CLOSED`.

### Vì sao KHÔNG được tự suy ra debounce

- Bộ đếm chỉ là `transitions`/`cycles`; không có `bounce_count`, `rejected_transitions` hay thời gian chống dội trong bất kỳ dòng nào.
- Với `Show timestamp = OFF`, không thể kiểm tra khoảng thời gian giữa hai lần đổi mức, nên không thể phát hiện dội ngắn.

## 4. Quan sát kèm theo (để truy vết, không phải kết luận)

- Các dòng MC-38 xuất hiện **xen kẽ** với khối in nhiệt độ, tức sketch bench vừa in trạng thái cửa vừa in snapshot nhiệt. Dạng log này là công cụ bench, **không** phải schema telemetry v0 của Member C (`backend/fixtures/telemetry_v0.json` dùng `door.state = "OPEN"/"CLOSED"`).
- Trong ảnh chỉ có **một** dòng `Valid: 4/4`, đặt sau khối nhiệt độ thứ nhất. Khối nhiệt độ thứ hai bị **cắt** trong ảnh (dừng ở `DS2: 30.19 C`) nên phần còn lại của khối đó — kể cả dòng `Valid` — không hiển thị. Bộ chứng cứ này **không** suy ra rằng chuỗi đọc vẫn hợp lệ cho toàn bộ 24 chu kỳ.

## 5. Giới hạn — điều bộ chứng cứ này KHÔNG chứng minh

| Mục | Trạng thái |
|---|---|
| Ánh xạ `LOW/HIGH` → `OPEN/CLOSED` | **Chưa xác minh** (`PENDING_POLARITY_CONFIRMATION`) |
| Debounce / thời gian dội thực tế | **Chưa đo** |
| Timestamp sự kiện cửa | **Không có** (`Show timestamp = OFF`) |
| `door-test.csv` thô | **Không có** — ảnh chỉ hiển thị 6 dòng log |
| Số chu kỳ tổng của phiên | **Không xác định** — chỉ thấy bộ đếm luỹ tiến 21→24, không thấy điểm bắt đầu và kết thúc phiên |
| Chân GPIO thực tế / cách đấu dây | **Không có trong bằng chứng này** (W01 chỉ ghi *candidate* pin) |
| Nguồn firmware đã chạy | **Không có trong repo** |

## 6. Điều kiện để đóng `A-W02-07`

- [x] Freeze bảng `raw input → OPEN/CLOSED` với cấu hình đấu dây được ghi lại — **đã có ở mức bench**: `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` (`mc38/mc38-bench-report.md §4`). Firmware W02 vẫn giữ `CG_DOOR_POLARITY_CONFIRMED=0` (không tự sửa cờ khi chưa chạy ESP-IDF thật).
- [x] Lưu dữ liệu thô ≥20 chu kỳ — **đã có**: `mc38/mc38-bench.csv` (48 cặp cạnh có mốc ms; không phải `door-test.csv` schema ngưỡng `-c`).
- [x] Ghi lại thời gian chống dội đã chọn và lý do — **đã có**: 40 ms (sketch bench, ghi trong log `# DEBOUNCE_MS=40`); firmware dùng `CG_DOOR_DEBOUNCE_MS=50` — sự khác biệt được khai báo.
- [ ] Chạy firmware ESP-IDF thật + `door-test.csv` dựng bằng `cg_build_door_csv.py --open-level` từ log `#CG DOOR_EDGE`, kèm số cạnh thô/bị bỏ cho từng chu kỳ.

**Trạng thái hiện tại của `A-W02-07`: `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED` — polarity + debounce + ≥20 chu kỳ được chứng minh ở mức bench sketch; firmware ESP-IDF chưa chạy thật.**

## 6. Cập nhật 7 (2026-10-18): firmware ESP-IDF đã nạp thật; polarity + DOOR_EDGE vẫn PENDING

- Firmware `1b93f572` đã flash thật (3/3 region verified) và chạy thật (`espidf-run/`):
  mỗi boot in `#CG DOOR_POLARITY state=UNVERIFIED raw_open_level=0` — đúng ý nghĩa
  `CG_DOOR_POLARITY_CONFIRMED=0` trong `coldguard_config.h` (không sửa firmware; ánh xạ
  polarity `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` vẫn ở mức hồ sơ bench của `mc38/`).
- Trong phiên runtime 252 mẫu: `door_raw=1` bất động suốt phiên (cửa không bị thao tác),
  **0 dòng `#CG DOOR_EDGE`** — không nâng `A-W02-07`; bài cửa firmware (B3) và
  `door-test.csv` vẫn phải chạy riêng, sau đó mới đóng cờ.
