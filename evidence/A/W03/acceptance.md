# W03 acceptance matrix — Member A

**Trạng thái hồ sơ: `W03 NOT PASS`** (tương tự W02: hồ sơ review, không phải nghiệm thu).
File này là **nguồn trạng thái duy nhất** của W03; `README.md` chỉ tóm tắt. Script `validate_w03.py` kiểm tra các nhãn trong file này, nhưng **không** đọc hiểu văn xuôi và **không** xác nhận bất kỳ sự thật vật lý nào.

**Quy ước nhãn trạng thái dùng trong W03:**

| Nhãn | Nghĩa |
|---|---|
| `VERIFIED BY EXISTING EVIDENCE` | Đã có bằng chứng thật từ trước (W01/W02) nhưng **không** do phiên W03 này đo lại; chỉ dùng trong phạm vi bằng chứng đó |
| `CODE IMPLEMENTED / HARDWARE RUN PENDING` | Code đã có trong repo + đã được test tự động/kiểm tra tĩnh + đã compile thật trên CI, nhưng **chưa** nạp/chạy trên phần cứng |
| `MEASUREMENT REQUIRED` | Phải có người vận hành đo/log thật mới được nâng trạng thái; không suy diễn từ ảnh, unit test hay nhãn linh kiện |
| `SAFETY REVIEW PENDING` | Phải được Member D (và leader khi lệch freeze) duyệt trước khi cấp nguồn/thao tác |
| `LEADER APPROVAL PENDING` | Cần leader quyết định (lệch freeze, phạm vi, lịch) |
| `PENDING_READBACK` | Cần một lần đọc thật từ module (PZEM) — hiện chưa từng có trong repo |

---

## 1. Acceptance matrix A-W03-01 … A-W03-07

### A-W03-01 — XL4015 logic supply (~5 V)

- **Canonical yêu cầu:** set output logic, đo bằng đồng hồ, ghi giá trị no-load/load nếu thực tế. Target ~5 V trong giới hạn module.
- **Trạng thái:** `VERIFIED BY EXISTING EVIDENCE (W01 user-reported) + MEASUREMENT REQUIRED`.
  - Có: báo cáo người dùng trong W01 — XL4015 ~5 V (không tải), TB4506 ~4.99 V; fuse 5 A cho XL4015 (W01 `hardware-audit-w01.md`, `physical-risk-ledger.md` R04).
  - Thiếu: đo có tải, ripple, nhiệt, và ghi lại **trong phiên W03** bằng đồng hồ với người vận hành; chưa từng đo dòng logic tổng.
- **Điều kiện nâng trạng thái:** phiên đo W03 với đúng trình tự trong `logic-power-measurement.md` §3, ghi số vào file đó; có D khi cấp nguồn cho tải.
- **Người quyết định còn lại:** Member A (đo) + D (chứng kiến/duyệt tải).

### A-W03-02 — MAX3485 / RS-485

- **Canonical yêu cầu:** module VCC = 3.3 V; map `DI/RO/DE//RE/A/B`; dùng UART/RS-485 mode hoặc điều khiển hướng tường minh.
- **Thực tế phần cứng (đọc từ ảnh W01 `02-rs485-front.jpg`, `03-rs485-back.jpg`):** module là **TTL485-V2.0**, rail 5 V, **auto-direction, không có chân DE//RE**; đầu tín hiệu chỉ `GND/RXD/TXD/VCC`; cầu A/B/GND; điện trở 120 Ω có jumper. **Không phải** MAX3485 đã freeze (W01 `freeze-deviation-review.md` CR-A-W01-01, đang PENDING).
- **Mức logic:** theo báo cáo người dùng W01 — TXD idle 5 V, phân áp tạm 10k/10k/10k → ~3.314 V đo được tại GPIO37 (tính ≈ 3.33 V); **agent không đo lại**. Không được đấu 5 V trực tiếp vào GPIO; **không được giả định RO là 3.3 V**.
- **Trạng thái:** `SAFETY REVIEW PENDING — Member D + leader (CR-A-W01-01)`; chưa có bài UART phần cứng nào được chạy trong W03 (cố ý, xem `hardware-deviation-and-safety.md`).
- **Điều kiện nâng trạng thái:** D + leader chấp nhận (a) module TTL485-V2.0 với phân áp, hoặc (b) mua module 3.3 V đúng freeze; sau đó mới loopback/log UART thật. Khi đó firmware đã sẵn sàng: `CG_RS485_DIR_MODE 0` (AUTO) là mặc định; MANUAL (GPIO35) chỉ là compile-time option cho module MAX3485 canonical.
- **Người quyết định còn lại:** D + leader.

