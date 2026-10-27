# W03 acceptance matrix — Member A

**Trạng thái hồ sơ: `MEMBER A W03 EVIDENCE — DELIVERED FOR REVIEW`**
**Cổng nghiệm thu nhóm: `W03 TEAM GATE: PENDING_REVIEW` — kỹ thuật vẫn `W03 NOT PASS`.**
File này là **nguồn trạng thái duy nhất** của W03; `README.md` chỉ tóm tắt. Script
`validate_w03.py` kiểm tra các nhãn trong file này, nhưng **không** đọc hiểu văn xuôi và
**không** xác nhận bất kỳ sự thật vật lý nào.

Bộ hồ sơ được đẩy lên PR để **review**, không phải để tuyên bố W03 đạt. Việc mở/merge PR
không thay phê duyệt của Member D/leader và không nâng bất kỳ mục nào dưới đây.

**Quy ước nhãn trạng thái dùng trong W03:**

| Nhãn | Nghĩa |
|---|---|
| `VERIFIED BY EXISTING EVIDENCE` | Có bằng chứng thật từ trước (W01/W02) nhưng **không** do phiên W03 này đo lại; chỉ dùng trong phạm vi bằng chứng đó |
| `CODE IMPLEMENTED / HARDWARE RUN PENDING` | Code đã có trong repo + đã test tự động/kiểm tra tĩnh; **chưa** nạp/chạy trên phần cứng |
| `MEASURED — BENCH ARTIFACT` | Có file gốc trong repo, hash được pin, đọc lại được bằng script; **vẫn** có thể không phải firmware W03 |
| `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` | Chỉ có lời khai/số đọc của người vận hành; không có file gốc để tái kiểm |
| `MEASUREMENT REQUIRED` | Phải có người vận hành đo/log thật mới được nâng trạng thái |
| `SAFETY REVIEW PENDING` | Phải được Member D (và leader khi lệch freeze) duyệt trước khi cấp nguồn/thao tác |
| `LEADER APPROVAL PENDING` | Cần leader quyết định (lệch freeze, phạm vi, lịch) |
| `PENDING_READBACK` | Cần một lần đọc thật từ module (PZEM) bằng firmware W03 |
| `RAW_EVIDENCE_NOT_AVAILABLE` | Không có file capture gốc; hồ sơ không dựng lại log/ảnh/hex |

---

## 1. Acceptance matrix A-W03-01 … A-W03-07

### A-W03-01 — XL4015 logic supply (~5 V)

- **Canonical yêu cầu:** set output logic, đo bằng đồng hồ, ghi giá trị no-load/load nếu thực tế. Target ~5 V trong giới hạn module.
- **Trạng thái:** `VERIFIED BY EXISTING EVIDENCE (W01 operator-reported, no-load) + MEASUREMENT REQUIRED`.
  - Có: W01 ghi XL4015 `5.00 V` (không tải), TB4506 `4.99 V`; fuse 5 A cho XL4015 (W01 `bom-audit.csv` HW-13/HW-16).
  - Thiếu: đo có tải, ripple, nhiệt, dòng logic tổng; chưa có phép đo nào trong phiên W03.
- **Bổ sung 2026-10-27:** phiên bench mới **không** đo lại rail logic; chỉ đo điện áp nhánh TEC qua PZEM (`11.94–11.95 V`, xem A-W03-05). Không suy rail 5 V từ số đó.
- **Điều kiện nâng trạng thái:** phiên đo W03 với đúng trình tự trong `logic-power-measurement.md` §3, ghi số vào file đó; có D khi cấp nguồn cho tải → `TD-W03-09`.
- **Người quyết định còn lại:** Member A (đo) + D (chứng kiến/duyệt tải).

### A-W03-02 — MAX3485 / RS-485

