# [A-W03] Power path, RS-485/PZEM read-only tooling, IBT-2 safe-state logic + bench evidence 2026-10-27

> **⚠️ ĐỌC TRƯỚC — `MEMBER A W03 EVIDENCE — DELIVERED FOR REVIEW`.**
> **Cổng nhóm: `W03 TEAM GATE: PENDING_REVIEW`. Kỹ thuật: `W03 NOT PASS`.**
> PR này đưa hồ sơ W03 ra review; **không** phải nghiệm thu W03 và **không** tuyên bố bất kỳ
> bài đo phần cứng nào đã PASS. Firmware ESP-IDF W03 **chưa từng chạy trên board**. Ba bài
> bench mới (TEST 131/132B/133B) là **sketch Arduino**, không phải firmware W03; log của
> TEST 132B tự kết luận `RESULT: REVIEW REQUIRED`.

**Base:** `feat/a-w02-sensor-foundation` (stacked — W02 chưa merge) · **Head:** `feat/a-w03-power-pzem-logic` · **Loại:** NORMAL PR (Ready for Review) — **không** tự merge
**Issue/pack:** `A-W03-01` … `A-W03-07`
**Parent docs:** `docs/04 §18`, `docs/05A §12`, `docs/01 §9` (PZEM), `§10` (RS-485), `§11.7/§11.8` (pin map, actuator default-off), `§12` (IBT-2/TEC)
**Reviewer bắt buộc:** Member D (`docs/04 §3.3`: wiring / pin / sensing / safety)
**Hardware config affected?:** Chưa — `hardware_config_id` vẫn `NOT_ASSIGNED`. PR ghi nhận các lệch freeze đã có từ W01 (`CR-A-W01-01`, `CR-A-W01-02`, `CR-A-W01-03/04`) và **một xung đột pin mới** (`GPIO10`), nhưng **không** sửa BOM/pinout.
**Evidence path:** `evidence/A/W03/`
**Nguồn trạng thái duy nhất:** `evidence/A/W03/acceptance.md` · **Quyết định chờ D/leader:** `evidence/A/W03/team-dependencies.md`

---

## 0. Cập nhật 2026-10-27 — bench evidence + xung đột pin

Phần này bổ sung cho lịch sử PR và **không** nâng W03.

### 0.1 Bằng chứng mới (đã lưu byte-for-byte + hash)

| Test | File | Hash / kết quả | Trạng thái |
|---|---|---|---|
| **TEST 132B** (OFF envelope) | `hardware-2026-10-27/raw/test-132b-off-envelope.log` (20 618 B) | SHA-256 `0af8a083…c557e` | `MEASURED — BENCH ARTIFACT` |
| TEST 132B (CSV trích nguyên văn) | `raw/test-132b-off-envelope.csv` (19 157 B) | SHA-256 `7eac5f80…f81d8`, 600 hàng | 600/600 hợp lệ, 0 lỗi |
| **TEST 131** (50 A profile) | `test-131-profile-readback.md` | frame `01 03 02 00 01 79 84`, CRC `0x8479` khớp | `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` |
| **TEST 133B** (reset/default-OFF) | `firmware/ColdGuard_TEST_133B_reset_default_off.ino` | SHA-256 `8986a21c…e296b` | `OPERATOR-REPORTED` — 120/120 mẫu, không có raw log |
| Shunt continuity | `shunt-continuity.md` | `≈0 Ω / ≈453 kΩ / ≈24–25 kΩ / ≈0.98 A` | `OPERATOR-REPORTED`; failure mode mở |
| Phân loại bằng chứng | `hardware-2026-10-27/provenance-matrix.md` | — | `MEASURED` / `OPERATOR-REPORTED` / `INFERRED` / `NOT MEASURED` |

### 0.2 Số liệu TEST 132B — đọc đúng

