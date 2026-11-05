# ColdGuard — Member A — W02: firmware và công cụ kiểm chứng

Thư mục này chứa **công cụ host** đi kèm firmware W02 (`firmware/main/`) và một bộ
kiểm tra tự động chạy được **không cần phần cứng, không cần cài thêm gói**.

Toàn bộ công cụ chỉ dùng thư viện chuẩn Python 3 (trừ `cg_capture.py` cần `pyserial`
khi đọc cổng COM thật; phần phân tích không cần `pyserial`).

---

## 1. Chạy toàn bộ kiểm tra (một lệnh)

```powershell
cd <repo>
py firmware/tools/run_all_checks.py
```

Chạy ba lớp kiểm tra: unittest của công cụ, kiểm tra tĩnh firmware, và validator hồ sơ
`evidence/A/W02/`. Exit code 0 chỉ khi cả ba PASS. Không lớp nào biên dịch firmware hay
chạm phần cứng.

---

## 2. Công cụ phân tích log (chạy trên bản ghi thật)

| Lệnh | Việc | Bằng chứng tạo ra |
|---|---|---|
| `py firmware/tools/cg_capture.py --port COM4 --out evidence/A/W02/sensor-w02-run.log --seconds 900` | Ghi log Serial Monitor **nguyên bản** + đầu mục metadata (giờ, cổng, host) | `serial log` có thể kiểm chứng |
| `py firmware/tools/cg_verify_reboots.py <log> --min-boots 5 --json reboot-report.json` | Xác minh ROM → vai trò **giữ nguyên qua ≥5 reboot** (A-W02-03); yêu cầu thêm `boot_id` phân biệt + `boot_count` tăng dần | `reboot-report.json` |
| `py firmware/tools/cg_build_sensor_csv.py <log> --out sensor-consistency.csv --summary-out sensor-consistency-summary.md --min-samples 600` | Dựng `sensor-consistency.csv` + mean/SD/pairwise/max disagreement (A-W02-05) | CSV + summary |
| `py firmware/tools/cg_build_door_csv.py <log> --out door-test.csv --open-level <0\|1> --require-cycles 20 [--boot N]` | Dựng `door-test.csv` + số chu kỳ + bằng chứng dội tiếp điểm (A-W02-07); capture trải nhiều boot phải chọn `--boot N` | CSV + thống kê |
| `py firmware/tools/cg_check_firmware.py` | Kiểm tra tĩnh firmware ↔ hồ sơ bằng chứng | báo cáo PASS/FAIL |

### Quy tắc chống tự lừa dối (đã được kiểm tra tự động)

* `nan` trong log → **ô CSV rỗng**, không bao giờ thành `0.0`. `SPARE` không có cờ `tN`
  trong grammar v1: token `nan` là dấu hiệu mất giá trị duy nhất của nó.
* `--min-samples` không đạt → exit code 1 và in `WINDOW NOT USABLE` (`WINDOW USABLE` chỉ
  khi mọi đầu dò đủ mẫu hợp lệ và không có giá trị `nan`).
* **Không** có `--open-level` → **mọi dòng dữ liệu** CSV có `state` = `UNVERIFIED`
  (không dòng nào mang `OPEN`/`CLOSED`), exit code 1. Công cụ không đoán polarity
  (docs/01 §8.2).
* `--require-cycles` không đạt → exit code 1.
* `cg_verify_reboots.py` chỉ PASS khi **≥5 boot thật**: `boot_id` đôi một phân biệt và
  `boot_count` tăng dần nghiêm ngặt (khối dán lặp, `boot_count` đứng yên hoặc bằng 0 ⇒
  `BOOT_METADATA_INVALID`). PASS in `... roles stable, boot metadata consistent`.
* Cửa: capture trải **nhiều boot** (có dòng cửa sau ≥2 khối `#CG BOOT`) → **từ chối**
  (exit 1, không bao giờ trộn bộ đếm giữa các boot); chọn `--boot N` để phân tích đúng
  một boot (`N` không có dòng cửa → exit 2).
