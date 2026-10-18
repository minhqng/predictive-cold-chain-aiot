# W02 bench procedure — các bước cần người thao tác phần cứng

Danh sách này **chỉ** chứa việc không thể làm bằng code/dữ liệu/git. Mọi thứ làm được
bằng máy đã được làm trong `firmware/` và `firmware/tools/` (xem
`firmware-implementation.md`).

Thứ tự đề xuất: **B1 → B2 → B3 → B4 → B5**. Tổng thời gian bench ước tính ~25 phút
(không tính hàn/dán nhãn).

---

## B0. Nạp firmware (build đã xong trên CI)

Firmware W02 **đã được biên dịch thật** trên GitHub Actions (ESP-IDF v6.1, target
`esp32s3`, SUCCESS — run URL, log và SHA-256 ở `build-report-w02.md`). B0 giờ chỉ còn là
**nạp**; giữ nguyên cấu hình mặc định.

Cách 1 — dùng artifact của CI (không cần Docker cục bộ): tải artifact
`a-w02-espidf-build-report` từ run ghi trong `build-report-w02.md`, giải nén thư mục
`artifacts/`, rồi flash bằng esptool (lệnh do chính build in ra):

```bash
python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 2MB --flash-freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 coldguard_firmware.bin
```

Cách 2 — build lại cục bộ nếu máy có Docker (đúng lệnh README gốc; lưu log nếu muốn):

```bash
rm -rf /tmp/coldguard-firmware-build && mkdir -p /tmp/coldguard-firmware-build && cp -r firmware/. /tmp/coldguard-firmware-build/
docker run --rm -v /tmp/coldguard-firmware-build:/project:z -w /project espressif/idf:v6.1 bash -c "idf.py set-target esp32s3 && idf.py build"
```

> Bước này **không** cấp nguồn cho TEC hay bất kỳ tải nào — chỉ nạp firmware và mở serial
> monitor cho các bước sau.

---

## B1. Xác minh danh tính qua ≥5 reboot (`A-W02-03`)

1. Mở Serial Monitor `COM4 @ 115200`.
2. Chạy: `py firmware/tools/cg_capture.py --port COM4 --out evidence/A/W02/serial-w02-reboot.log --seconds 90`
3. Nhấn **RST/EN** trên board **5 lần**, mỗi lần cách nhau ~5–10 giây (đủ để thấy khối
   `#CG BOOT` + 4 dòng `#CG ROM`).
4. Dừng capture (Ctrl+C) — file log vẫn được ghi.
5. Kiểm chứng:
   ```powershell
   py firmware/tools/cg_verify_reboots.py evidence/A/W02/serial-w02-reboot.log --min-boots 5 --json evidence/A/W02/reboot-report.json
   ```
   Kết quả cần: `REBOOT IDENTITY: PASS (5 boots, roles stable, boot metadata consistent)`.
   Công cụ **từ chối PASS** nếu `boot_id` thiếu/trùng hoặc `boot_count` không tăng dần —
   không thể dán lặp một khối boot để giả thành 5 reboot.

---

## B2. Consistency 10 phút (`A-W02-05`)

1. Đặt 3 đầu dò T1/T2/T3 **cạnh nhau trong cùng điều kiện** (cùng một khoang/bát giữ nhiệt,
   tránh gió, tránh tay người). Ghi lại cách đặt bằng ảnh nếu muốn.
2. Chạy capture 10 phút:
   ```powershell
   py firmware/tools/cg_capture.py --port COM4 --out evidence/A/W02/serial-w02-consistency.log --seconds 620
   ```
3. Dựng CSV + thống kê:
   ```powershell
   py firmware/tools/cg_build_sensor_csv.py evidence/A/W02/serial-w02-consistency.log --out evidence/A/W02/sensor-consistency.csv --summary-out evidence/A/W02/sensor-consistency-summary.md --min-samples 600 --json evidence/A/W02/sensor-consistency-stats.json
   ```
   Kết quả cần: `WINDOW USABLE` (≥600/600 mẫu hợp lệ mỗi đầu dò) và `window duration`
   ≈ 600 giây, `effective rate` ≈ 1 Hz **đo được** (không còn là suy luận).

---

## B3. Chu kỳ cửa + polarity (`A-W02-07`)

1. **Quan sát vật lý trước, đừng đoán:** mở cửa, nhìn dòng `#CG DOOR_EDGE … raw=?` và
   ghi lại mức thô khi cửa **mở**.
2. Chạy capture và thực hiện **≥20 lần mở/đóng** có chủ đích (mỗi lần giữ mở ~1–2 giây):
   ```powershell
   py firmware/tools/cg_capture.py --port COM4 --out evidence/A/W02/serial-w02-door.log --seconds 180
   ```
3. Dựng CSV với mức mở đã quan sát (ví dụ quan sát thấy cửa mở ⇒ `raw=0`):
   ```powershell
   py firmware/tools/cg_build_door_csv.py evidence/A/W02/serial-w02-door.log --out evidence/A/W02/door-test.csv --open-level 0 --require-cycles 20
   ```
   Kết quả cần: `DOOR TEST: CYCLES PROVEN (24 >= 20)` và có `edges per transition` để
   nói về dội tiếp điểm.
   Lưu ý: capture chỉ được chứa cửa của **một boot**. Nếu log có dòng cửa sau ≥2 khối
   `#CG BOOT`, công cụ **từ chối** (exit 1) cho tới khi chọn `--boot N` (N = thứ tự khối
   boot, tính từ 0) — bộ đếm giữa các boot không bao giờ bị trộn.
4. Nếu polarity đã chốt, đổi `CG_DOOR_POLARITY_CONFIRMED 1` + `CG_DOOR_RAW_OPEN_LEVEL <mức>`
   trong `coldguard_config.h` (commit riêng, dẫn chiếu file `door-test.csv`).

---

## B4. Dán nhãn vật lý (`A-W02-02`, cần cho leader review)

1. Nhãn **T1** (gần cửa) → đầu dò có ROM `287088CA00000051`; **T2** (giữa) → `28AEBF2200000006`;
   **T3** (xa/đối diện) → `28CBE9CA00000072`; **SPARE** → `283BE5C9000000A9`.
2. Cách tìm đúng đầu dò cho từng ROM: rút/để riêng từng đầu dò trong khi xem log — đầu dò
   nào mất thì dòng `#CG ERR msg=probe_state role=… status=… present=0` chỉ ra vai trò đó.
3. Chụp ảnh nhãn + vị trí, lưu `photo-labels-*.jpg`; cập nhật `physical_label` trong
   `sensor-rom-map.yaml` từ `PENDING` sang giá trị thật, kèm ngày.

---

## B5. BME280 (`A-W02-06`)

Chưa thuộc firmware W02 (driver I²C chưa nằm trong repo). Test tối thiểu cần ghi lại:

- I²C address đọc được (0x76/0x77),
- chip-ID,
- T/RH đọc được và mức hợp lý (so với nhiệt độ phòng),
- vị trí gá không bị ESP32/V1 sấy nóng (ảnh + mô tả khoảng cách).

Kết quả thật → commit bổ sung **vào cùng PR** kèm ảnh/log; **không** đánh dấu PASS trước đó.

---

## Sau khi xong

```powershell
py firmware/tools/run_all_checks.py
```

rồi cập nhật `acceptance.md` (trạng thái từng hạng mục) và `sensor-rom-map.yaml`
(`verification_status`). `validate_w02.py` sẽ chặn nếu hồ sơ tự mâu thuẫn.