### A-W03-03 — PZEM communication

- **Canonical yêu cầu:** kiểm tra nguồn phía module, slave address, Modbus CRC, framing thật; nếu 8N1 fail thì rà revision tài liệu trước khi kết luận lỗi phần cứng.
- **Trạng thái:** `CODE IMPLEMENTED / HARDWARE RUN PENDING` + `MEASUREMENT REQUIRED`.
  - Đã implement + test tự động: CRC16/MODBUS (init 0xFFFF, poly 0xA001), khung đọc FC 0x04 (input 0x0000..0x0005) và FC 0x03 (holding 0x0003), timeout 250 ms/2 attempts/poll 1 Hz, phân loại `OK/TIMEOUT/CRC_ERR/BAD_SLAVE/BAD_FUNCTION/BAD_LENGTH/EXCEPTION/UART_ERR`, `uptime_ms` thật từ `esp_timer`, scaling V/A/W/Wh theo LSB canonical, `nan` khi lỗi (không giữ giá trị cũ).
  - Framing: mặc định **8N1** cấu hình bằng macro (`CG_RS485_*`); **không** tự giả định 8N2 (canonical yêu cầu rà revision tài liệu của module thật trước).
  - Thiếu: phiên thật đọc PZEM trên module as-built (slave/framing/CRC phải xác nhận bằng log thật; chưa từng có).
- **Điều kiện nâng trạng thái:** log `#CG PZEM_CFG` + ≥1 chu kỳ `#CG PZEM` OK từ firmware trên board, đối chiếu `cg_pzem_readback.py`/`cg_build_pzem_off_csv.py`.
- **Người quyết định còn lại:** Member A (chạy) sau khi A-W03-02 được duyệt an toàn.

### A-W03-04 — 50 A profile

- **Canonical yêu cầu:** đọc/đặt current-range register; bằng chứng phải cho thấy `0x0001` hoặc cấu hình 50 A tương đương.
- **Trạng thái:** `CODE IMPLEMENTED / HARDWARE RUN PENDING` + `PENDING_READBACK`.
  - Đã implement: **chỉ đọc** holding 0x0003 (FC 0x03) — không có builder ghi register trong firmware lẫn công cụ host; profile 50 A ứng với raw `0x0001`; tool `cg_pzem_readback.py` tái giải mã CRC/value/profile từ hex thật và đối chiếu chéo với log firmware.
  - **Không** suy profile 50 A từ nhãn shunt `50A 75mV` (nhãn chỉ là thuộc tính shunt, không chứng minh register).
  - Thiếu: lần đọc thật từ module (`pzem-register-readback.txt` hiện là bản ghi PENDING).
- **Điều kiện nâng trạng thái:** chạy `py firmware/tools/cg_pzem_readback.py <capture> --expect-profile 50A` trên log thật và ghi kết quả vào `pzem-register-readback.txt` (giữ raw tx/rx + CRC + decode).
- **Người quyết định còn lại:** Member A (chạy) — **cấm** ghi register đổi profile trong W03.

### A-W03-05 — OFF electrical envelope (TEC OFF)

- **Canonical yêu cầu:** với TEC OFF vật lý, thu ≥10 phút mẫu PZEM; đo voltage, current noise/zero, power noise/zero, Modbus error rate.
- **Trạng thái:** `MEASUREMENT REQUIRED`.
  - Công cụ đã xong + đã test: `cg_build_pzem_off_csv.py` từ chối window < 600 s, từ chối khi thiếu `#CG PZEM_CFG`/`read_only=1`, từ chối trộn nhiều boot, bắt buộc `--tec-off-confirmed` (xác nhận vận hành — tool không tự kiểm chứng được), từ chối khi tỉ lệ mẫu hợp lệ < ngưỡng; CSV để ô trống cho mẫu lỗi; thống kê mean/min/max/sd(noise)/gap/success rate.
  - Thiếu: phiên đo thật ≥10 phút (chưa cấp nguồn TEC bao giờ; PZEM cũng chưa từng được firmware W03 poll).
  - `pzem-off.csv` được khai báo **MISSING** (chưa có raw thật — xem §3).
