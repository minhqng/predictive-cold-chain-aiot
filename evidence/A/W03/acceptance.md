# W03 acceptance matrix — Member A

**Trạng thái hồ sơ: `MEMBER A W03 EVIDENCE — IMPLEMENTED & VERIFIED WITHIN TESTED SCOPE`.**
**Kết luận theo hạng mục: xem §1 (`DONE` / `PARTIAL` / `HARDWARE-LIMITED` / `NOT IMPLEMENTED` /
`INFRASTRUCTURE-LIMITED`). Tệp này không chứa cổng phê duyệt chéo thành viên.**
File này là **nguồn trạng thái duy nhất** của W03; `README.md` chỉ tóm tắt. Script
`validate_w03.py` kiểm tra các nhãn trong file này, nhưng **không** đọc hiểu văn xuôi và
**không** xác nhận bất kỳ sự thật vật lý nào.

Phần firmware/công cụ W03 thuộc phạm vi Member A đã được kiểm chứng bằng unit test mô
hình + kiểm tra tĩnh + biên dịch thật (native ESP-IDF v6.1, `esp32s3`). Phần còn lại là
**kiểm chứng vật lý** (đo/log trên board), **việc triển khai** ngoài phạm vi W03, hoặc
**giới hạn hạ tầng** (CI GitHub Actions bị chặn billing) — không phải điều kiện phê duyệt
của thành viên khác.

> **Ghi chú 2026-10-28 — pin map v2.** Firmware chuyển sang
> `evidence/A/as-built-pinmap-2026-10-27.md`: DS18B20=33, BME=21/34, MC-38=35,
> RS-485 36/37 AUTO, IBT-2 RPWM/R_EN/L_EN=5/6/10; `CG_PIN_MAP_VERSION=2`.
> `cg_actuator_force_off()` xóa **cả R_EN và L_EN** trước RPWM; thêm validator
> `firmware/tools/cg_gpio_map.py` và guard `#error`. `TD-W03-03` đóng ở mức cấu hình;
> continuity vật lý **chưa đo** (xem `ibt2-pin-map.md` §2.1).

**Quy ước nhãn trạng thái dùng trong W03:**

| Nhãn | Nghĩa |
|---|---|
| `DONE` | Đã implement trong repo và kiểm chứng bằng máy (unit test mô hình + kiểm tra tĩnh và/hoặc biên dịch thật) trong phạm vi này |
| `PARTIAL` | Một phần hạng mục có bằng chứng thật; phần còn lại là kiểm chứng vật lý |
| `HARDWARE-LIMITED` | Code/logic xong nhưng **chưa nạp/chạy trên board**, hoặc cần phép đo điện để xác nhận |
| `NOT IMPLEMENTED` | Chưa triển khai (ngoài phạm vi W03 hoặc cần phần cứng chưa có) |
| `INFRASTRUCTURE-LIMITED` | Bị chặn bởi hạ tầng (ví dụ GitHub Actions billing), không phải lỗi kỹ thuật |
| `VERIFIED BY EXISTING EVIDENCE` | Có bằng chứng thật từ W01/W02 nhưng **không** do phiên W03 này đo lại |
| `MEASURED — BENCH ARTIFACT` | Có file gốc trong repo, hash được pin, đọc lại được bằng script; **vẫn** có thể không phải firmware W03 |
| `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` | Chỉ có lời khai/số đọc của người vận hành; không có file gốc để tái kiểm |
| `MEASUREMENT REQUIRED` | Phải có người vận hành đo/log thật mới được nâng trạng thái |
| `PENDING_READBACK` | Cần một lần đọc thật từ module (PZEM) bằng firmware W03 |
| `RAW_EVIDENCE_NOT_AVAILABLE` | Không có file capture gốc; hồ sơ không dựng lại log/ảnh/hex |

---

## 1. Acceptance matrix A-W03-01 … A-W03-07

### A-W03-01 — XL4015 logic supply (~5 V)