- **Canonical yêu cầu:** module VCC = 3.3 V; map `DI/RO/DE//RE/A/B`; dùng UART/RS-485 mode hoặc điều khiển hướng tường minh.
- **Thực tế phần cứng (đọc từ ảnh W01 `02-rs485-front.jpg`, `03-rs485-back.jpg`):** module là **TTL485-V2.0**, rail 5 V, **auto-direction, không có chân DE//RE**; đầu tín hiệu chỉ `GND/RXD/TXD/VCC`; cầu A/B/GND; điện trở 120 Ω có jumper. **Không phải** MAX3485 đã freeze (W01 `freeze-deviation-review.md` CR-A-W01-01, đang PENDING).
- **Mức logic:** theo báo cáo W01 — TXD idle 5 V, phân áp tạm 10k/10k/10k → ~3.314 V tại GPIO37 (tính ≈ 3.33 V); **agent không đo lại**. Không được đấu 5 V trực tiếp vào GPIO; **không được giả định RO là 3.3 V**.
- **Trạng thái:** `SAFETY REVIEW PENDING — Member D + leader (CR-A-W01-01)`.
  - **Bổ sung 2026-10-27:** sketch Arduino bench đã trao đổi được **600/600** phản hồi ở `9600 8N1`, slave `0x01`, qua đúng module as-built. Điều này chứng minh **đường UART bench hoạt động ở cấu hình đã dùng**, không chứng minh mức logic an toàn và **không** phải firmware ESP-IDF W03.
  - Không bài UART nào dùng firmware W03 được chạy (cố ý).
- **Điều kiện nâng trạng thái:** D + leader chấp nhận (a) module TTL485-V2.0 với phân áp, hoặc (b) mua module 3.3 V đúng freeze (`TD-W03-01`); sau đó mới loopback/log UART thật bằng firmware W03.
- **Người quyết định còn lại:** D + leader.

### A-W03-03 — PZEM communication

- **Canonical yêu cầu:** kiểm tra nguồn phía module, slave address, Modbus CRC, framing thật; nếu 8N1 fail thì rà revision tài liệu trước khi kết luận lỗi phần cứng.
- **Trạng thái:** `CODE IMPLEMENTED / HARDWARE RUN PENDING` + `MEASUREMENT REQUIRED`.
  - Đã implement + test tự động: CRC16/MODBUS (init 0xFFFF, poly 0xA001), khung đọc FC 0x04 (input 0x0000..0x0005) và FC 0x03 (holding 0x0003), timeout 250 ms/2 attempts/poll 1 Hz, phân loại `OK/TIMEOUT/CRC_ERR/BAD_SLAVE/BAD_FUNCTION/BAD_LENGTH/EXCEPTION/UART_ERR`, `uptime_ms` thật từ `esp_timer`, scaling V/A/W/Wh theo LSB canonical, `nan` khi lỗi (không giữ giá trị cũ).
  - Framing: mặc định **8N1** cấu hình bằng macro; **không** tự giả định 8N2.
  - Thiếu: log `#CG PZEM_CFG` + `#CG PZEM` từ **firmware W03** trên board.
  - **Bổ sung 2026-10-27 (Arduino bench, KHÔNG phải ESP-IDF):** TEST 132B — **600 hàng, 600 hợp lệ, 0 lỗi**, `rx_len=29` mọi hàng, `SUCCESS_RATE 100.00 %`. Đây là `MEASURED — BENCH ARTIFACT` cho **sketch bench**, không phải `#CG PZEM_*` của W03. Log tự kết luận **`RESULT: REVIEW REQUIRED`**, không phải PASS.
  - Archive 2026-10-20 (601 mẫu / 594 hợp lệ / 7 lỗi) vẫn là provenance của lỗi cũ; phiên mới **không** chứng minh nguyên nhân đã được sửa.
- **Điều kiện nâng trạng thái:** log `#CG PZEM_CFG` + ≥1 chu kỳ `#CG PZEM` OK từ firmware trên board, đối chiếu `cg_pzem_readback.py`/`cg_build_pzem_off_csv.py`.
- **Người quyết định còn lại:** Member A (chạy) sau khi A-W03-02 được duyệt an toàn.

### A-W03-04 — 50 A profile