| Chỉ số | Giá trị |
|---|---|
| Mẫu / hợp lệ / lỗi | **600 / 600 / 0** (`SUCCESS_RATE 100.00 %`) |
| Điện áp | min/max `11.94/11.95 V`; mean `11.9483 V` |
| Dòng / công suất / energy | `0.00 A` / `0.0 W` / `0 Wh` — **dưới độ phân giải hiển thị**, không phải zero tuyệt đối |
| `rx_len` | `29` mọi hàng (cấu trúc 21+8 byte là suy luận từ độ dài) |
| Cửa sổ mẫu | `10 ms → 599000 ms` = **598.99 s**, không phải 600.00 s |
| Gate của log | **`RESULT: REVIEW REQUIRED`** — hồ sơ không nâng thành PASS |
| TEC OFF | **Operator-reported**, không có kênh đo độc lập |

### 0.3 Ba việc phải chặn trước freeze

1. **`GPIO10` xung đột:** as-built báo `L_EN → GPIO10`, nhưng W02 dùng `GPIO10` cho
   `CG_PIN_DS18B20_DATA` (đã đọc 4 ROM ID/620 mẫu). Không thể cùng một chân → `TD-W03-03`.
   W03 **không** đổi pinout/dây để né.
2. **Failure mode shunt:** `B−` common với GND logic (`≈0 Ω`); nếu shunt/đầu cốt hở, dòng hồi
   TEC có thể đi qua GND logic. Đây là **giả thuyết từ continuity**, chưa xảy ra sự cố
   → `TD-W03-02`.
3. **Cửa sổ OFF envelope:** 600 mẫu nhưng span `598.99 s`; "≥10 phút" tính theo
   `DURATION_MS 600000` hay theo span thật là quyết định của D → `TD-W03-04`.

### 0.4 Patch echo/prefix (firmware + host)

- RX buffer **32 byte**, đọc UART theo **idle gap 10 ms**, chỉ chọn frame **kết thúc ở tail**;
  chấp nhận shape **FC04 17 byte / FC03 7 byte / exception 5 byte**; loại frame cũ/exception
  không khớp; log raw RX để điều tra. Không thêm FC06/FC16, không đổi actuator/TEC.
- **Host PASS** (126 unittest, 89 static W03, 39 static W02). **ESP-IDF compile cho
  patch: phải chờ CI trên commit mới** — run cũ `39213118829` chỉ áp dụng cho commit `ae1744d` (cây `firmware/` giống hệt `b858693`).
- Patch **không** được tuyên bố là đã sửa 7 frame lỗi của archive 2026-10-20 (phiên khác,
  không có raw frame để so sánh).

---

## 1. Member A đã hoàn thành những gì (phần không cần phần cứng)

- **Firmware W03 trong repo** (`firmware/main/`):
  - `cg_crc16.c/.h` — CRC16/MODBUS (init `0xFFFF`, poly `0xA001`, low-byte-first); mọi khung
    nhận phải qua CRC **trước khi** được diễn giải.
  - `cg_pzem.c/.h` — PZEM-017 **chỉ đọc**: input `0x0000..0x0005` (FC `0x04`), holding `0x0003`
    (FC `0x03`). **Không tồn tại builder ghi** register. Phân loại
    `OK/TIMEOUT/CRC_ERR/BAD_SLAVE/BAD_FUNCTION/BAD_LENGTH/EXCEPTION/UART_ERR`; scaling V/I
    `0.01`, P/Wh 32-bit low-word-first; `nan` khi lỗi.
  - `cg_rs485.c/.h` — UART1: framing từ macro (mặc định **8N1**); `CG_RS485_DIR_MODE 0` (AUTO)
    cho TTL485-V2.0 as-built; MANUAL (GPIO35) chỉ là compile-time option cho MAX3485 canonical.
  - `cg_power.c/.h` — poll 1 Hz, timeout 250 ms × tối đa 2 attempts, log
    `PZEM_CFG`/`PZEM_RANGE`/`PZEM` với `uptime_ms` thật từ `esp_timer`.
  - `cg_actuator.c/.h` — IBT-2 **logic-only**: `RPWM GPIO5` + `ENABLE GPIO6` về 0 (enable
    trước), không LEDC/MCPWM, guard `cg_actuator_outputs_allowed()` từ chối mọi output khi
    `CG_ACTUATOR_ENABLE_ALLOWED=0`.
  - `cg_log.h` grammar v2 — v1 không đổi + 3 kind mới; `app_main.c` gọi `cg_power_start()` sau
    safety; firmware version `cg-w03-0.1.0`.
