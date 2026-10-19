# W03 firmware and tooling verification (Member A)

**Ngày:** 2026-10-19 · **Phạm vi:** phần không cần phần cứng (mã nguồn + công cụ + kiểm tra tự động).
Notebook này mô tả **đã implement gì**, **đã kiểm chứng bằng gì**, và **chưa làm gì**. Không có mục nào trong đây là bằng chứng đo.

```
firmware_commit: b85869322fb8c9828e25942346465d1ec6e131d7
```

*(SHA trên là commit firmware W03 trong nhánh này (gồm cả fix enum RS-485 sau lần compile CI đầu — xem `build-report-w03.md` §4). `validate_w03.py` xác minh bằng `git cat-file`/`git show` rằng commit đó chứa đủ module W03 và `coldguard_config.h` có grammar 2 + actuator default-OFF — không chỉ so chuỗi.)*

## 1. Firmware W03 — module bản đồ

| Module | Vai trò |
|---|---|
| `firmware/main/cg_crc16.c/.h` | CRC16/MODBUS (init 0xFFFF, poly 0xA001, tính & kiểm tra, CRC ghi low-byte-first) |
| `firmware/main/cg_pzem.c/.h` | Giao thức PZEM: builder **chỉ đọc** (FC 0x04 input 0x0000..0x0005; FC 0x03 holding 0x0003), phân tích/classify khung trả lời, scaling V/A/W/Wh, tên profile. **Không có builder ghi** |
| `firmware/main/cg_rs485.c/.h` | UART1 transport: framing từ macro (8N1 mặc định), AUTO direction mặc định; MANUAL (GPIO35) chỉ khi biên dịch với `CG_RS485_DIR_MODE 1` (module MAX3485 canonical) |
| `firmware/main/cg_power.c/.h` | Task poll 1 Hz (deadline-paced): tx/rx raw, timeout 250 ms × tối đa 2 attempts, log `PZEM_CFG`/`PZEM`/`PZEM_RANGE`; `nan` khi lỗi; đếm ok/fail |
| `firmware/main/cg_actuator.c/.h` | Safe-state IBT-2: `force_off()` (ENABLE=0 trước, RPWM=0), guard `outputs_allowed()` từ chối khi chưa authorization/đối nghịch/ngoài dải; không PWM |
| `firmware/main/cg_safety.c/.h` | Gọi actuator force-off + log `#CG SAFETY` (giữ nguyên như W02, giờ ủy quyền pin cho `cg_actuator`) |
| `firmware/main/coldguard_config.h` | Toàn bộ cấu hình W03 (RS485/PZEM/actuator), grammar v2, firmware version `cg-w03-0.1.0`; giữ `CG_PIN_MAP_VERSION 1` |
| `firmware/main/cg_log.h` | Grammar v2 = v1 không đổi + `PZEM_CFG`/`PZEM_RANGE`/`PZEM` |
| `firmware/main/app_main.c` | Gọi `cg_power_start()` sau safety; giữ nguyên v1: safety off trước NVS/task/sensor |

Quyết định thiết kế quan trọng:

- **Grammar v2 tương thích ngược:** parser v2 đọc được capture v1 (có unit test khóa hành vi này); parser v1 cũ "bỏ qua kind lạ" đúng như thiết kế v1.
- **Timeout/retry có giới hạn:** timeout là kết quả được phân loại (`TIMEOUT`), không phải lý do lặp vô hạn; giới hạn bằng `CG_PZEM_MAX_ATTEMPTS` (static check khẳng định vòng lặp có bound).
- **Địa chỉ trùng trực quan:** input 0x0003 (power-high) và holding 0x0003 (current-range) khác nghĩa theo function code — reader không được trộn hai nghĩa (đã ghi chú trong config lẫn code).

## 2. Công cụ host W03

| Công cụ | Vai trò | Kiểm chứng |
|---|---|---|
| `firmware/tools/cg_modbus.py` | Codec tham chiếu: CRC, builder chỉ đọc, classify, scaling, decode range | `test_cg_modbus.py` (16 test) |
| `firmware/tools/cg_serial.py` (mở rộng) | Parse `PZEM_CFG`/`PZEM_RANGE`/`PZEM`, `GRAMMAR_VERSION=2`; thống kê link + power (mean/min/max/sd/spread/gaps/success/error) | `test_cg_serial_pzem.py` (21 test) + test W02 cũ vẫn PASS |
| `firmware/tools/cg_pzem_readback.py` | Tái giải mã `#CG PZEM_RANGE` từ log thật: CRC host-side, value, profile, đối chiếu chéo với firmware; yêu cầu `read_only=1` | `test_cg_pzem_tools.py` |
| `firmware/tools/cg_build_pzem_off_csv.py` | Dựng `pzem-off.csv` + summary: ≥600 s, chống trộn boot, bắt buộc `--tec-off-confirmed`, ô trống cho mẫu lỗi | `test_cg_pzem_tools.py` |
| `firmware/tools/cg_check_firmware_w03.py` | Kiểm tra tĩnh: parity register/scaling ↔ `cg_modbus.py`, read-only, CRC trước khi tin khung, framing macro, retry bound, token parity, default-OFF, boot order, grammar, CMake | chính nó: **84 check PASS** |
| `firmware/tools/run_all_checks_w03.py` | Một lệnh chạy toàn bộ 5 lớp kiểm tra | xem §3 |