- **Canonical yêu cầu:** đọc/đặt current-range register; bằng chứng phải cho thấy `0x0001` hoặc cấu hình 50 A tương đương.
- **Trạng thái:** `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` + `PENDING_READBACK` (ESP-IDF) + `CODE IMPLEMENTED / HARDWARE RUN PENDING`.
  - Đã implement: **chỉ đọc** holding 0x0003 (FC 0x03) — không có builder ghi register trong firmware lẫn công cụ host; profile 50 A ứng với raw `0x0001`; tool `cg_pzem_readback.py` tái giải mã CRC/value/profile từ hex thật.
  - **Bổ sung 2026-10-27 (TEST 131):** người vận hành báo frame `01 03 02 00 01 79 84`. CRC16/MODBUS tính lại host-side = `0x8479` → on-wire `79 84` **khớp**; `0x0001` = 50 A theo `docs/01 §9.3`. Frame **tự nhất quán**.
  - **Giới hạn:** `RAW_EVIDENCE_NOT_AVAILABLE` — không có file log/capture gốc cho TEST 131; không có tx/rx của lần đọc trong file. Hai phản hồi lỗi đầu tiên không có byte để phân tích. Vì vậy **không** được gọi là evidence-grade readback, và A-W03-04 **không** được nâng thành verified.
  - Không suy profile từ nhãn shunt `50A 75mV`.
  - Archive 2026-10-20 (`FC06 SET50`) là hành vi ngoài hợp đồng read-only, `ARCHIVE ONLY — DO NOT FLASH OR EXECUTE` → `TD-W03-07`.
- **Điều kiện nâng trạng thái:** chạy `py firmware/tools/cg_pzem_readback.py <capture> --expect-profile 50A` trên log **firmware W03** thật và ghi kết quả vào `pzem-register-readback.txt`; hoặc D chấp nhận capture gốc của TEST 131 (`TD-W03-05`).
- **Người quyết định còn lại:** Member A (chạy) — **cấm** ghi register đổi profile trong W03.

### A-W03-05 — OFF electrical envelope (TEC OFF)

- **Canonical yêu cầu:** với TEC OFF vật lý, thu ≥10 phút mẫu PZEM; đo voltage, current noise/zero, power noise/zero, Modbus error rate.
- **Trạng thái:** `MEASUREMENT REQUIRED` (canonical ESP-IDF) + `MEASURED — BENCH ARTIFACT` (Arduino, có giới hạn).
  - **Bổ sung 2026-10-27 (TEST 132B, Arduino bench):**
    - 600/600 hợp lệ, 0 lỗi; `V` min/max `11.94/11.95 V`, mean `11.9483 V`.
    - `I=0.00 A`, `P=0.0 W`, `E=0 Wh` ở mọi hàng — dưới độ phân giải hiển thị, **không** phải zero tuyệt đối.
    - Cửa sổ mẫu `10 ms → 599000 ms` = **598.99 s**, không phải 600.00 s; giây cuối không có mẫu → `TD-W03-04`.
    - Gate của log: **`RESULT: REVIEW REQUIRED`**.
  - TEC OFF trong phiên này là **`OPERATOR-REPORTED`**, không có kênh đo độc lập.
  - Đây **không** phải `pzem-off.csv` canonical: CSV trong bundle dùng schema bench (`elapsed_ms,valid,voltage_v,...`), không có `#CG PZEM_CFG`/`read_only=1`/`uptime_ms`.
  - Công cụ `cg_build_pzem_off_csv.py` vẫn từ chối window < 600 s, thiếu `--tec-off-confirmed`, trộn boot, tỉ lệ hợp lệ thấp.
- **Điều kiện nâng trạng thái:** file `pzem-off.csv` + summary sinh từ log **firmware W03** thật bằng công cụ trên, kèm xác nhận TEC OFF của vận hành; D chấp nhận cách tính cửa sổ (`TD-W03-04`) và chính sách canonical (`TD-W03-10`).
- **Người quyết định còn lại:** Member A (chạy) + D (chứng kiến OFF envelope theo handoff `docs/05A §12`).

### A-W03-06 — Shunt installation inspection

- **Canonical yêu cầu:** đúng đường dòng, đầu cốt chắc, không dùng dây tín hiệu trong đường dòng lớn, marking vật lý 50 A / 75 mV.
- **Trạng thái:** `VERIFIED BY EXISTING EVIDENCE (ảnh W01)` cho marking + `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` cho continuity + `SAFETY REVIEW PENDING (D)`.
  - Có (ảnh W01 `04-pzem-shunt.jpg`, `18-shunt-marking-actual.jpg`): nhãn **in** `50A 75mV`; khắc `FL-2 0.5`; PZEM-017 ghi `RANGE: U DC 0—300V`; cổng RS-485 `5V/A/B/GND`.
  - **Bổ sung 2026-10-27 (số đọc DMM do người vận hành báo, không có log/ảnh màn hình):** `B−` ↔ `GND logic` ≈ `0 Ω`; `B−` ↔ `PSU−` ≈ `453 kΩ` khi tách shunt; `GND logic` ↔ `GND IBT-2` thông mạch sau khi nối lại; `VCC logic IBT-2` ↔ `GND logic` ≈ `24–25 kΩ` khi nguồn OFF; một lần PWM 10% ngắn thấy ≈ `0.98 A`.
  - **Failure mode mở:** `B−` common với GND logic ⇒ nếu shunt/đầu cốt hở, dòng hồi TEC có thể đi qua GND logic. Đây là **giả thuyết dựa trên continuity**, chưa xảy ra sự cố → `TD-W03-02`.
  - **Không** nhìn thấy trong bất kỳ ảnh nào: Kelvin sense, cỡ dây/đầu cốt, lực kẹp, nhiệt dưới tải. Chưa thử tải 50 A.
