# [A-W03] Power Path, RS-485/PZEM Read-Only Tooling and IBT-2 Safe-State Logic

> **⚠️ W03 NOT PASS — READ FIRST.** Bộ chứng cứ này là hồ sơ review, **không** phải nghiệm
> thu W03. Mở PR này **không** đồng nghĩa W03 đã PASS. Toàn bộ hành vi phần cứng W03
> (RS-485, PZEM, OFF envelope, XL4015 có tải, IBT-2 cold-boot) vẫn `PENDING` vì mức logic
> RS-485 chưa được Member D + leader duyệt (CR-A-W01-01) và chưa có buổi đo thật. Điều
> **đã** đạt: firmware + công cụ + test tự động + kiểm tra tĩnh (84 check W03), regression
> W02, và compile thật trên CI (xem `build-report-w03.md`).

**Base:** `feat/a-w02-sensor-foundation` (stacked — W02 chưa merge; xem §6) · **Head:** `feat/a-w03-power-pzem-logic` · **Loại:** NORMAL PR (Ready for Review — không phải Draft)
**Issue/pack:** `A-W03-01` … `A-W03-07`
**Parent docs:** `docs/04 §18` (W03), `docs/05A §12` (Member A W03), `docs/01 §9` (PZEM), `§10` (RS-485), `§11.7/§11.8` (pin map, actuator default-off), `§12` (IBT-2/TEC)
**Reviewer bắt buộc:** Member D (`docs/04 §3.3`: wiring / pin / sensing / safety)
**Hardware config affected?:** Chưa — `hardware_config_id` vẫn `NOT_ASSIGNED`. PR này phát hiện lệch freeze (**TTL485-V2.0 ≠ MAX3485**) đã có trong W01 = `CR-A-W01-01`, nay kèm phân tích firmware/công cụ cho hướng xử lý; **không** tự thay đổi BOM.
**Evidence path:** `evidence/A/W03/`
**Trạng thái W03:** **`W03 NOT PASS`** — acceptance matrix đầy đủ ở `evidence/A/W03/acceptance.md` (nguồn trạng thái duy nhất).

---

## 1. Member A đã hoàn thành những gì (phần không cần phần cứng)