## 3. Kiểm tra đã chạy trên máy hiện tại (2026-10-19)

```
py firmware/tools/run_all_checks_w03.py
```

| Lớp | Kết quả |
|---|---|
| unittest (W02 + W03) | **113 test PASS** (trước W03: 57; W03 thêm 56 test) |
| static W03 (`cg_check_firmware_w03.py`) | **84 check PASS** |
| static W02 (`cg_check_firmware.py`, regression) | **39 check PASS** |
| `validate_w02.py` (regression) | **W02 STRUCTURE PASS — 9/9 bench blob hash verified** (validator nay chạy được trên checkout sạch nhờ file log được đóng gói kèm — xem §5) |
| `validate_w03.py` | **W03 STRUCTURE PASS** (chi tiết khi chạy) |

Các test tập trung vào đúng nơi dễ sai:

- CRC: vector độc lập `01 04 0000 0001 31 CA` (từ sketch bench W01); mọi bit-flip phải bị bắt; low-byte-first.
- Read-only: builder ném lỗi với FC 0x05/0x06/0x0F/0x10; static check quét literal FC ghi trong `cg_pzem.{c,h}` + `cg_modbus.py`.
- Classify: `BAD_SLAVE`, `BAD_FUNCTION`, `BAD_LENGTH`, `CRC_ERR`, `EXCEPTION` (kèm mã), và "no response" là `BAD_LENGTH` phía parser còn `TIMEOUT` thuộc transport (không trộn).
- Scaling: V/I 0.01; P/Wh 32-bit low-word-first (test đảo word chứng minh thứ tự); decode cần đủ 6 thanh ghi.
- Parser: `nan` → `None`; số trên dòng non-OK **không** vào thống kê; grammar v1 vẫn parse; boot grouping; malformed được ghi lại.
- Thống kê: success/error rate, status counts, CRC/timeout counts, gaps > 2×median, sd/spread; mẫu lỗi không vào mean.
- CLI: readback từ chối thiếu cfg / `read_only=0` / CRC lệch host-firmware / profile mismatch; builder từ chối window < 600 s / thiếu xác nhận TEC OFF / trộn boot / tỉ lệ hợp lệ thấp; CSV ô trống đúng chỗ.

## 4. Compile thật

Xem `build-report-w03.md` (GitHub Actions, image `espressif/idf:v6.1`, target `esp32s3`). Kết quả ghi trong file đó — **không** nằm trong file này để tránh mâu thuẫn khi CI cập nhật.

## 5. Sửa lỗi đóng gói W02 (kèm trong nhánh W03)

`evidence/A/W02/espidf-run/serial-reboot-original.log` (58 271 B, SHA-256 `e48977be20cd4e78d233f6c458d05e2d4486930283e0bac17e491320194f7854`) từng bị `.gitignore` (`*.log`) loại khỏi checkout W02 ⇒ `validate_w02.py` fail trên máy sạch. Nhánh W03 sửa bằng ngoại lệ `!evidence/**/*.log` và commit lại đúng file (hash khớp pin của validator). Đây là fix đóng gói, không đổi nội dung W02.

## 6. Giới hạn đã khai báo (không giấu)

1. **Chưa nạp/chạy firmware W03 trên board.** Mọi hành vi runtime (PZEM thật, framing thật, UART/RS-485) là `HARDWARE RUN PENDING`.
2. Test hành vi là **mô hình Python + kiểm tra tĩnh**; không có golden-run trên target. Lớp compile thật nằm ở CI.
3. RS-485 **không** chạy bài phần cứng nào vì mức logic chưa được duyệt (CR-A-W01-01) — xem `hardware-deviation-and-safety.md`.
4. `pzem-off.csv`, `rs485-wiring.png` được khai báo MISSING (không có dữ liệu thật/không vẽ lại sơ đồ từ trí nhớ).
5. W03 không thêm mqtt/telemetry/control — ngoài phạm vi tuần.