- **Điều kiện nâng trạng thái:** D duyệt topology return/star-ground; phiên kiểm tra có D (nguồn OFF trước khi chạm), ảnh cận cảnh mới + checklist; sau đó mới cấp tải qua shunt.
- **Người quyết định còn lại:** D (an toàn) + Member A (thao tác).

### A-W03-07 — IBT-2 logic only

- **Canonical yêu cầu:** xác nhận nhãn chân module thật, enable, PWM input, reset/default state; **không** suy dòng liên tục từ giới hạn chip `43 A`.
- **Trạng thái:** `CODE IMPLEMENTED / HARDWARE RUN PENDING` + `OPERATOR-REPORTED` (TEST 133B) + `SAFETY REVIEW PENDING (D)`.
  - Đã có (ảnh W01 `14-ibt2-actual.jpg`): module HW-039, BTS7960B ×2, SN74HC244; header `VCC R_IS R_EN RPWM` / `GND L_IS L_EN LPWM`; pin map ở `ibt2-pin-map.md`.
  - Firmware W03: **logic-only, default OFF** — ép `RPWM GPIO5` + `ENABLE GPIO6` về 0 ngay đầu `app_main`; không LEDC/MCPWM; không tồn tại lệnh ghi mức 1; guard `cg_actuator_outputs_allowed()` từ chối mọi output (`CG_ACTUATOR_ENABLE_ALLOWED=0`).
  - **Bổ sung 2026-10-27 (TEST 133B, operator-reported):** 6 cửa sổ × 20 mẫu = **120/120** hợp lệ, `0.00 A`, `0.0 W`; 5 lần `ESP.restart()` + cold boot thủ công vẫn OFF.
  - **Ba giới hạn phải giữ:** (a) dòng `RPWM: LOW / R_EN: LOW / L_EN: LOW` là **hằng chuỗi do sketch in**, không phải phép đo chân; (b) `SCOPE: AFTER FIRMWARE START ONLY` — không chứng minh trạng thái **trước** `setup()`; (c) cold boot chỉ là lời khai, không có bảng đếm/timestamp → `RAW_EVIDENCE_NOT_AVAILABLE`.
  - **Xung đột pin (BLOCKER):** as-built báo `L_EN → GPIO10`, nhưng W02 dùng `GPIO10` cho `CG_PIN_DS18B20_DATA`. Không thể cùng một chân → `TD-W03-03`. **Nghiêm cấm cấp nguồn tải/TEC (energize)** khi xung đột này chưa được giải quyết.
  - Trả lời câu hỏi leader: `43 A` là **giới hạn chip BTS7960B**, không phải định mức liên tục của module — `ibt2-pin-map.md` §4.
- **Điều kiện nâng trạng thái:** D duyệt pin map không xung đột + tie-off; log cold-boot/reset default-OFF theo phương pháp D duyệt (`TD-W03-06`); chỉ sau đó mới xét PWM ở W04.
- **Người quyết định còn lại:** D (safety) + leader (pin map, lịch W04).

---

## 2. Pass criteria canonical (`docs/05A §12`) — đối chiếu