- **Canonical yêu cầu:** set output logic, đo bằng đồng hồ, ghi giá trị no-load/load nếu thực tế. Target ~5 V trong giới hạn module.
- **Trạng thái:** `PARTIAL` — `VERIFIED BY EXISTING EVIDENCE (W01 operator-reported, no-load)` + `MEASUREMENT REQUIRED` (có tải/ripple/nhiệt).
  - Có: W01 ghi XL4015 `5.00 V` (không tải), TB4506 `4.99 V`; fuse 5 A cho XL4015 (W01 `bom-audit.csv` HW-13/HW-16).
  - Thiếu: đo có tải, ripple, nhiệt, dòng logic tổng; chưa có phép đo nào trong phiên W03.
- **Bổ sung 2026-10-27:** phiên bench mới **không** đo lại rail logic; chỉ đo điện áp nhánh TEC qua PZEM (`11.94–11.95 V`, xem A-W03-05). Không suy rail 5 V từ số đó.
- **Điều kiện nâng trạng thái:** phiên đo W03 với đúng trình tự trong `logic-power-measurement.md` §3, ghi số vào file đó; cần một người thứ hai chứng kiến khi cấp nguồn cho tải → `TD-W03-09`.
- **Việc còn lại:** Member A đo; cần người chứng kiến khi cấp nguồn cho tải.

### A-W03-02 — MAX3485 / RS-485