- **Công cụ host** (`firmware/tools/`): `cg_modbus.py`, `cg_serial.py` (mở rộng),
  `cg_pzem_readback.py` (CRC host-side, từ chối `read_only=0`/CRC lệch),
  `cg_build_pzem_off_csv.py` (≥600 s, `--tec-off-confirmed`, chống trộn boot, ô trống cho mẫu
  lỗi), `cg_check_firmware_w03.py`, `run_all_checks_w03.py`.
- **Kiểm chứng tự động:** 126 unittest, 89 static W03, 39 static W02, `validate_w02.py`,
  `validate_w03.py` (gồm hai bundle verifier). CI ESP-IDF v6.1/esp32s3 **SUCCESS** cho
  `0171d0a`; run FAIL đầu tiên (lỗi macro trùng enum) được giữ nguyên để truy vết.

## 2. Deliverable canonical (`docs/05A §12`) — trạng thái thật

| Deliverable | Trạng thái | Ghi chú |
|---|---|---|
| `logic-power-measurement.md` | **CÓ** — số đo W03 còn trống | W01 operator-reported + kế hoạch đo; `MEASUREMENT REQUIRED` |
| `pzem-register-readback.txt` | **CÓ — `PENDING_READBACK`** | TEST 131 frame operator-reported + CRC host-side; **không** capture gốc, **không** log firmware W03 |
| `pzem-off.csv` | **MISSING (khai báo)** | Không có raw canonical từ firmware W03; CSV bench nằm trong bundle ngày, không copy lên root |
| `rs485-wiring.png` | **MISSING (khai báo)** | Không vẽ lại từ trí nhớ; sơ đồ chính thức thuộc buổi D duyệt CR-A-W01-01 |
| `ibt2-pin-map.md` | **CÓ** | Pin map từ ảnh W01 + default-OFF + xung đột `GPIO10` + câu trả lời "43 A" |

## 3. Những gì CHƯA xác minh (nêu tường minh)

| Hạng mục | Trạng thái | Chi tiết |
|---|---|---|
| Mức logic RS-485 (CR-A-W01-01) | **`SAFETY REVIEW PENDING` — D + leader** | TTL485-V2.0 5 V auto-direction; phân áp tạm 10k/10k/10k (~3.314 V tại GPIO37, operator-reported W01). Không đấu 5 V vào GPIO; không giả định RO là 3.3 V |
| PZEM bằng firmware W03 | **`HARDWARE RUN PENDING`** | Chưa từng poll module thật bằng ESP-IDF; TEST 132B là Arduino bench, gate `REVIEW REQUIRED` |
| 50 A profile | **`PENDING_READBACK`** | Frame TEST 131 tự nhất quán CRC nhưng **không** có capture gốc; không suy từ nhãn shunt |
| OFF envelope canonical | **`MEASUREMENT REQUIRED`** | Bench 598.99 s, TEC OFF operator-reported; CSV không phải schema canonical |
| Patch echo/prefix | **HOST PASS (PYTHON UNITTEST + STATIC CHECKS) — ESP-IDF CI PENDING — HARDWARE NOT RUN** | Chờ CI trên commit mới trước khi flash |
| XL4015 có tải | **`MEASUREMENT REQUIRED`** | W01 chỉ ~5.00 V no-load |
| Shunt có điện / an toàn tải lớn | **`SAFETY REVIEW PENDING (D)`** | Continuity chỉ là số đọc DMM; failure mode return path mở |
| IBT-2 cold-boot / tie-off | **`SAFETY REVIEW PENDING (D)`** | TEST 133B chỉ quan sát sau khi firmware chạy; chuỗi LOW là hằng chuỗi do sketch in |
| Pin map không xung đột | **KHÔNG** — `GPIO10` trùng DS18B20 | `TD-W03-03` |
| Nạp + chạy firmware W03 | **CHƯA** | Không flash, không mở serial trong W03 |