- **Điều kiện nâng trạng thái:** file `pzem-off.csv` + summary sinh từ log thật bằng công cụ trên, kèm xác nhận TEC OFF của vận hành.
- **Người quyết định còn lại:** Member A (chạy) + D (chứng kiến OFF envelope theo handoff `docs/05A §12`).

### A-W03-06 — Shunt installation inspection

- **Canonical yêu cầu:** đúng đường dòng, đầu cốt chắc, không dùng dây tín hiệu trong đường dòng lớn, marking vật lý 50 A / 75 mV.
- **Trạng thái:** `VERIFIED BY EXISTING EVIDENCE (ảnh W01) + MEASUREMENT REQUIRED / SAFETY REVIEW PENDING (D)`.
  - Có (đọc từ ảnh W01 `04-pzem-shunt.jpg`, `18-shunt-marking-actual.jpg`): nhãn **in** `50A 75mV`; khắc `FL-2 0.5`; PZEM-017 ghi `RANGE: U DC 0—300V`; cổng RS-485 `5V/A/B/GND`.
  - **Không** nhìn thấy trong bất kỳ ảnh nào: đường dòng đã mắc nối tiếp đúng nhánh low-side chưa, cỡ dây/đầu cốt, lực kẹp, dây sense Kelvin, và tình trạng có điện (W01 `physical-risk-ledger.md` R05 = `NOT_TESTED`).
  - Ảnh không chứng minh được "không dùng dây tín hiệu trong đường dòng lớn" — chỉ kiểm tra được bằng mắt khi có điện (hoặc ảnh cận cảnh mới có chú thích vật lý).
- **Điều kiện nâng trạng thái:** phiên kiểm tra có D (nguồn OFF trước khi chạm), ảnh cận cảnh mới + checklist; sau đó mới cấp tải qua shunt.
- **Người quyết định còn lại:** D (an toàn) + Member A (thao tác).

### A-W03-07 — IBT-2 logic only

- **Canonical yêu cầu:** xác nhận nhãn chân module thật, enable, PWM input, reset/default state; **không** suy dòng liên tục từ giới hạn chip `43 A`.
- **Trạng thái:** `CODE IMPLEMENTED / HARDWARE RUN PENDING` + `SAFETY REVIEW PENDING (D)`.
  - Đã có (đọc từ ảnh W01 `14-ibt2-actual.jpg`): module HW-039, BTS7960B ×2, SN74HC244; header `VCC R_IS R_EN RPWM` / `GND L_IS L_EN LPWM`; cầu đấu xanh 4 vị trí; pin map chi tiết ở `ibt2-pin-map.md`.
  - Firmware W03: **logic-only, default OFF** — ép `RPWM GPIO5` + `ENABLE GPIO6` về 0 ngay đầu `app_main` (trước NVS/task/sensor/PZEM); không cấu hình LEDC/MCPWM; không tồn tại lệnh ghi mức 1 lên hai chân này; guard `cg_actuator_outputs_allowed()` từ chối mọi output khi chưa có authorization (`CG_ACTUATOR_ENABLE_ALLOWED=0`).
  - Thiếu: log cold-boot/reset/watchdog thật với tải an toàn; quyết định tie-off `LPWM`/`L_EN` (mạch kéo 10 kΩ đã có trên bench theo báo cáo W01 R06 — **chưa** được log); và quan trọng nhất: **chưa có authorization nào để bật** — W03 không bật.
  - Trả lời câu hỏi leader (`docs/05A §12`): `43 A` là **giới hạn dòng của chip BTS7960B** trong điều kiện lý tưởng, không phải định mức liên tục của module (điện trở dẫn, tản nhiệt, đầu cos, dây, duty) — chi tiết `ibt2-pin-map.md` §4.
- **Điều kiện nâng trạng thái:** D duyệt sơ đồ đấu dây + tie-off; log cold-boot/reset default-OFF; chỉ sau đó mới xét PWM ở W04.
- **Người quyết định còn lại:** D (safety) + leader (lịch W04).

---

