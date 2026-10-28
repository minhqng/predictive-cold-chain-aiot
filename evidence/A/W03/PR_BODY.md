# [A-W03] Power path, RS-485/PZEM read-only tooling, IBT-2 safe-state logic + bench evidence 2026-10-27

**Base:** `feat/a-w02-sensor-foundation` (stacked — W02 chưa merge) · **Head:** `feat/a-w03-power-pzem-logic` · **Loại:** NORMAL PR — **không** tự merge
**Issue/pack:** `A-W03-01` … `A-W03-07`
**Parent docs:** `docs/04 §18`, `docs/05A §12`, `docs/01 §9` (PZEM), `§10` (RS-485), `§11.7/§11.8` (pin map, actuator default-off), `§12` (IBT-2/TEC)
**Evidence path:** `evidence/A/W03/` · **Nguồn trạng thái duy nhất:** `evidence/A/W03/acceptance.md`

## Tóm tắt

PR này giao phần W03 không cần phần cứng: firmware ESP-IDF đọc PZEM-017 **read-only**,
safe-state IBT-2 **default-OFF**, pin map v2 trong cấu hình, cùng bộ công cụ host và kiểm tra
tĩnh. Firmware **chưa** được nạp/chạy trên board; các bài bench 2026-10-27 là **sketch
Arduino**, không phải firmware W03. Phần kiểm chứng vật lý còn lại được liệt kê ngắn ở §5 và
ghi chi tiết trong `acceptance.md` §4.

## 1. Đã implement (firmware + cấu hình)

- **Pin map v2** (`firmware/main/coldguard_config.h`, `CG_PIN_MAP_VERSION=2`) theo
  `evidence/A/as-built-pinmap-2026-10-27.md`: DS18B20=33, BME280 SDA/SCL=21/34, MC-38=35,
  RS-485 TX/RX=36/37 (AUTO), IBT-2 RPWM/R_EN/L_EN=5/6/10. Validator host
  `firmware/tools/cg_gpio_map.py` kiểm tra quyền sở hữu chân + guard `#error` (gồm cấu hình
  MANUAL DE/RE trùng GPIO35 của MC-38 phải fail lúc compile).
- **Safe-state IBT-2 (W03: không PWM):** `cg_actuator_force_off()` chạy trước NVS/sensor/task,
  kéo **R_EN và L_EN về 0 trước RPWM**; không LEDC/MCPWM; `CG_ACTUATOR_ENABLE_ALLOWED=0` nên
  `cg_actuator_outputs_allowed()` từ chối mọi output. Invariant một phía: chỉ một nửa cầu được
  lệnh; hai nửa cầu cùng duty cho **hai đầu ra bằng nhau → không có vi sai** (không phải lệnh
  đảo chiều) — W03 không tạo vi sai nào.
- **RS-485/PZEM read-only:** `cg_crc16` (init `0xFFFF`, poly `0xA001`, low-byte-first, CRC kiểm
  **trước** khi diễn giải); `cg_pzem` chỉ có builder FC `0x04`/`0x03`, **không** tồn tại builder
  ghi register; scaling V/I `0.01`, P/Wh 32-bit low-word-first; `cg_rs485` mặc định 8N1 +
  `CG_RS485_DIR_MODE 0` (AUTO) cho TTL485-V2.0 as-built; `cg_power` poll 1 Hz, timeout 250 ms ×
  tối đa 2 attempts, log grammar v2 với `uptime_ms` thật.
- **Công cụ host:** `cg_modbus.py`, `cg_pzem_readback.py` (từ chối `read_only=0`/CRC lệch),
  `cg_build_pzem_off_csv.py`, `cg_check_firmware_w03.py`, `run_all_checks_w03.py`.

## 2. Kiểm chứng đã chạy

| Lớp | Kết quả |
|---|---|
| Python unittest (W03) | **PASS** — 153 test (gồm 10 test actuator safety, 17 test pin map) |
| Python unittest (W02 regression) | **PASS** — 74 test |
| Kiểm tra tĩnh firmware W03 | **PASS** — 96 check (parity register/scaling, read-only, CRC-trước-khi-tin, retry bound, default-OFF, boot order, grammar, CMake, pin map v2, guard `#error` MANUAL DE/RE) |
| Kiểm tra tĩnh firmware W02 (regression) | **PASS** — 39 check |
| `validate_w02.py` / `validate_w03.py` | **PASS** — cấu trúc hồ sơ, `firmware_commit` (git cat-file), workflow CI, content anchors, hai bundle verifier |
| Bundle verifier 2026-10-27 | **PASS** — hash, 600 hàng, span 598.99 s, gate `REVIEW REQUIRED`, CRC TEST 131 |
| Bundle verifier 2026-10-20 | **PASS** — 7/7 hash, 601/594/7, 7 frame CRC, FC06 archive-only |
| **Native ESP-IDF v6.1 build (`esp32s3`)** | **PASS** — 1.090/1.090 bước Ninja, 0 warning, 0 error, trên commit `f8587dd`; log + checksum + verifier ở `build-native-windows-2026-10-27/` |
| **Native build trên working tree hiện tại (2026-10-28)** | **PASS** — cùng 1.090 bước, 0 warning, 0 error, trên đúng mã nguồn sẽ commit (pin map v2 + safe-OFF 3 chân); log + `SHA256SUMS.txt` + verifier ở `build-native-windows-2026-10-28/` |