- **Canonical yêu cầu:** module VCC = 3.3 V; map `DI/RO/DE//RE/A/B`; dùng UART/RS-485 mode hoặc điều khiển hướng tường minh.
- **Thực tế phần cứng (đọc từ ảnh W01 `02-rs485-front.jpg`, `03-rs485-back.jpg`):** module là **TTL485-V2.0**, rail 5 V, **auto-direction, không có chân DE//RE**; đầu tín hiệu chỉ `GND/RXD/TXD/VCC`; cầu A/B/GND; điện trở 120 Ω có jumper. **Không phải** MAX3485 đã freeze (W01 `freeze-deviation-review.md` CR-A-W01-01 — phê duyệt 2026-11-09).
- **Mức logic:** theo báo cáo W01 — TXD idle 5 V, phân áp tạm 10k/10k/10k → ~3.314 V tại GPIO37 (tính ≈ 3.33 V); **agent không đo lại**. Không được đấu 5 V trực tiếp vào GPIO; **không được giả định RO là 3.3 V**.
- **Trạng thái:** `PASS` (2026-11-10, theo đường nghiệm thu biến thể 5 V đã duyệt của evaluator chính thức; mô tả ở cập nhật 2026-11-10 bên dưới). **Hạn chế an toàn điện:** module 5 V; **không** nối 5 V trực tiếp vào GPIO37, phải xác nhận mức logic sau phân áp ở GPIO37 trước khi đấu.
  - **Bổ sung 2026-10-27:** sketch Arduino bench đã trao đổi được **600/600** phản hồi ở `9600 8N1`, slave `0x01`, qua đúng module as-built. Điều này chứng minh **đường UART bench hoạt động ở cấu hình đã dùng**, không chứng minh mức logic an toàn và **không** phải firmware ESP-IDF W03.
  - Không bài UART nào dùng firmware W03 được chạy (cố ý).
  - **Cập nhật 2026-11-09:** CR-A-W01-01 đã được **project owner phê duyệt** — TTL485-V2.0 là linh kiện as-built hợp lệ (decision log `evidence/A/W01/freeze-deviation-review.md`; BOM HW-07 `APPROVED_SUBSTITUTION`). Beyond bench (TEST 132B 600/600), bằng chứng giao tiếp trên **ESP32 thật** qua firmware `cg-w06-0.1.0`: capture 2026-11-07 (4 S1×600 khung, elec OK 600/600 — PR #91 dataset) và 2026-11-09 (600 khung, electrical_valid_rate 0.99667, 2 timeout startup). Chi tiết mapping DI/RO/DE//RE/A/B + mức logic: `rs485-pin-and-compatibility.md` §6. Các mục xác minh mở: ảnh marking chip, đo lại mức logic lần đấu lại, evaluator store rerun với VCC 5.0 V đúng bản chất module (đối chiếu mức GPIO37 ~3.314 V, không khai 3.3 V làm VCC module).
  - **Cập nhật 2026-11-10 (đường nghiệm thu biến thể 5 V đã duyệt):** evaluator chính thức (`handler_max3485`) tách hai cấu hình, không giảm yếu cấu hình gốc: (i) **MAX3485 3,3 V (freeze):** giữ nguyên yêu cầu VCC 3,2–3,4 V; (ii) **TTL485-V2.0 5 V (CR-A-W01-01):** cung module hợp lệ trong dải 4,5–5,5 V (thực đo 5,0 V — không khai 3,3 V), provenance phê duyệt (decision log 2026-11-09 + BOM HW-07 `APPROVED_SUBSTITUTION`), **mức vào ESP32 kiểm tra riêng** sau phân áp trong dải 2,475–3,4 V (VIH = 0,75×VDD = 2,475 V tại VDD 3,3 V; trần 3,4 V là logic ceiling 3,3 V-class của evaluator, dưới abs max VDD+0,3 = 3,6 V theo ESP32-S3 Series Datasheet v2.2 — authority đã trích trong docs/00 §ESP32-S3R2), cấm 5 V trực tiếp vào GPIO. Store reruns đúng kê khai thực đo: VCC module **5,0 V** (đo, không đổi thành 3,3), mức GPIO37 **3,314 V** (số người dùng báo từ bench W01, khớp tính toán phân áp ≈3,33 V) → toàn bộ check PASS; kết quả nguồn `OPERATOR_MEASUREMENT`; FAIL cũ (2026-11-04, `vcc_3v3_ABOVE_MAXIMUM`) archive trong `results/history/` của store. **Giới hạn còn mở:** marking chip MAX13487ESA vẫn chưa có ảnh; mức logic chưa đo lại sau thời gian lắp dài — checklist đo RO/TXD bằng đồng hồ trước khi nối GPIO37 **vẫn bắt buộc** cho lần đấu lại mạch kế tiếp; BOM approval không tự động chứng minh an toàn điện GPIO (mức đo tại chân là căn cứ).
- **Điều kiện nâng trạng thái:** cấu hình gốc MAX3485: VCC module 3,2–3,4 V. Biến thể đã duyệt TTL485-V2.0 5 V: mức sau phân áp tại GPIO37 trong dải 2,475–3,4 V (đối chiếu `rs485-pin-and-compatibility.md` §6); sau đó mới loopback/log UART thật bằng firmware W03.
- **Việc còn lại:** đo lại mức logic tại GPIO37 trước lần đấu lại mạch kế tiếp (xem `rs485-pin-and-compatibility.md` §6). `CR-A-W01-01` đã được project owner phê duyệt 2026-11-09 (decision log W01), không còn là change review mở; việc đo lại mức logic là yêu cầu an toàn điện, không phải cổng phê duyệt cấu hình.

### A-W03-03 — PZEM communication

- **Canonical yêu cầu:** kiểm tra nguồn phía module, slave address, Modbus CRC, framing thật; nếu 8N1 fail thì rà revision tài liệu trước khi kết luận lỗi phần cứng.
- **Trạng thái:** `DONE` (code + automated tests) + `HARDWARE-LIMITED` (chưa poll module bằng firmware W03).
  - Đã implement + test tự động: CRC16/MODBUS (init 0xFFFF, poly 0xA001), khung đọc FC 0x04 (input 0x0000..0x0005) và FC 0x03 (holding 0x0003), timeout 250 ms/2 attempts/poll 1 Hz, phân loại `OK/TIMEOUT/CRC_ERR/BAD_SLAVE/BAD_FUNCTION/BAD_LENGTH/EXCEPTION/UART_ERR`, `uptime_ms` thật từ `esp_timer`, scaling V/A/W/Wh theo LSB canonical, `nan` khi lỗi (không giữ giá trị cũ).
  - Framing: mặc định **8N1** cấu hình bằng macro; **không** tự giả định 8N2.
  - Thiếu: log `#CG PZEM_CFG` + `#CG PZEM` từ **firmware W03** trên board.
  - **Bổ sung 2026-10-27 (Arduino bench, KHÔNG phải ESP-IDF):** TEST 132B — **600 hàng, 600 hợp lệ, 0 lỗi**, `rx_len=29` mọi hàng, `SUCCESS_RATE 100.00 %`. Đây là `MEASURED — BENCH ARTIFACT` cho **sketch bench**, không phải `#CG PZEM_*` của W03. Log tự kết luận **`RESULT: REVIEW REQUIRED`**, không phải PASS.
  - Archive 2026-10-20 (601 mẫu / 594 hợp lệ / 7 lỗi) vẫn là provenance của lỗi cũ; phiên mới **không** chứng minh nguyên nhân đã được sửa.
- **Điều kiện nâng trạng thái:** log `#CG PZEM_CFG` + ≥1 chu kỳ `#CG PZEM` OK từ firmware trên board, đối chiếu `cg_pzem_readback.py`/`cg_build_pzem_off_csv.py`.
- **Việc còn lại:** Member A chạy sau khi mức logic RS-485 được đo/xác nhận.

### A-W03-04 — 50 A profile

- **Canonical yêu cầu:** đọc/đặt current-range register; bằng chứng phải cho thấy `0x0001` hoặc cấu hình 50 A tương đương.
- **Trạng thái:** `DONE` (read-only readback tooling) + `PARTIAL` (50 A profile mới `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE`) + `PENDING_READBACK` (ESP-IDF).
  - Đã implement: **chỉ đọc** holding 0x0003 (FC 0x03) — không có builder ghi register trong firmware lẫn công cụ host; profile 50 A ứng với raw `0x0001`; tool `cg_pzem_readback.py` tái giải mã CRC/value/profile từ hex thật.
  - **Bổ sung 2026-10-27 (TEST 131):** người vận hành báo frame `01 03 02 00 01 79 84`. CRC16/MODBUS tính lại host-side = `0x8479` → on-wire `79 84` **khớp**; `0x0001` = 50 A theo `docs/01 §9.3`. Frame **tự nhất quán**.
  - **Giới hạn:** `RAW_EVIDENCE_NOT_AVAILABLE` — không có file log/capture gốc cho TEST 131; không có tx/rx của lần đọc trong file. Hai phản hồi lỗi đầu tiên không có byte để phân tích. Vì vậy **không** được gọi là evidence-grade readback, và A-W03-04 **không** được nâng thành verified.
  - Không suy profile từ nhãn shunt `50A 75mV`.
  - Archive 2026-10-20 (`FC06 SET50`) là hành vi ngoài hợp đồng read-only, `ARCHIVE ONLY — DO NOT FLASH OR EXECUTE` → `TD-W03-07`.
- **Điều kiện nâng trạng thái:** chạy `py firmware/tools/cg_pzem_readback.py <capture> --expect-profile 50A` trên log **firmware W03** thật và ghi kết quả vào `pzem-register-readback.txt`; hoặc D chấp nhận capture gốc của TEST 131 (`TD-W03-05`).
- **Việc còn lại:** Member A chạy — **cấm** ghi register đổi profile trong W03.

### A-W03-05 — OFF electrical envelope (TEC OFF)

- **Canonical yêu cầu:** với TEC OFF vật lý, thu ≥10 phút mẫu PZEM; đo voltage, current noise/zero, power noise/zero, Modbus error rate.
- **Trạng thái:** `PARTIAL` — `MEASURED — BENCH ARTIFACT` (Arduino, có giới hạn) + `MEASUREMENT REQUIRED` (canonical ESP-IDF).
  - **Bổ sung 2026-10-27 (TEST 132B, Arduino bench):**
    - 600/600 hợp lệ, 0 lỗi; `V` min/max `11.94/11.95 V`, mean `11.9483 V`.
    - `I=0.00 A`, `P=0.0 W`, `E=0 Wh` ở mọi hàng — dưới độ phân giải hiển thị, **không** phải zero tuyệt đối.
    - Cửa sổ mẫu `10 ms → 599000 ms` = **598.99 s**, không phải 600.00 s; giây cuối không có mẫu → `TD-W03-04`.
    - Gate của log: **`RESULT: REVIEW REQUIRED`**.
  - TEC OFF trong phiên này là **`OPERATOR-REPORTED`**, không có kênh đo độc lập.
  - Đây **không** phải `pzem-off.csv` canonical: CSV trong bundle dùng schema bench (`elapsed_ms,valid,voltage_v,...`), không có `#CG PZEM_CFG`/`read_only=1`/`uptime_ms`.
  - Công cụ `cg_build_pzem_off_csv.py` vẫn từ chối window < 600 s, thiếu `--tec-off-confirmed`, trộn boot, tỉ lệ hợp lệ thấp.
- **Điều kiện nâng trạng thái:** file `pzem-off.csv` + summary sinh từ log **firmware W03** thật bằng công cụ trên, kèm xác nhận TEC OFF của vận hành; D chấp nhận cách tính cửa sổ (`TD-W03-04`) và chính sách canonical (`TD-W03-10`).
- **Việc còn lại:** Member A chạy; cần người vận hành xác nhận TEC OFF trong phiên đo.

### A-W03-06 — Shunt installation inspection

- **Canonical yêu cầu:** đúng đường dòng, đầu cốt chắc, không dùng dây tín hiệu trong đường dòng lớn, marking vật lý 50 A / 75 mV.
- **Trạng thái:** `PARTIAL` — `VERIFIED BY EXISTING EVIDENCE (ảnh W01)` cho marking + `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` cho continuity; chưa thử tải.
  - Có (ảnh W01 `04-pzem-shunt.jpg`, `18-shunt-marking-actual.jpg`): nhãn **in** `50A 75mV`; khắc `FL-2 0.5`; PZEM-017 ghi `RANGE: U DC 0—300V`; cổng RS-485 `5V/A/B/GND`.
  - **Bổ sung 2026-10-27 (số đọc DMM do người vận hành báo, không có log/ảnh màn hình):** `B−` ↔ `GND logic` ≈ `0 Ω`; `B−` ↔ `PSU−` ≈ `453 kΩ` khi tách shunt; `GND logic` ↔ `GND IBT-2` thông mạch sau khi nối lại; `VCC logic IBT-2` ↔ `GND logic` ≈ `24–25 kΩ` khi nguồn OFF; một lần PWM 10% ngắn thấy ≈ `0.98 A`.
  - **Failure mode mở:** `B−` common với GND logic ⇒ nếu shunt/đầu cốt hở, dòng hồi TEC có thể đi qua GND logic. Đây là **giả thuyết dựa trên continuity**, chưa xảy ra sự cố → `TD-W03-02`.
  - **Không** nhìn thấy trong bất kỳ ảnh nào: Kelvin sense, cỡ dây/đầu cốt, lực kẹp, nhiệt dưới tải. Chưa thử tải 50 A.
- **Điều kiện nâng trạng thái:** đo/kiểm tra topology return/star-ground khi nguồn OFF, ảnh cận cảnh mới + checklist; sau đó mới cấp tải qua shunt.
- **Việc còn lại:** Member A thao tác (nguồn OFF trước khi chạm).

### A-W03-07 — IBT-2 logic only

- **Canonical yêu cầu:** xác nhận nhãn chân module thật, enable, PWM input, reset/default state; **không** suy dòng liên tục từ giới hạn chip `43 A`.
- **Trạng thái:** `DONE` (logic-only safe state + static checks) + `OPERATOR-REPORTED` (TEST 133B) + `HARDWARE-LIMITED` (chưa có log cold-boot trên board).
  - Đã có (ảnh W01 `14-ibt2-actual.jpg`): module HW-039, BTS7960B ×2, SN74HC244; header `VCC R_IS R_EN RPWM` / `GND L_IS L_EN LPWM`; pin map ở `ibt2-pin-map.md`.
  - Firmware W03: **logic-only, default OFF** — ép `RPWM GPIO5` + `ENABLE GPIO6` về 0 ngay đầu `app_main`; không LEDC/MCPWM; không tồn tại lệnh ghi mức 1; guard `cg_actuator_outputs_allowed()` từ chối mọi output (`CG_ACTUATOR_ENABLE_ALLOWED=0`).
  - **Bổ sung 2026-10-27 (TEST 133B, operator-reported):** 6 cửa sổ × 20 mẫu = **120/120** hợp lệ, `0.00 A`, `0.0 W`; 5 lần `ESP.restart()` + cold boot thủ công vẫn OFF.
  - **Ba giới hạn phải giữ:** (a) dòng `RPWM: LOW / R_EN: LOW / L_EN: LOW` là **hằng chuỗi do sketch in**, không phải phép đo chân; (b) `SCOPE: AFTER FIRMWARE START ONLY` — không chứng minh trạng thái **trước** `setup()`; (c) cold boot chỉ là lời khai, không có bảng đếm/timestamp → `RAW_EVIDENCE_NOT_AVAILABLE`.
  - **Lệch cấu hình `GPIO10`:** W02 **cấu hình** `CG_PIN_DS18B20_DATA = GPIO10` (và đã đọc 4 ROM với cấu hình đó), còn lời khai as-built đặt `L_EN` trên `GPIO10`. Đây là **lệch cấu hình firmware ↔ lời khai dây**, không phải bằng chứng hai dây vật lý cùng ở GPIO10 — chưa có phép đo continuity. Map v2 xử lý ở mức cấu hình (DS18B20→GPIO33, L_EN=10) — `TD-W03-03`. **Nghiêm cấm cấp nguồn tải/TEC (energize)** cho tới khi có phép đo continuity và tie-off được kiểm chứng trên phần cứng.
  - Làm rõ giới hạn chip: `43 A` là **giới hạn chip BTS7960B**, không phải định mức liên tục của module — `ibt2-pin-map.md` §4.
- **Điều kiện nâng trạng thái:** đo continuity + kiểm chứng tie-off trên phần cứng; log cold-boot/reset default-OFF (`TD-W03-06`); PWM chỉ xét ở W04.
- **Việc còn lại:** Member A đo/log; lịch W04 thuộc kế hoạch.

---

## 2. Pass criteria canonical (`docs/05A §12`) — đối chiếu

| Tiêu chí canonical | W03 hiện tại |
|---|---|
| MAX3485 powered correctly | **`PARTIAL`** — thực tế TTL485-V2.0 5 V; bench Arduino 600/600; chưa chạy UART bằng firmware W03 và chưa đo mức logic (`CR-A-W01-01` change review mở) |
| PZEM stable enough to poll | **`PARTIAL`** — bench Arduino 600/600 hợp lệ nhưng không phải firmware W03; log tự gate `REVIEW REQUIRED` |
| 50 A range verified | **`PARTIAL`** — frame operator-reported tự nhất quán CRC, **không** có capture gốc; `PENDING_READBACK` cho ESP-IDF |
| OFF envelope measured | **`PARTIAL`** — bench 598.99 s / 600 mẫu (Arduino), gate `REVIEW REQUIRED`, TEC OFF operator-reported; canonical cần phiên ESP-IDF |
| IBT-2 can remain disabled/default OFF | **`DONE` phần code** (logic-only default OFF + guard + kiểm tra tĩnh); **`HARDWARE-LIMITED`** vì chưa có log cold-boot |
| Pin map nhất quán | **`DONE` ở mức cấu hình** — map v2 không còn gán trùng; continuity vật lý `GPIO10` **chưa đo** |

→ Kết luận kỹ thuật: các hạng mục code/tooling của W03 `DONE` trong phạm vi đã kiểm; phần
còn lại `PARTIAL`/`HARDWARE-LIMITED` vì chưa có kiểm chứng vật lý trên board.

## 3. Artifact canonical khai báo

| Artifact canonical (`docs/05A §12 Deliverables`) | Trạng thái | Lý do |
|---|---|---|
| `logic-power-measurement.md` | **CÓ** | Phần W01 (operator-reported) + kế hoạch đo; số đo W03 vẫn trống |
| `pzem-register-readback.txt` | **CÓ — `PENDING_READBACK`** | Có frame TEST 131 operator-reported + CRC host-side; **không** có capture gốc và **không** có log firmware W03 |
| `pzem-off.csv` | **MISSING** (khai báo) | Không có raw canonical từ firmware W03; CSV bench nằm trong `hardware-2026-10-27/raw/` và không được copy lên root (`TD-W03-10`) |
| `rs485-wiring.png` | **MISSING** (khai báo) | Không vẽ lại sơ đồ từ trí nhớ; sơ đồ thuộc change review `CR-A-W01-01` |
| `ibt2-pin-map.md` | **CÓ** | Pin map từ ảnh thật + hành vi default-OFF + lệch cấu hình `GPIO10` (continuity chưa đo) |

Lớp biên dịch: `DONE` — native ESP-IDF v6.1 (`esp32s3`), 1.090/1.090 bước Ninja,
0 warning/0 error. Bundle `build-native-windows-2026-10-27/` build từ commit `f8587dd`;
bundle `build-native-windows-2026-10-28/` build từ **working tree hiện tại** (gồm pin map v2,
safe-OFF 3 chân và comment IBT-2 đã sửa) — đây là nguồn sẽ được giao. CI GitHub Actions của
repo hiện `INFRASTRUCTURE-LIMITED` (billing) nên bằng chứng compile lấy từ hai bản native đó.

Bổ sung ngoài canonical: hai bundle bench được giữ nguyên trạng —
`hardware-2026-10-20/` (601/594/7, 7 frame lỗi, FC06 archive-only) và
`hardware-2026-10-27/` (TEST 131/132B/133B + shunt continuity + provenance matrix).
Không bundle nào thay đổi nhãn `MISSING`/`PENDING_READBACK` ở trên.

## 4. Phần còn lại — kiểm chứng vật lý, việc triển khai và giới hạn hạ tầng

Đây **không** phải cổng phê duyệt chéo thành viên. Mỗi mục là một phép đo/log chưa thực
hiện, một việc triển khai ngoài phạm vi W03, hoặc một hạn chế hạ tầng.

1. **Mức logic RS-485** — `MEASUREMENT REQUIRED`: module 5 V, cần xác nhận mức ở GPIO37
   ≤3.3 V trước khi đấu; đây là **hạn chế an toàn điện**, không phải phê duyệt.
2. **Pin map** — phần cấu hình `DONE` (`CG_PIN_MAP_VERSION=2`, guard `#error`); **continuity
   vật lý chưa đo** cho `GPIO10` (xem `ibt2-pin-map.md` §2.1) — `MEASUREMENT REQUIRED`.
3. **PZEM readback thật** — chạy firmware trên board, thu `#CG PZEM_CFG`/`#CG PZEM_RANGE`;
   nâng `pzem-register-readback.txt` khỏi `PENDING_READBACK` (không đổi profile bằng ghi).
4. **OFF envelope** — phiên canonical ≥600 s theo `cg_build_pzem_off_csv.py`
   — `MEASUREMENT REQUIRED`.
5. **XL4015** — đo lại có tải + ghi số trong `logic-power-measurement.md` (`TD-W03-09`).
6. **Shunt** — kiểm tra đường dòng/đầu cốt khi nguồn OFF; ảnh cận cảnh. **Không** tháo
   shunt đang có điện (hạn chế an toàn điện).
7. **IBT-2** — chạy log default-OFF trên board sau khi xác nhận tie-off LPWM (hạn chế an
   toàn điện: không cấp nguồn TEC cho tới khi có phép đo).
8. **Hardware change review** — lệch TTL485-V2.0 vs MAX3485 vẫn mở (`CR-A-W01-01`);
   `hardware_config_id` as-built chưa gán.
9. **Bench 2026-10-20** — 7 frame `INVALID` chưa rõ nguyên nhân (`TD-W03-11`); FC06 SET50
   là sai lệch quy trình cần mô tả trong hồ sơ (`TD-W03-07`).

## 5. Đầu vào bên ngoài còn thiếu

Xem `team-dependencies.md` — bảng `TD-W03-01…11` liệt kê từng mục còn thiếu, ai/việc gì
cung cấp, và việc gì được mở khóa. Các mục đó là **điều kiện dữ liệu/phép đo**, không
phải điều kiện phê duyệt để công nhận phần Member A đã kiểm chứng.