## 4. Yêu cầu review cụ thể cho Member D

1. **`TD-W03-01` / CR-A-W01-01:** chấp nhận TTL485-V2.0 + phân áp cho bench (kèm ràng buộc đo
   lại mức logic trước khi nối GPIO37) hay yêu cầu module 3.3 V đúng freeze.
2. **`TD-W03-03`:** chốt as-built `GPIO10` (L_EN hay DS18B20 DATA) và `pin_map_version`.
3. **`TD-W03-02`:** duyệt topology return/star-ground của shunt và tiêu chí kiểm tra đầu cốt
   trước khi có tải; xác nhận failure mode đã được đánh giá đúng.
4. **`TD-W03-06`:** duyệt tie-off `LPWM`/`L_EN` và phương pháp log cold-boot/reset default-OFF.
5. **`TD-W03-04` / `TD-W03-05` / `TD-W03-07`:** cách tính cửa sổ OFF envelope; có cần capture
   gốc TEST 131/133B không; xử lý lần FC06 SET50 ngoài hợp đồng read-only.
6. **REVIEW READ-ONLY:** xác nhận W03 **không** bật output nào — không LEDC/MCPWM, không ghi
   mức 1 lên `RPWM`/`ENABLE`, guard từ chối tất cả.

## 5. Phụ thuộc W02 (stacked PR)

- PR **stacked trên** `feat/a-w02-sensor-foundation` (PR **#8**, còn OPEN). Base cố ý là nhánh
  W02 để diff review sạch; khi W02 merge, PR này cần **retarget sang `main`** (leader/B quyết).
- PR **không** sửa nội dung W01/W02. Có một fix đóng gói W02 kèm theo: `.gitignore` từng loại
  `evidence/A/W02/espidf-run/serial-reboot-original.log` (`*.log`) khỏi checkout sạch ⇒
  `validate_w02.py` fail; nhánh W03 thêm ngoại lệ `!evidence/**/*.log` và commit lại đúng byte.
- **Xung đột mới phát hiện:** W02 dùng `GPIO10` cho DS18B20; as-built IBT-2 báo `L_EN` cũng
  `GPIO10`. Không tự sửa — xem `TD-W03-03`.

## 6. Cách kiểm chứng cục bộ (reviewer)

```text
py firmware/tools/run_all_checks_w03.py                        # 5/5: unittest, static W03, static W02, validate W02, validate W03
py evidence/A/W03/validate_w03.py                              # cấu trúc + firmware_commit + anchors + 2 bundle verifier
py evidence/A/W03/hardware-2026-10-27/verify_test132b.py       # hash, 600 hàng, span 598.99 s, gate REVIEW REQUIRED, CRC TEST 131
py evidence/A/W03/hardware-2026-10-20/verify_capture.py        # 7/7 hash, 601/594/7, 7 frame CRC, FC06 archive-only
```

- Kiểm chứng trên máy là **host/Python + static checks**; repo **không** có native C harness,
  và đây **không** phải build ESP-IDF.
- CI thật: `a-w03-espidf-build.yml` (image `espressif/idf:v6.1`, target `esp32s3`). Kết quả
  của commit này được ghi ở `build-report-w03.md` sau khi CI chạy.

## 7. Chính sách merge

- PR này **yêu cầu review**, **không** tự merge; không dùng approval của chính tác giả thay
  cho Member D/leader.
- Base giữ `feat/a-w02-sensor-foundation`; việc retarget/merge thuộc leader/B.
- Merge PR **không** làm W03 PASS: mọi gate phần cứng trong `acceptance.md` vẫn `PENDING`.
- **Miễn trừ trách nhiệm:** PR này không phải nghiệm thu W03 và không thay bất kỳ phê duyệt an
  toàn nào của Member D/leader.