## 2. Pass criteria canonical (`docs/05A §12`) — đối chiếu

| Tiêu chí canonical | W03 hiện tại |
|---|---|
| MAX3485 powered correctly | **KHÔNG ĐẠT** — thực tế là TTL485-V2.0 5 V; chưa được D/leader duyệt mức logic (CR-A-W01-01); chưa có phiên UART W03 |
| PZEM stable enough to poll | **CHƯA CHỨNG MINH** — code + tool đã sẵn sàng; chưa từng poll bằng firmware W03 |
| 50 A range verified | **CHƯA** — `PENDING_READBACK`; không suy từ nhãn shunt |
| OFF envelope measured | **CHƯA** — `MEASUREMENT REQUIRED` |
| IBT-2 can remain disabled/default OFF | **PHẦN CODE: CÓ** (logic-only default OFF + guard + kiểm tra tĩnh); **PHẦN PHẦN CỨNG / D: PENDING** |

→ Kết luận: **W03 NOT PASS**. Đây là hồ sơ review trung thực với blocker nêu tường minh.

## 3. Artifact canonical khai báo còn thiếu

| Artifact canonical (`docs/05A §12 Deliverables`) | Trạng thái | Lý do |
|---|---|---|
| `logic-power-measurement.md` | **CÓ** (đã tạo trong W03) | Có phần "đã có từ W01" + kế hoạch đo; số đo W03 vẫn trống vì chưa chạy |
| `pzem-register-readback.txt` | **CÓ — nội dung PENDING** | Chưa từng có log/thư viện PZEM thật trong repo; file ghi rõ điều kiện và lệnh sinh dữ liệu thật, không chèn hex giả |
| `pzem-off.csv` | **MISSING** (khai báo) | Chưa có raw thật ≥600 s; công cụ từ chối tạo từ dữ liệu không đạt |
| `rs485-wiring.png` | **MISSING** (khai báo) | Không vẽ lại sơ đồ từ trí nhớ; W01 đã có ảnh module thật (`02/03-rs485-*.jpg`) làm nguồn; sơ đồ đấu dây chính thức là việc D duyệt cùng CR-A-W01-01 |
| `ibt2-pin-map.md` | **CÓ** (đã tạo trong W03) | Pin map từ ảnh thật + hành vi default-OFF + việc chờ D |

## 4. Blocker và điều kiện chuyển trạng thái (điều kiện để W03 PASS)

1. **Mức logic RS-485:** D + leader duyệt CR-A-W01-01 (TTL485-V2.0 5 V + phân áp tạm, hoặc mua module đúng freeze). Chặn mọi bài UART phần cứng.
2. **PZEM readback thật:** chạy firmware trên board, thu `#CG PZEM_CFG`/`#CG PZEM_RANGE`; nâng `pzem-register-readback.txt` khỏi PENDING. (Không đổi profile bằng ghi.)
3. **OFF envelope:** phiên ≥10 phút TEC OFF theo `cg_build_pzem_off_csv.py`; sinh `pzem-off.csv` thật; D chứng kiến.
4. **XL4015:** đo lại có tải + ghi số trong `logic-power-measurement.md`.
5. **Shunt:** kiểm tra đường dòng/đầu cốt với D khi chưa cấp tải; ảnh cận cảnh.
6. **IBT-2:** D duyệt tie-off; log cold-boot/reset default-OFF.
7. **Leader:** chấp nhận lệch TTL485 (hardware change review), gán `hardware_config_id`.

## 5. Quyết định cần D / leader (không tự quyết trong W03)

| Nội dung | Vì sao | Ai |
|---|---|---|
| CR-A-W01-01: chấp nhận TTL485-V2.0 + phân áp hay thay module | Lệch freeze + an toàn mức logic | D + leader |
| Tie-off `LPWM`/`L_EN` của IBT-2 | Tránh nửa cầu còn lại trôi nổi | D |
| Phạm vi OFF envelope (đo bao lâu, điều kiện phụ tải nào, ai chứng kiến) | Handoff D của `docs/05A §12` | D + Member A |
| Merge PR W03 khi W03 chưa PASS (hồ sơ review) | Để không chặn review kỹ thuật | Leader |
| Retarget PR base W02→main khi W02 merge | Thứ tự stacked PR | Leader/B |