* `cg_check_firmware.py` đối chiếu ROM trong `coldguard_config.h` với
  `evidence/A/W02/sensor-rom-map.yaml` và **tính lại CRC8 Dallas** của từng ROM
  (bắt lỗi chép sai ký tự).

---

## 3. Trình tự bench còn thiếu (cần người thao tác phần cứng)

Xem `evidence/A/W02/bench-procedure-w02.md` để có danh sách ngắn, có lệnh cụ thể cho
từng bước: BME280, nhãn vật lý, 5 chu kỳ reboot, 10 phút consistency, chu kỳ cửa.

---

## 4. Chạy test của chính công cụ

```powershell
cd firmware/tools
py -m unittest discover -s tests -t tests -v
```

Test dùng log **tổng hợp** sinh trong thư mục tạm. Không có dữ liệu tổng hợp nào được
ghi vào `evidence/`.

---

## 5. Điều công cụ này KHÔNG chứng minh

* Bộ kiểm tra này **không** biên dịch firmware; nó chỉ kiểm tra hợp đồng tĩnh.
  Việc build chạy riêng bằng ESP-IDF v6.1 trên máy bench, log và hash được ghim
  tại `evidence/A/W04/build-2026-11-01/`.
* Không thay thế H0 mechanical, không thay thế bài test BME280 thật, không dán nhãn
  vật lý, không tạo dữ liệu cảm biến.
* Không phát hiện thiết bị 1-Wire lạ trên bus: firmware W02 đọc theo ROM cố định và
  **không** cài ROM search (giới hạn đã khai báo trong hồ sơ).

---

## 6. W04 — TEC commissioning

Bản W04 thêm đường dẫn TEC fail-closed và telemetry thô. Output stage **bị tắt
khi biên dịch** (`CG_TEC_OUTPUT_STAGE_ENABLED = 0`), mọi giới hạn vận hành ở
trạng thái `UNRESOLVED`, nên lệnh `START` luôn bị từ chối trên bản giao này.

| Lệnh | Việc |
|---|---|
| `py firmware/tools/run_all_checks_w04.py` | Chạy unittest (gồm harness C của state machine), checker W04, checker W02/W03 và validator hồ sơ |
| `py firmware/tools/cg_check_firmware_w04.py` | Kiểm tra tĩnh: fail-closed, giới hạn chưa RESOLVED, thứ tự enable/PWM, telemetry, GPIO, tài liệu |
| `py firmware/tools/cg_build_telemetry.py <capture> --jsonl raw.jsonl --csv telemetry.csv --ml-out ml.csv` | Tách capture thô thành JSONL trung thực, CSV acquisition và dataset ML dẫn xuất |

Harness C (`tests/cg_tec_harness.c`) biên dịch nguyên `cg_tec_control.c` +
`cg_tec_limits.c` và chạy 34 kịch bản offline (boot, timeout, cảm biến lỗi/già,
interlock, ESTOP, CLEAR, heartbeat, rollback phần cứng). Test Python tự tìm MSVC
qua `vswhere`, hoặc `cc`/`gcc` nếu có.

Quy tắc dữ liệu W04: `nan` → ô rỗng/`None`, không bao giờ thành 0;
`timestamp_utc=UNAVAILABLE` vì thiết bị không có đồng hồ thực; `t_ambient_c` và
`t_cold_side_c` là `NOT_ASSIGNED` và RH là `SENSOR_NOT_PRESENT` cho tới khi có
phép đo/gán probe thật. `t_inside_c` lấy từ T1 (`CHAMBER_CENTER`), còn
`t_hot_side_c` lấy từ T2 (`TEC_HOT_SIDE` — ROM `28AEBF2200000006`, mặt tản nhiệt
TEC, không phải không khí trong buồng); mỗi field tự khai nguồn qua
`t_inside_src` / `t_hot_side_src`. Kế hoạch cổng G0–G5 nằm trong
`docs/06-tec-commissioning-safety-and-limits.md`.