- **Firmware W03 trong repo** (`firmware/main/`, +6 module C mới):
  - `cg_crc16.c/.h` — CRC16/MODBUS (init `0xFFFF`, poly `0xA001`, CRC low-byte-first); mọi khung nhận đều phải qua CRC **trước khi** được diễn giải.
  - `cg_pzem.c/.h` — giao thức PZEM-017 **chỉ đọc**: đọc input `0x0000..0x0005` (FC `0x04`) và holding `0x0003` = current-range (FC `0x03`). **Không tồn tại builder ghi** register trong firmware lẫn công cụ host (A-W03-04 yêu cầu READ ONLY trước). Phân loại `OK/TIMEOUT/CRC_ERR/BAD_SLAVE/BAD_FUNCTION/BAD_LENGTH/EXCEPTION`; scaling V/I `0.01`, P/Wh 32-bit low-word-first; `nan` khi lỗi — **không** giữ giá trị cũ.
  - `cg_rs485.c/.h` — UART1 transport: framing từ macro (mặc định **8N1**, **không** tự giả định 8N2); `CG_RS485_DIR_MODE 0` (AUTO) là mặc định cho **TTL485-V2.0 as-built** (không có chân DE//RE); MANUAL (GPIO35) chỉ là compile-time option cho MAX3485 canonical — xem lệch freeze §4.
  - `cg_power.c/.h` — task poll 1 Hz theo deadline: tx/rx raw hex, timeout 250 ms × **tối đa 2 attempts** (bounded, không lặp vô hạn), 3 loại dòng log `PZEM_CFG` / `PZEM_RANGE` / `PZEM` với `uptime_ms` thật từ `esp_timer`.
  - `cg_actuator.c/.h` — safe-state IBT-2 **logic-only**: ép `RPWM GPIO5` + `ENABLE GPIO6` về 0 (enable trước), **không** cấu hình LEDC/MCPWM (không tồn tại PWM trong W03), guard `cg_actuator_outputs_allowed()` từ chối mọi output khi chưa authorization / hai chiều đối nghịch / quá dải. Với `CG_ACTUATOR_ENABLE_ALLOWED 0`, lệnh rời cũng không thể bật nhánh TEC.
  - `cg_log.h grammar v2` — v1 **không đổi** + 3 kind mới; parser v2 đọc được capture v1 (có unit test khóa hành vi); `app_main.c` gọi `cg_power_start()` sau safety; firmware version `cg-w03-0.1.0`.
- **Công cụ host** (`firmware/tools/`):
  - `cg_modbus.py` — codec tham chiếu (CRC, builder chỉ đọc, classify, scaling, decode range) được đối chiếu **từng hằng số** với firmware bằng kiểm tra tĩnh.
  - `cg_serial.py` (mở rộng) — parse 3 kind mới, thống kê link (success/error rate, CRC/timeout counts, attempts, gaps > 2×median) và thống kê power (mean/sd/min/max/spread trên **mẫu hợp lệ**; mẫu lỗi không vào mean).
  - `cg_pzem_readback.py` — tái giải mã `#CG PZEM_RANGE` từ log thật: **CRC tính lại host-side**, value + profile đối chiếu chéo firmware↔host; từ chối capture thiếu `read_only=1`; từ chối CRC lệch; `--expect-profile 50A` bắt buộc để kết luận.
  - `cg_build_pzem_off_csv.py` — dựng `pzem-off.csv` + summary từ log thật: **từ chối** window < 600 s, thiếu xác nhận TEC OFF của người vận hành (`--tec-off-confirmed`), trộn nhiều boot, hay tỉ lệ mẫu hợp lệ thấp; ô trống cho mẫu lỗi (không lặp giá trị cũ).
- **Kiểm chứng tự động** (chạy trên máy hiện tại, lệnh trong §7):
  - **113 unittest PASS** (W02: 57; W03 thêm 56) — CRC vector từ sketch bench W01, bit-flip phải bị bắt, read-only FC, classify, word-order P/Wh, parser v1↔v2, thống kê, CLI từ chối dữ liệu không đạt.
  - **84 check tĩnh W03 PASS** (`cg_check_firmware_w03.py`) — parity register/scaling ↔ `cg_modbus.py`, quét FC ghi, CRC-trước-khi-tin, retry bound, token parity, default-OFF, boot order, grammar, CMake completeness.
  - **39 check tĩnh W02 PASS** + `validate_w02.py` **PASS (9/9 blob hash)** — regression W02 nguyên vẹn trên nhánh W03.
  - **CI GitHub Actions**: run `39213118829` — **SUCCESS cả hai job** (`idf.py build` esp32s3 + host checks; số liệu + SHA-256 trong `build-report-w03.md` §2/§3). Run đầu tiên FAIL vì một lỗi biên dịch thật (macro config trùng tên enum RS-485) — đã fix ở `b858693`, **giữ nguyên trong báo cáo** để truy vết (`build-report-w03.md` §4).

## 2. Deliverable canonical (`docs/05A §12`) — trạng thái thật

| Deliverable | Trạng thái | Ghi chú |
|---|---|---|
| `logic-power-measurement.md` | **CÓ** — số đo W03 còn trống | Phần W01 (user-reported) + kế hoạch đo có tải; `MEASUREMENT REQUIRED` |
| `pzem-register-readback.txt` | **CÓ — nội dung PENDING** | Chưa từng có log PZEM thật trong repo; file ghi schema + lệnh sinh dữ liệu thật, **không** chèn hex giả |
| `pzem-off.csv` | **MISSING (khai báo)** | Chưa có raw ≥600 s; không tạo từ fixture (validator từ chối nếu file xuất hiện khi chưa có buổi đo) |
| `rs485-wiring.png` | **MISSING (khai báo)** | Không vẽ lại sơ đồ từ trí nhớ; sơ đồ chính thức thuộc buổi D duyệt CR-A-W01-01 |
| `ibt2-pin-map.md` | **CÓ** | Pin map từ ảnh W01 `14-ibt2-actual.jpg` + hành vi default-OFF + câu trả lời "43 A" |

## 3. Review tĩnh một vòng (chi tiết `review-w03.md`)

Một vòng review đối kháng nội bộ (CRC/scaling, parser/timeout, readback CLI, ngân sách
độ dài dòng log, UART/hướng, tương thích mức logic, IBT-2 default-OFF, regression W02) đã
chạy trên máy và **không có defect nào trong các lớp đó**. Lớp **compile thật (CI)** bắt
thêm **một** defect mà static check + unittest không thể thấy: macro config
(`CG_RS485_DIR_MANUAL`) trùng tên enum constant trong `cg_rs485.h`
(`coldguard_config.h:151: error: expected identifier before numeric constant`) — **đã
fix** ở `b858693` (enum → `CG_RS485_MODE_*`), ghi ở `review-w03.md` §6 và
`build-report-w03.md` §4. Hai ghi chú tồn dư (không phải defect) được giữ lại trong
`review-w03.md` §4: margin buffer log khi bộ đếm chạy nhiều năm, và nhánh MANUAL không
được compile trong CI. **Review này không thay thế reviewer độc lập và không phải phê
duyệt an toàn của Member D.**

## 4. Những gì CHƯA xác minh (nêu tường minh)

| Hạng mục | Trạng thái | Chi tiết |
|---|---|---|
| Mức logic RS-485 (CR-A-W01-01) | **`SAFETY REVIEW PENDING` — D + leader** | Module thật là **TTL485-V2.0 5 V, auto-direction** (không phải MAX3485 đã freeze); TXD idle 5 V, phân áp tạm 10k/10k/10k → ~3.314 V tại GPIO37 (**user-reported W01, không đo lại**). **Không** được đấu 5 V vào GPIO; **không** được giả định RO là 3.3 V. Không bài UART phần cứng nào chạy trong W03 (cố ý). |
| PZEM communication thật | **`CODE IMPLEMENTED / HARDWARE RUN PENDING` + `MEASUREMENT REQUIRED`** | Chưa từng poll module thật bằng firmware W03; slave/framing thật phải xác nhận bằng log thật (8N1 là mặc định có grounds, không phải kết luận). |
| 50 A profile | **`PENDING_READBACK`** | Chỉ đọc; **không** suy profile từ nhãn shunt `50A 75mV`. Lệnh xác nhận: `cg_pzem_readback.py <capture> --expect-profile 50A`. |
| OFF envelope ≥10 phút | **`MEASUREMENT REQUIRED`** | Công cụ xong + đã test; chưa có buổi đo (TEC chưa từng được cấp nguồn). |
| XL4015 có tải | **`MEASUREMENT REQUIRED`** | W01 chỉ có ~5 V no-load (user-reported); ripple/nhiệt/dòng tải chưa đo. |
| Shunt inspection có điện | **`MEASUREMENT REQUIRED / SAFETY REVIEW PENDING (D)`** | Ảnh W01 chứng minh nhãn in `50A 75mV` + khắc `FL-2 0.5`; đường dòng/đầu cốt/lực kẹp **không** nhìn thấy trong ảnh nào. |
| IBT-2 cold-boot / tie-off | **`SAFETY REVIEW PENDING (D)`** | Firmware default-OFF đã kiểm chứng tĩnh; chưa có log reset/watchdog trên board; `LPWM`/`L_EN` chờ D quyết định tie-off. |
| Nạp + chạy firmware W03 | **CHƯA** | Không flash, không mở serial trong W03; mọi hành vi runtime là PENDING. |

## 5. Yêu cầu review cụ thể cho Member D

1. **CR-A-W01-01** (`hardware-deviation-and-safety.md`, `rs485-pin-and-compatibility.md`): chấp nhận TTL485-V2.0 + phân áp (kèm ràng buộc đo lại mức logic **trước** khi nối GPIO37) hay yêu cầu thay module 3.3 V đúng freeze. Đây là **blocker** của mọi bài UART phần cứng W03.
2. **IBT-2**: duyệt tie-off `LPWM`/`L_EN` (`ibt2-pin-map.md` §5) và phương án log cold-boot/reset default-OFF an toàn (chưa cấp tải TEC).
3. **Shunt**: duyệt checklist kiểm tra đường dòng/đầu cốt khi nguồn OFF trước khi bất kỳ tải nào đi qua shunt.
4. Xác nhận rằng W03 **không** bật bất kỳ output nào (REVIEW READ-ONLY: 5 file firmware mới không có LEDC/MCPWM, guard từ chối tất cả).

## 6. Phụ thuộc W02 (stacked PR)

- PR này **stacked trên** `feat/a-w02-sensor-foundation` (PR **#8**, còn OPEN). Base của PR này cố ý là nhánh W02 vì W02 chưa merge — review diff sẽ sạch hơn base `main`.
- Khi W02 merge vào `main`, PR này cần được **retarget sang `main`** (leader/B quyết định thời điểm; PR này không tự đổi).
- PR này **không** sửa nội dung W01/W02. Có **một sửa lỗi đóng gói W02** kèm theo: `.gitignore` từng loại `evidence/A/W02/espidf-run/serial-reboot-original.log` (`*.log`) khỏi checkout sạch ⇒ `validate_w02.py` fail; nhánh W03 thêm ngoại lệ `!evidence/**/*.log` và commit lại **đúng byte** file log (SHA-256 khớp pin của validator W02). Đây là fix đóng gói, không đổi số liệu W02.

## 7. Cách kiểm chứng cục bộ (reviewer)

```text
py firmware/tools/run_all_checks_w03.py        # 5 lớp: unittest, static W03, static W02, validate W02, validate W03
py evidence/A/W03/validate_w03.py              # cấu trúc hồ sơ + firmware_commit (git cat-file)
```

- CI thật: GitHub Actions, workflow `a-w03-espidf-build.yml` (image `espressif/idf:v6.1`, target `esp32s3`) — kết quả + SHA-256 trong `build-report-w03.md`.
- **Miễn trừ trách nhiệm:** PR này không phải nghiệm thu W03 và không thay thế bất kỳ phê duyệt an toàn nào của Member D/leader.