| Tiêu chí canonical | W03 hiện tại |
|---|---|
| MAX3485 powered correctly | **KHÔNG ĐẠT** — thực tế TTL485-V2.0 5 V; chưa được D/leader duyệt mức logic (CR-A-W01-01); chưa có phiên UART firmware W03 |
| PZEM stable enough to poll | **CHƯA CHỨNG MINH cho W03** — bench Arduino 600/600 hợp lệ, nhưng không phải firmware W03; log tự gate `REVIEW REQUIRED` |
| 50 A range verified | **CHƯA** — có frame operator-reported tự nhất quán CRC, **không** có capture gốc; `PENDING_READBACK` cho ESP-IDF |
| OFF envelope measured | **CHƯA cho canonical** — bench 598.99 s / 600 mẫu, gate `REVIEW REQUIRED`, TEC OFF operator-reported |
| IBT-2 can remain disabled/default OFF | **PHẦN CODE: CÓ** (logic-only default OFF + guard + kiểm tra tĩnh); **PHẦN PHẦN CỨNG / D: PENDING**; quan sát 120/120 chỉ sau khi firmware chạy |
| Pin map nhất quán | **KHÔNG** — `GPIO10` vừa là `L_EN` (as-built) vừa là DS18B20 DATA (W02) → `TD-W03-03` |

→ Kết luận kỹ thuật: **W03 NOT PASS**. Hồ sơ đã được đẩy để review
(`MEMBER A W03 EVIDENCE — DELIVERED FOR REVIEW`), cổng nhóm vẫn `PENDING_REVIEW`.

## 3. Artifact canonical khai báo

| Artifact canonical (`docs/05A §12 Deliverables`) | Trạng thái | Lý do |
|---|---|---|
| `logic-power-measurement.md` | **CÓ** | Phần W01 (operator-reported) + kế hoạch đo; số đo W03 vẫn trống |
| `pzem-register-readback.txt` | **CÓ — `PENDING_READBACK`** | Có frame TEST 131 operator-reported + CRC host-side; **không** có capture gốc và **không** có log firmware W03 |
| `pzem-off.csv` | **MISSING** (khai báo) | Không có raw canonical từ firmware W03; CSV bench nằm trong `hardware-2026-10-27/raw/` và không được copy lên root (`TD-W03-10`) |
| `rs485-wiring.png` | **MISSING** (khai báo) | Không vẽ lại sơ đồ từ trí nhớ; sơ đồ chính thức thuộc buổi D duyệt CR-A-W01-01 |
| `ibt2-pin-map.md` | **CÓ** | Pin map từ ảnh thật + hành vi default-OFF + xung đột `GPIO10` + việc chờ D |

Bổ sung ngoài canonical: hai bundle bench được giữ nguyên trạng —
`hardware-2026-10-20/` (601/594/7, 7 frame lỗi, FC06 archive-only) và
`hardware-2026-10-27/` (TEST 131/132B/133B + shunt continuity + provenance matrix).
Không bundle nào thay đổi nhãn `MISSING`/`PENDING_READBACK` ở trên.

## 4. Blocker và điều kiện chuyển trạng thái (điều kiện để W03 PASS)

1. **Mức logic RS-485** — `TD-W03-01` (D + leader). Chặn mọi bài UART firmware W03.
2. **Pin map** — `TD-W03-03`: chốt `GPIO10` (L_EN hay DS18B20 DATA) trước khi freeze.
3. **PZEM readback thật** — chạy firmware trên board, thu `#CG PZEM_CFG`/`#CG PZEM_RANGE`; nâng `pzem-register-readback.txt` khỏi PENDING (không đổi profile bằng ghi).
4. **OFF envelope** — phiên canonical ≥600 s theo `cg_build_pzem_off_csv.py`; D chấp nhận cách tính cửa sổ (`TD-W03-04`) và chính sách canonical (`TD-W03-10`).
5. **XL4015** — đo lại có tải + ghi số trong `logic-power-measurement.md` (`TD-W03-09`).
6. **Shunt** — D duyệt topology return/failure mode (`TD-W03-02`); kiểm tra đường dòng/đầu cốt khi nguồn OFF; ảnh cận cảnh.
7. **IBT-2** — D duyệt tie-off + phương pháp log cold-boot (`TD-W03-06`); chạy log default-OFF.
8. **Leader** — chấp nhận lệch TTL485 (hardware change review), gán `hardware_config_id` (`TD-W03-08`).
9. **Bench 2026-10-20** — 7 frame `INVALID` chưa rõ nguyên nhân (`TD-W03-11`); FC06 SET50 là sai lệch quy trình cần xử lý (`TD-W03-07`).

## 5. Quyết định cần D / leader (không tự quyết trong W03)

Xem `team-dependencies.md` — bảng `TD-W03-01…11` là nguồn duy nhất, gồm cả trạng thái và
việc được mở khóa. Không mục nào trong file này được coi là đã chốt.