CI GitHub Actions của repo hiện bị chặn bởi hạn mức thanh toán tài khoản (`Billing & plans`,
run `40532665748`) → `INFRASTRUCTURE-LIMITED`; bằng chứng compile lấy từ bản native ở trên.
Workflow `a-w03-espidf-build.yml` (image `espressif/idf:v6.1`, target `esp32s3`, không flash)
vẫn giữ nguyên.

## 3. Bằng chứng bench 2026-10-27 (sketch Arduino, không phải firmware W03)

| Test | Kết quả | Nhãn |
|---|---|---|
| TEST 132B (OFF envelope) | 600/600 hợp lệ, `rx_len=29`, span **598.99 s**, log tự gate `RESULT: REVIEW REQUIRED`; `0.00 A`/`0.0 W` dưới độ phân giải hiển thị | `MEASURED — BENCH ARTIFACT` |
| TEST 131 (50 A profile) | frame `01 03 02 00 01 79 84`, CRC `0x8479` khớp host-side; không có file capture gốc | `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` |
| TEST 133B (reset/default-OFF) | 120/120 mẫu `0.00 A`, 5 lần restart + cold boot thủ công vẫn OFF; `SCOPE: AFTER FIRMWARE START ONLY` | `OPERATOR-REPORTED` |
| Shunt continuity | `≈0 Ω / ≈453 kΩ / ≈24–25 kΩ / ≈0.98 A` (DMM, operator-reported) | `OPERATOR-REPORTED` |

Phân loại từng câu (đo / lời khai / suy luận / chưa đo):
`hardware-2026-10-27/provenance-matrix.md`.

## 4. Lệch cấu hình `GPIO10` (đã xử lý ở mức cấu hình)

W02 **cấu hình** `CG_PIN_DS18B20_DATA = GPIO10` và đã đọc 4 ROM ID/620 mẫu với cấu hình đó;
lời khai as-built IBT-2 lại đặt `L_EN` trên `GPIO10`. Đây là **lệch giữa giá trị cấu hình
firmware và lời khai đấu dây**, không phải bằng chứng hai dây vật lý cùng một chân — chưa có
phép đo continuity. Map v2 tách hai chức năng (DS18B20→GPIO33, `L_EN`=GPIO10) và không thay đổi
dây/BOM. `TD-W03-03` đóng ở mức cấu hình; continuity vẫn `MEASUREMENT REQUIRED` và **cấm cấp
nguồn tải/TEC** cho tới khi đo.

## 5. Chưa xác minh (tóm tắt; chi tiết ở `acceptance.md` §4)

- Firmware W03 **chưa nạp/chạy** trên board → chưa có `#CG PZEM_CFG`/`#CG PZEM_RANGE` thật
  (`PENDING_READBACK`); OFF envelope canonical chưa có (`pzem-off.csv` khai báo `MISSING`).
- Mức logic RS-485: module 5 V; cần xác nhận ≤3.3 V ở GPIO37 trước khi đấu — **hạn chế an toàn
  điện**; change review `CR-A-W01-01` (TTL485 vs MAX3485) vẫn mở.
- Continuity `GPIO10` và tie-off `LPWM` chưa đo; topology đường hồi shunt chưa kết luận.
- `hardware_config_id` as-built chưa gán (`NOT_ASSIGNED`).
- 7 frame `INVALID` của archive 2026-10-20 chưa rõ nguyên nhân; lần FC06 SET50 trong archive là
  sai lệch quy trình (archive giữ nguyên, `ARCHIVE ONLY — DO NOT FLASH OR EXECUTE`).

## 6. Cách kiểm chứng cục bộ

```text
py firmware/tools/run_all_checks_w03.py                        # 5/5: unittest, static W03, static W02, validate W02, validate W03
py evidence/A/W03/validate_w03.py                              # cấu trúc + firmware_commit + anchors + 2 bundle verifier
py evidence/A/W03/hardware-2026-10-27/verify_test132b.py       # hash, 600 hàng, span 598.99 s, gate REVIEW REQUIRED, CRC TEST 131
py evidence/A/W03/hardware-2026-10-20/verify_capture.py        # 7/7 hash, 601/594/7, 7 frame CRC, FC06 archive-only
```

## 7. Ghi chú tích hợp

- PR stacked trên `feat/a-w02-sensor-foundation` (PR #8, còn OPEN); retarget `main` sau khi W02
  merge thuộc quy trình tích hợp. PR này không sửa nội dung W01/W02 ngoài fix đóng gói
  `.gitignore` (`!evidence/**/*.log`) đã nêu trong W02.
- PR **không** tự merge. Review mã nguồn/hồ sơ độc lập vẫn cần trước khi delivery, nhưng việc
  công nhận phần đã kiểm chứng bằng máy không phụ thuộc vào một chữ ký phê duyệt riêng.
- Giới hạn an toàn điện trong §5 là ràng buộc vận hành, không phải điều kiện hành chính.
