# 06. TEC commissioning — ranh giới an toàn, giới hạn dẫn xuất và kế hoạch bench G0–G5

**Trạng thái hiện tại:**

```text
W04 FOUNDATION DELIVERED — PRODUCTION TEC OUTPUT STAGE COMPILED OUT AND NOT AUTHORIZED
H6 BENCH ENERGIZATION EXECUTED UNDER OPERATOR SUPERVISION (2026-10-29, PWM 10 %, 60 s, 0.97 A)
```

**Phạm vi:** W04 (Member A). Đây là tài liệu làm việc do Member A soạn cho giai
đoạn commissioning TEC: nó ghi phần cứng nào **đã** được xác nhận, phần nào
**chưa**, firmware fail-closed được xây dựng thế nào, giới hạn vận hành đến từ
đâu, dữ liệu thô được thu thập ra sao, và người vận hành chỉ được đi tiếp qua
cổng nào với bằng chứng nào.

**Đây KHÔNG phải tài liệu canonical và KHÔNG phải hợp đồng.** Chuỗi thẩm quyền
của dự án là `docs/00 > docs/01 > docs/02 > docs/03 > docs/04 > docs/05A`, và
toàn bộ cổng G0–G5, bảng giới hạn cùng các tiền đề trong tệp này đứng dưới chuỗi
đó. Hễ mâu thuẫn với bất kỳ tệp canonical nào, tệp canonical thắng và khác biệt
phải được ghi thành mục mở trong `evidence/A/W04/acceptance.md`, không được sửa
ngầm ngay trong tệp này.

**Tệp này không nhân danh ai cấp nguồn cho bất kỳ thao tác vật lý nào.** Quyền
cấp nguồn thuộc người vận hành, quyết định theo từng phiên. Một lần cấp nguồn có
giám sát đã xảy ra ở phiên H6 2026-10-29 bằng ảnh bench riêng (không phải output
stage của firmware này) và có log trong `evidence/A/W04/h6/`; trước đó
`evidence/A/as-built-pinmap-2026-10-27.md` đã ghi một quan sát PWM 10 % cỡ 0.98 A
dạng *user reported*. Output stage của firmware production vẫn bị tắt khi biên
dịch và chưa được ủy quyền.

---

## 0. Vì sao phải fail-closed

TEC là tải công suất lớn, không có “thử nhanh cho biết”. Một chế độ lỗi điển
hình không phải “TEC không lạnh” mà là:

- cả hai nửa cầu dẫn cùng lúc → dòng xuyên (shoot-through);
- kênh lạnh bị đảo cực → sưởi thay vì làm lạnh;
- mất cảm biến hot-side → điều khiển mù, nhiệt tích tụ;
- PWM còn chạy trong khi enable đã tắt → trạng thái “tưởng OFF nhưng vẫn có
  năng lượng”;
- lỗi phần mềm sau reset → tự chạy lại lệnh cũ khi không có người.

Vì vậy mọi đường dẫn trong W04 kết thúc ở **OFF**, không phải “thử lại”.

---

## 1. Sự thật phần cứng: đã xác nhận / chưa xác minh

Nhãn bằng chứng giữ nguyên như `evidence/A/as-built-pinmap-2026-10-27.md` §0:
`MEASURED`, `SOURCE VERIFIED`, `USER REPORTED`, `NOT VERIFIED`.

### 1.1 Đã xác nhận (dùng được để thiết kế)

| Hạng mục | Giá trị | Lớp | Nguồn |
|---|---|---|---|
| Board / MCU / flash | MAKDRIVERONE, ESP32-S3R2, W25Q32 | `SOURCE VERIFIED` | pinmap §1 |
| DS18B20 DATA | GPIO33, đọc 4 ROM | `MEASURED` | pinmap §2 (TEST 129D) |
| RS-485 TX/RX | GPIO36/37, Modbus trả lời hợp lệ | `MEASURED` | pinmap §2, §6 |
| Nhánh TEC khi OFF | 11.94–11.95 V | `MEASURED` | pinmap §5 (TEST 132B) |
| Shunt | 50 A / 75 mV, khắc `FL-2 0.5` | `SOURCE VERIFIED` | pinmap §5 (ảnh 18/04) |
| IBT-2 RPWM / R_EN / L_EN | GPIO5 / GPIO6 / GPIO10 | `USER REPORTED` | pinmap §2 |
| IBT-2 LPWM | nối GND trên module | `USER REPORTED` | pinmap §2 |
| Shunt ở đường hồi `B−` → `PSU−` | vị trí hiện tại | `USER REPORTED` | pinmap §5 |

### 1.2 Chưa xác minh — đây là các cổng vật lý còn lại

| # | Hạng mục | Vì sao chưa đủ | Cổng đóng |
|---|---|---|---|
| U1 | Continuity GPIO → header module (5/6/10, 33, 36/37) | chưa đo thông mạch, chỉ có lời khai | G0 |
| U2 | Đường hồi shunt và quan hệ `B−` ↔ GND logic | chưa đo; nếu TEC current chạy qua GND logic là rủi ro | G0 |
| U3 | Cách ly nhánh TEC khỏi USB/logic khi test | chưa có quy trình đo | G0 |
| U4 | Mức logic 3.3 V ESP32 → input IBT-2 (module có buffer? SN74HC244?) | chưa rõ topology input của module | G0/G1 |
| U5 | Pull-down / trạng thái OFF vật lý của RPWM, R_EN, L_EN khi boot | mới chứng minh ở mức firmware + tĩnh | G1 |
| U6 | Interlock phần cứng | **chưa tồn tại**; firmware trả `read_interlock()=false` | G0/G1 (thiết kế + đấu dây mới) |
| U7 | Model TEC chính xác và datasheet tin cậy | chỉ có tên thương mại TEC1-12715; docs/01 §13.2 cấm suy ra Imax/Vmax/Qmax | G3 |
| U8 | Khả năng dòng của PSU, bảo vệ nhánh, cầu chì cuối | docs/01 §16: cầu chì cuối là kết quả commissioning | G0/G3 |
| U9 | Heatsink + fan: khả năng tản nhiệt thực | chưa đo | G2/G4 |
| U10 | Đo nhiệt hot-side tin cậy | chưa gán probe, chưa kiểm tra tiếp xúc | G2 |
| U11 | Lắp đặt đúng mặt lạnh/mặt nóng, keo tản nhiệt | chưa commissioning | G4 |
| U12 | Cổng console UART0 xuất hiện trên USB CH343G | chưa xác nhận trên board thật | G1 |

**Không có mục nào trong bảng 1.2 được phép “coi như đã xong”.** Firmware được
giao trong W04 vì thế giữ `CG_TEC_OUTPUT_STAGE_ENABLED = 0`.

---

## 2. Bất biến an toàn và cách firmware thực thi

| Bất biến | Nội dung | Thực thi trong W04 |
|---|---|---|
| PHY-ACT-001 | Boot/reset ⇒ output OFF | Output stage compile-disabled; adapter từ chối mọi lệnh bật; không nguồn nào ghi mức 1 lên RPWM/R_EN/L_EN |
| PHY-ACT-002 | PWM không ngầm bật output; enable là tín hiệu riêng | Thứ tự START: duty 0 → fan → `enables(R_EN=1, L_EN=0)` → duty; STOP: enables off trước, rồi duty 0 |
| PHY-ACT-003 | Không bao giờ đảo cực | `set_enables(true, false)` là API duy nhất; adapter từ chối `len=true`; LPWM vật lý GND |
| PHY-ACT-004 | Thermal shutdown không phải chế độ vận hành hợp lệ | OVERTEMP latch, không auto-resume |
| PHY-TEC-001 | Hot side phải tản cả `Qc + Pin` | Start yêu cầu kênh hot-side hợp lệ; hiện `NOT_ASSIGNED` ⇒ từ chối start |
| PHY-FUSE-001 | Không test có nguồn nào bỏ qua cầu chì nhánh | G0/G3 bắt buộc cầu chì đúng vị trí; cấm bypass là quy định của PHY-FUSE-001 (docs/01), không phải do tệp này đặt ra |

Bảng “đường dẫn lỗi → trạng thái cuối”:

| Sự kiện | Kết quả bắt buộc | Cơ chế |
|---|---|---|
| Boot / reset / power cycle | OFF, không tự ARM | `cg_tec_control_init` + token mới mỗi boot |
| Quá thời hạn ARM (120 s) | OFF | `arm_ttl_ms` |
| START khi chưa ARM / sai token | Từ chối, OFF | `cg_tec_arm` / gate thứ tự |
| START khi thiếu/già/mâu thuẫn cảm biến | Từ chối, OFF | `inputs_problem()` |
| START khi giới hạn chưa RESOLVED | Từ chối, OFF | `cg_tec_limits_all_resolved()` |
| START khi stage/interlock/fan không sẵn sàng | Từ chối, OFF | gate stage/interlock/fan |
| Lệnh phần cứng thất bại giữa chừng | Rollback + FAULT_LATCH | rollback từng bước |
| Vượt thời lượng đã đặt | COOLDOWN (fan còn chạy) → OFF | `cooling_deadline_ms` mỗi tick |
| Tick trễ > 1000 ms khi đang COOLING | FAULT_LATCH | heartbeat gap |
| Đồng hồ lùi | FAULT_LATCH | `now_ms < last_tick_ms` |
| Quá dòng / quá áp / thấp áp / quá nhiệt | FAULT_LATCH | ngưỡng lấy từ bảng giới hạn |
| ESTOP | OFF ngay + FAULT_LATCH | `cg_tec_estop` |
| Lệnh cloud | Không tồn tại | mã ứng dụng không gọi API mạng nào (Wi-Fi/HTTP/MQTT); đường vào duy nhất là console UART địa phương |

---

## 3. Kiến trúc firmware W04

### 3.1 Module

| Tệp | Vai trò |
|---|---|
| `firmware/main/cg_tec_control.c/.h` | Lõi state machine thuần C, thời gian/phần cứng/cảm biến được inject |
| `firmware/main/cg_tec_limits.c/.h` | Bảng giới hạn vận hành dạng dữ liệu + provenance |
| `firmware/main/cg_tec_platform.h` | Hợp đồng `cg_tec_hw_ops_t` (enables, duty, fan, interlock, availability) |
| `firmware/main/cg_tec_hw.c` | Adapter as-built: từ chối mọi yêu cầu cấp nguồn, luôn `force_off` |
| `firmware/main/cg_tec_command.c/.h` | Parser lệnh console nghiêm ngặt |
| `firmware/main/cg_snapshot.c/.h` | Ảnh chụp cảm biến/power/door có khóa, có mốc thời gian |
| `firmware/main/cg_telemetry.c/.h` | Dòng `#CG TELEM schema=N` (1 ở W04, 2 từ W05), một lần/giây |
| `firmware/main/cg_console.c/.h` | UART0 115200, hàng đợi lệnh |
| `firmware/main/cg_commission.c/.h` | Task 100 ms, token boot, log, telemetry, watchdog |

Lõi điều khiển **không** phụ thuộc ESP-IDF/FreeRTOS, nên cùng một mã chạy được
trong harness host (`firmware/tools/tests/cg_tec_harness.c`).

### 3.2 State machine

```text
OFF --ARM(token)--> ARMED --START--> COOLING --STOP/hết giờ--> COOLDOWN --> OFF
                                        \--lỗi--> FAULT_LATCH --CLEAR(token, đầu vào khỏe)--> COOLDOWN
```

| Trạng thái | Ý nghĩa | Có thể cấp nguồn? |
|---|---|---|
| `OFF` | An toàn, không ARM | Không |
| `ARMED` | Đã ủy quyền một lần, TTL 120 s, chưa chạy | Không |
| `COOLING` | Một run có thời hạn đang chạy | Chỉ khi mọi gate đã qua (hiện không thể) |
| `COOLDOWN` | Output OFF, fan còn chạy 60 s | Không |
| `FAULT_LATCH` | Lỗi đã chốt, output OFF | Không |

### 3.3 Thứ tự đóng / ngắt

```text
START: set_cooling_duty(0) -> set_fan(true) -> set_enables(R_EN=true, L_EN=false) -> set_cooling_duty(duty)
STOP : set_enables(false, false) -> set_cooling_duty(0)          (fan giữ nguyên trong COOLDOWN)
ESTOP: enables off -> duty 0 -> fan on -> latch
```

Mỗi bước thất bại đều rollback toàn bộ và chốt `HW_REJECTED`.

### 3.4 Fault latch

Các bit lỗi: `UNAUTHORIZED`, `LIMITS_UNRESOLVED`, `STAGE_UNAVAILABLE`,
`SENSOR_INVALID`, `SENSOR_STALE`, `OVERCURRENT`, `OVERVOLTAGE`, `UNDERVOLTAGE`,
`OVERTEMP`, `INTERLOCK_OPEN`, `FAN_UNAVAILABLE`, `HEARTBEAT`, `HW_REJECTED`,
`ESTOP`.

- Latch chỉ xóa bằng `CLEAR <token>` **và** đầu vào phải khỏe lại; CLEAR không
  ARM run kế tiếp.
- Latch luôn kéo theo `safe_stop_outputs`; nếu fan còn điều khiển được thì giữ
  fan chạy để bảo vệ hot side.

### 3.5 Ủy quyền vận hành

- Mỗi boot sinh token 8 hex từ `esp_random()`, in một lần:
  `#CG AUTH token=<8hex> ttl_ms=120000 clear_requires_token=1`.
- `ARM` và `CLEAR` đòi đúng token của boot hiện tại.
- Một ARM chỉ ủy quyền **một** run; START thành công tiêu thụ ARM.
- Mã nguồn và header ứng dụng không gọi API mạng nào (Wi-Fi/HTTP/MQTT/lwIP/TLS/
  socket) — mục 8 của `cg_check_firmware_w04.py` kiểm tra bất biến này trên chính
  cây giao hàng. Thành phần mặc định của ESP-IDF vẫn xuất hiện trên dòng link,
  nhưng link map của ảnh build không nằm trong PR này nên tệp này không tuyên bố
  gì về số object mà mỗi archive đóng góp. Phạm vi tuyên bố vì thế chỉ là mã ứng
  dụng: firmware này không tự mở đường lệnh từ xa nào; việc các archive mặc định
  có sót object mạng vào ảnh hay không là câu hỏi mở, không phải bằng chứng ở đây.

### 3.6 Giới hạn là dữ liệu, không phải hằng số rải rác

`cg_tec_limits.c` chứa bảng có `state` (`UNRESOLVED`/`RESOLVED`) và `source`
(provenance). START từ chối nếu **bất kỳ** mục nào `UNRESOLVED`. Muốn đổi một
giới hạn phải sửa bảng + nguồn + bằng chứng + review; không có `#define` rời để
ai đó “chỉnh nhanh”.

---

## 4. Bảng giới hạn vận hành (trạng thái giao hàng)

| ID | Giới hạn | Đơn vị | Trạng thái | Nguồn / lý do chưa có |
|---|---|---|---|---|
| `CURRENT_MAX_A` | Dòng nhánh TEC tối đa | A | `UNRESOLVED` | `TEC_CONTINUOUS_RATING_NOT_ESTABLISHED` |
| `VOLTAGE_MAX_V` | Điện áp nhánh tối đa | V | `UNRESOLVED` | `TEC_VMAX_NOT_ESTABLISHED` |
| `VOLTAGE_MIN_V` | Điện áp nhánh tối thiểu khi có tải | V | `UNRESOLVED` | `PSU_LOAD_REGULATION_NOT_MEASURED` |
| `HOT_SIDE_MAX_C` | Nhiệt hot-side tối đa | °C | `UNRESOLVED` | `HOT_SIDE_LIMIT_NOT_ESTABLISHED` |
| `DUTY_MAX_PERMILLE` | Duty tối đa cho phép | ‰ | `UNRESOLVED` | `DUTY_NOT_CHARACTERISED` |
| `ON_TIME_MAX_MS` | Thời lượng run tối đa | ms | `UNRESOLVED` | `ON_TIME_NOT_CHARACTERISED` |

**Hệ quả có chủ đích:** mọi lệnh `START` trên bản giao W04 trả
`START_LIMITS_UNRESOLVED`. Đây là hành vi đúng, không phải lỗi cần “fix” bằng
cách điền số tạm.

Cách một mục chuyển sang `RESOLVED` (làm ở G3, có bằng chứng):

1. đo trên phần cứng thật (PSU/TEC/ shunt/IBT-2/heatsink của CG-HW-001);
2. ghi số đo + điều kiện vào `evidence/A/W04/`;
3. cập nhật `value` + `source` trỏ đúng tệp bằng chứng;
4. review lại thay đổi trước khi build.

---

## 5. Lệnh console (UART0, 115200 8N1)

Cú pháp nghiêm ngặt; sai cú pháp bị từ chối và log
`#CG ERR console=PARSE_FAIL error=<token>`.

| Lệnh | Điều kiện | Tác dụng |
|---|---|---|
| `ARM <8 hex>` | đúng token boot, trạng thái OFF/ARMED | ủy quyền một run, TTL 120 s |
| `START <giây>` | đã ARM, mọi gate qua | một run có thời hạn (1..86400 s) |
| `STOP` | COOLING/ARMED | dừng an toàn, vào COOLDOWN |
| `ESTOP` | bất kỳ | ngắt ngay + latch |
| `CLEAR <8 hex>` | FAULT_LATCH + token + đầu vào khỏe | xóa latch, vào COOLDOWN |
| `RUN <label>` | `[A-Za-z0-9_-]{1,32}` | đặt `run_id` cho telemetry |
| `PHASE <token>` | `UNSET`, `G0`..`G5`, `TEC_OFF` | đặt `test_phase` |
| `STATUS` | — | log trạng thái hiện tại |

Trên bản giao W04, `START` **luôn bị từ chối** vì giới hạn chưa RESOLVED và
output stage bị tắt; các lệnh còn lại chạy được để kiểm tra fail-closed.

---

## 6. Telemetry thô — schema 1 (W04) và schema 2 (W05)

Một dòng mỗi giây, bắt đầu bằng `#CG TELEM schema=N`, do
`firmware/main/cg_telemetry.c` phát ra. Mô tả trường của bản giao W04 (hợp
đồng dữ liệu canonical thuộc `docs/02`):

| Trường | Kiểu | Khi thiếu |
|---|---|---|
| `timestamp_utc` | chuỗi | luôn `UNAVAILABLE` — thiết bị không có đồng hồ thực |
| `elapsed_ms` | int | luôn có (uptime thiết bị) |
| `run_id` | chuỗi | `UNSET` cho tới khi `RUN` |
| `boot_id`, `boot_count` | chuỗi/int | luôn có |
| `firmware_version`, `hardware_config_id` | chuỗi | luôn có |
| `test_phase` | chuỗi | `UNSET`/`TEC_OFF`/`G0`..`G5` |
| `t_inside_c` | float/`nan` | `nan` + `t_inside_status` |
| `t_cold_side_c`, `t_hot_side_c`, `t_ambient_c` | float/`nan` | `nan` + `NOT_ASSIGNED`/`SENSOR_NOT_PRESENT` |
| `relative_humidity_pct` | float/`nan` | `nan` + `SENSOR_NOT_PRESENT` |
| `door_open` | 0/1/`nan` | `nan` + `UNVERIFIED` (polarity chưa commissioning) |
| `voltage_v`, `current_a`, `power_w` | float/`nan` | `nan` + `voltage_status`/`current_status`/`power_status` |
| `pwm_duty` | int ‰ | luôn có (trạng thái firmware) |
| `fan_command` | `ON`/`OFF` | luôn có |
| `sensor_validity` | `VALID`/`DEGRADED`/`INVALID`/`NO_DATA` | — |
| `fault_code` | hex 32-bit | luôn có (`0x00000000` khi sạch) |

Quy tắc dữ liệu:

- `nan` nghĩa là **không có giá trị**; parser host đổi thành `None`, không bao
  giờ thành 0.
- Một số chỉ dùng được khi `*_status=OK`; builder ML che giá trị nếu status khác
  `OK` (mâu thuẫn firmware không lọt vào dataset).
- `t_inside_c` lấy từ ROM `28AEBF2200000006` mà firmware gán role T2, và mang
  `t_inside_src=T2`. Nhãn vật lý của probe này **chưa** được xác nhận
  (`ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`, `evidence/A/W02/sensor-rom-map.yaml`),
  còn các phiên bench sau này báo cùng ROM đó đang nằm trên khối tản nhiệt nóng.
  Đổi ngữ nghĩa đo từ "không khí trong khoang" (docs/01 §6) sang HOT_SIDE là thay
  đổi hợp đồng đo và phải qua review cấp dự án theo chính sách thay đổi của
  docs/01; review đó **chưa** xảy ra, nên tệp này không đổi ngữ nghĩa, firmware
  production vẫn phát `t_hot_side_c=NOT_ASSIGNED`, và khác biệt được ghi là mục
  mở trong `evidence/A/W04/acceptance.md`.
- `t_cold_side_c`/`t_hot_side_c` hiện `NOT_ASSIGNED` vì chưa có probe nào được
  gán vật lý vào hai mặt TEC. Gán role là thay đổi cấu hình có tài liệu, không
  phải suy đoán trong parser.
- Dòng thô còn mang `raw_t1_c`..`raw_spare_c` + status để truy vết ROM/probe.
- `voltage_v`/`current_a`/`power_w` đến từ PZEM-017, nguồn đo điện frozen của
  CG-HW-001. Theo PHY-PZ-002 (docs/01), công suất đo dưới PWM là dữ liệu đặc
  trưng hóa, chưa đủ để tuyên bố năng lượng sơ cấp của nhánh.
- `timestamp_utc=UNAVAILABLE` là hành vi đúng: máy host chỉ được ghi metadata
  phiên (header của `cg_capture.py`), không được dán giờ host lên từng dòng thiết
  bị.

### 6.1 W05 — thêm identity, coherence, quality và liveness (schema 2)

W05 nâng `CG_TELEMETRY_SCHEMA_VERSION` lên **2** và giữ toàn bộ tên trường W04
nguyên nghĩa. `firmware/tools/cg_telemetry_schema.py` nhận cả schema 1 và 2, nên
các capture đã commit trong `evidence/A/W04/` vẫn parse được — test
`test_committed_w04_capture_still_parses` đọc trực tiếp 62 dòng thật và yêu cầu
0 dòng bị từ chối. Đây là stream serial nội bộ; envelope JSON trong `docs/02`
vẫn giữ `schema_version: 1` riêng của nó.

Nhóm mới trên dòng:

| Nhóm | Trường | Ý nghĩa bằng chứng |
|---|---|---|
| Identity | `device_id` `seq` `calibration_id` | Khoá dedup backend là `(device_id, boot_id, seq)` (docs/02 633-646, 845). `seq` tăng đơn điệu trong một boot; frame bị từ chối vì vượt ngân sách line **vẫn tiêu tốn seq**, nên khoảng hổng nghĩa là "quan sát này không tồn tại", không phải "dòng hỏng". |
| Calibration | `calibration_id=UNRECORDED` | Token trạng thái, không phải định danh. Chưa đo bundle hiệu chuẩn nào (docs/01 §29; `sensor-rom-map.yaml` ghi `calibration_id: null`). Host converter phải ánh xạ `UNRECORDED → null`; bịa ra `CG-CAL-…` là cách duy nhất để một giá trị chưa được kiểm chứng lọt vào downstream. |
| Sensor identity | `t1_rom` `t2_rom` `t3_rom` `spare_rom` `role_status` `rom_source` | docs/01 §6.5: identity là ROM, không phải index thư viện. `rom_source=FROZEN_CONFIG_MAP` nói thẳng các byte này đến từ bảng cấu hình đông cứng, **không** phải một phép match 1-Wire trong từng frame; bằng chứng detect mỗi boot nằm ở dòng `#CG ROM ... present=`. `role_status` nói thẳng nhãn vật lý vẫn pending. |
| Coherence | `thermal_age_ms` `power_age_ms` `door_age_ms` `thermal_seq` `power_seq` `door_transitions` `door_cycles` `probes_valid` `probes_expected` | Frame tự khai mỗi nhóm dữ liệu cũ bao nhiêu và producer nào đã thực sự poll. W04 không có door timestamp và không xuất `energy_wh`. |
| Electrical | `energy_wh` `energy_status` | Thanh ghi PZEM đã decode từ W03 nhưng chỉ nằm ở log; nay vào snapshot và vào dòng. |
| Quality | `thermal_quality` `environment_quality` `door_quality` `electrical_quality` `quality` | Đúng bốn trạng thái canonical `VALID/DEGRADED/INVALID/UNKNOWN` (docs/01 §19), collapse `INVALID > UNKNOWN > DEGRADED > VALID`. |
| Applied | `cooling_applied` `cooling_applied_source` `cooling_evidence` | Tách "lệnh đã xin" khỏi "đầu ra đang được giữ" và khỏi "PZEM xác nhận/phủ nhận". |
| Liveness | `health` `health_thermal` `health_bme` `health_door` `health_power` `health_telemetry` `health_control` `*_beats` `*_max_gap_ms` | A-W05-01: producer dừng beating phải hiện ra theo tên, không được trông như một sensor ổn định đang lặp lại cùng một giá trị. |

Bốn quy tắc phải giữ:

- **Thiếu = `nan` + status**, không bao giờ 0.0 và không bao giờ là giá trị cũ.
  `cg_snapshot_publish_power(valid=false, …)` thay quan sát bằng một quan sát
  invalid có timestamp riêng; không có đường dẫn nào tái dùng dòng trước.
- **`UNKNOWN` không được âm thầm thành bình thường** (docs/01 2302-2306). Nguồn
  chưa từng được publish là `UNKNOWN`, không phải `INVALID`; và frame không có
  báo cáo liveness là `health=UNKNOWN`, không phải `OK`.
- **Cũ ≠ không hoạt động.** `cooling_evidence=UNOBSERVED_STALE`/`UNOBSERVED_NO_DATA`
  phân biệt "không thể biết" với `MEASURED_IDLE_AND_ZERO` "biết, và dòng bằng 0".
  `MEASURED_CONTRADICTS_APPLIED` nêu trường hợp đầu ra và đo đạc mâu thuẫn.
- **Cổng BME280 chưa triển khai** nên `environment_quality=DEGRADED` và
  `quality` không thể đạt `VALID` trong build này. Đó là trạng thái trung thực,
  không phải lỗi cần che bằng cách bỏ qua nhóm environment.

Ngân sách dòng: worst case **dựng sẵn** (seq 10 chữ số, age 20 chữ số, token dài
nhất, run_id 32 ký tự) đo được **2098 byte** trên ngân sách `CG_TELEMETRY_LINE_MAX
= 2560`; frame điển hình 1873 byte, trong khi capture W04 thật đo 1007–1012 byte.
Test `test_measured_worst_case_fits_the_shipped_budget` thất bại nếu worst case
đạt **90 %** ngân sách. Chưa có frame schema-2 nào từng được phát trên phần cứng,
nên các con số này là phép tính trên ngân sách buffer, không phải throughput đo được.

Tài liệu tham chiếu: `evidence/A/W05/quality-test.md` (33 scenario C trên host,
118 static check, 24 mutation test), `evidence/A/W05/schema-fixture.json` (một
dòng thật do chính formatter render), `evidence/A/W05/timing-pilot.md` (nhịp đo
từ capture 60 s đã commit), `evidence/A/W05/handoff-w05.md` (hợp đồng cho B/C/D).
Tất cả đều là bằng chứng **phần mềm**: ảnh W05 chưa từng được flash, nên chưa có
30 phút telemetry thật.


### 6.2 W06 — hợp đồng lệnh device-side và ACK (serial schema 3)

W06 nâng `CG_TELEMETRY_SCHEMA_VERSION` lên **3** và giữ nguyên schema 1 (W04) cùng
schema 2 (W05): `cg_telemetry_schema.py` nhận cả ba, và test đọc lại capture W04 đã
commit cộng fixture W05 nên lịch sử không bị viết lại.

`firmware/main/cg_command.c/.h` cài đặt phần **device** của docs/02 §28-§32:

- chuỗi validate đúng thứ tự §29: schema → **nguồn** → `device_id` → `command_id`
  mới/trùng → freshness → range → local safety → local state. Nguồn chỉ nhận
  `CG_CMD_SOURCE_NETWORK`; `UNKNOWN` (giá trị khởi tạo 0) và `LOCAL_CONSOLE` bị chặn
  **trước** khi tra store, nên một nguồn không được phép cũng không đọc lại được
  canonical result của đường khác. Đây là phân loại xuất xứ, **không** phải xác thực:
  `source` cố ý không phải field trên dây, chỉ lớp nhận byte mới được đóng dấu.
- Parser đòi **đủ** các field bắt buộc của §28.2 theo đúng tên (`created_at_ms`,
  `expires_at_ms`, `action_cooling`, `action_duty_permille`, `policy_version`,
  `reason_code`), mỗi thiếu là một token `MISSING_*` riêng; `controller_id` thuộc
  §28.3 nên tùy chọn; một field ghi trùng ⇒ `DUPLICATE_FIELD`. Lý do:
  `CG_CMD_COOLING_OFF = 0`, nên một lệnh thiếu `action_cooling` mà không bị chặn sẽ
  trở thành một lệnh "tắt" thật sự — docs/01 §19 nói rõ unknown không được âm thầm
  thành bình thường.
- **expiry tuyệt đối không thẩm định được thì fail closed.** Thiết bị không có đồng hồ
  thực, nên `created_at`/`expires_at` của issuer không so sánh được với gì cả.
  Thiết bị trả `SAFETY_BLOCKED / reason=EPOCH_UNSYNCHRONIZED, expiry_evaluable=0`.
  **Không** thay bằng TTL tính từ lúc nhận: TTL từ lúc nhận chỉ chứng minh thiết bị
  *vừa thấy* lệnh, không nói lệnh đã nằm trong queue bao lâu, nên nó không thể thay
  cho ngữ nghĩa canonical.
  `expires_at` không có ⇒ `REJECTED/MISSING_EXPIRY`, không bao giờ được hiểu là "vĩnh viễn";
  thiếu `created_at` ⇒ `MISSING_CREATED_AT`; `expires_at <= created_at` ⇒ `OUT_OF_RANGE`.
- idempotency: store RAM 8 phần tử. Bản trùng trả `DUPLICATE_CANONICAL` kèm
  **canonical_status** của lần đầu, `reapplied=0`, và quyết định được trả trước cả
  freshness/range/safety — để một replay không thể đạt verdict khác khi thế giới đã đổi.
  Đếm `hits` và `evicted` để bound của retention là quan sát được, không phải giả định.
- **store không bao giờ xuống NVS.** Sau reset thiết bị *không nhớ* command_id cũ
  (`duplicate_recognized=0`) và cũng **không** tiếp tục desire cũ: nó khởi động
  default-OFF và validate lại. A-W06-06 được chứng minh bằng host scenario; phần vật lý
  (power-cycle thật sau một lệnh ON) còn nợ, và hôm nay được chặn bởi output stage
  compiled out.
- ACK tách `desired_*` khỏi `applied_*`; cặp applied chỉ lấy từ context của thiết bị.
  ACK cũng mang `device_id` **của chính thiết bị** (docs/02 §32.3, dòng 2206), lấy từ
  context chứ không echo lại `device_id` của lệnh — nhắc lại một danh tính được yêu
  cầu chỉ là bằng chứng của một cái tên, không phải của người đã trả lời.
  `applied_state_comes_from_the_device` chứng minh board *đang* làm lạnh phải ACK
  `applied_cooling=ON` khi bị yêu cầu OFF.
- Cầu console `CMDTEST` dùng đúng validator đó nhưng bị đóng dấu
  `source=LOCAL_CONSOLE`, `command_id_form=TEST_TOKEN` và **không** mang
  `created_at`/`expires_at` — thiết bị không có clock để đóng dấu, và một timestamp do
  người vận hành gõ không phải time base đã đồng bộ. Nó không thể đạt ACCEPTED trên
  build thật vì rule nguồn chạm trước mọi thứ khác: `SAFETY_BLOCKED /
  `SOURCE_NOT_CANONICAL`. Đây là công cụ test, **không phải** network command contract.

`schema=1` trên dòng `#CG CMDACK` là phiên bản **command envelope** của docs/02 §28.1,
không phải serial schema của stream telemetry; test giữ cho hai số này không lẫn nhau.

`device_mode` trong ACK là trạng thái controller (`OFF`/`ARMED`/`COOLING`/`COOLDOWN`/
`FAULT_LATCH`), **không phải** policy mode §23 docs/02 — firmware này không chạy policy
machine, và ghi tên policy mode sẽ gán cho firmware một quyết định nó chưa bao giờ đưa ra.

Khi chưa có time sync, **không lệnh remote nào có thể được accept**, kể cả lệnh STOP.
Đây là hệ quả có chủ đích của fail-closed; đường bảo vệ cục bộ (STOP/ESTOP console,
heartbeat timeout, fault latch, output stage compiled out) không phụ thuộc hợp đồng lệnh.
Chọn time sync hay sửa ngữ nghĩa expiry là quyết định của C/D và dự án (docs/02 phải đổi
trước), không phải quyết định của Member A — xem `evidence/A/W06/handoff-w06.md` §1.

Bằng chứng: `evidence/A/W06/command-parser-tests.md` (39 scenario C trên host, 120 static
check, 26 mutation + 1 must-not-fire control + 1 baseline, 8 unit test cho công cụ trace), `ack-fixture.json` và ba log lệnh
(`duplicate/expired/reset-command-log`) — tất cả generate từ source thật, gắn nhãn
host scenario, không phải đo vật lý. `physical-command-trace.md` nói rõ trace thật còn nợ gì.

---

## 7. Thu thập dữ liệu (bắt đầu bằng phiên TEC-OFF)

Ba tầng tách biệt, không ghi đè lên nhau:

```text
serial capture (thô, bất biến)
  -> telemetry-raw.jsonl   (trích xuất trung thực, giữ nguyên dòng gốc)
  -> telemetry.csv         (bảng acquisition phẳng theo hợp đồng)
  -> ml-dataset.csv        (dữ liệu dẫn xuất cho huấn luyện, tách riêng)
```

Lệnh (chạy trên máy bench và **không** tự chạy; người vận hành duyệt từng phiên):

```bash
py firmware/tools/cg_capture.py --port COM4 \
    --out evidence/A/W04/tec-off-session.log --seconds 900

py firmware/tools/cg_build_telemetry.py evidence/A/W04/tec-off-session.log \
    --jsonl evidence/A/W04/telemetry-raw.jsonl \
    --csv   evidence/A/W04/telemetry.csv \
    --ml-out evidence/A/W04/ml-dataset.csv
```

Builder trả exit 0 chỉ khi có ít nhất một dòng telemetry và **không** dòng nào bị
từ chối; dòng hỏng vẫn được ghi nhận kèm số dòng và lý do, không bị sửa.

Phiên TEC-OFF hợp lệ (cho G1/G2) là phiên mà:

- `tec_state=OFF`, `pwm_duty=0`, `output_stage=DISABLED` trên **mọi** dòng;
- không có `fault_code` khác 0 ngoài lỗi do người vận hành cố tình tạo, và phép
  tiêm lỗi vẫn phải tuân PHY-SAFE-006 (docs/01): những lỗi bị cấm tiêm thì vẫn
  bị cấm kể cả khi có giám sát;
- `run_id` và `test_phase` được đặt tường minh (`RUN tec-off-01`, `PHASE TEC_OFF`).

---

## 8. Kế hoạch bench G0–G5

Mỗi cổng có tiêu chí PASS/FAIL đo được và bằng chứng bắt buộc. Không cổng nào
được “PASS bằng cảm giác”. **Không** có số dòng/duty/thời gian cụ thể trong G3:
các số đó là kết quả đo, không phải giả định.

### G0 — Kiểm tra điện khi mất nguồn (chưa cấp nguồn TEC)

Điều kiện: PSU 12 V ngắt; USB ngắt; nhánh TEC không có nguồn; dùng DMM.

1. Xác nhận nhánh TEC thực sự chết (0 V tại `IBT-2 B+` và `B−` so với PSU−).
2. Đo continuity: GPIO5 ↔ header RPWM, GPIO6 ↔ R_EN, GPIO10 ↔ L_EN,
   GPIO33 ↔ DS18B20 DATA, GPIO36/37 ↔ TTL485 (đúng chiều TX/RX).
3. Đo và ghi vị trí shunt trong đường hồi; đo `B−` ↔ GND logic. Nếu có thông
   gần 0 Ω, ghi rõ đây là chủ ý hay cầu nối; **không** để dòng TEC đi qua GND
   logic.
4. Kiểm tra cầu chì nhánh đã lắp đúng vị trí gần nguồn (bộ 10/15/20 A,
   docs/01 §16). Ghi nhãn cầu chì đang lắp; đây chưa phải lựa chọn cuối.
5. Xác định topology input của IBT-2 (ảnh/marking/tài liệu module): có buffer
   5 V không, ngưỡng V_IH là bao nhiêu. Nếu không xác định được, ghi
   `NOT VERIFIED` và chuyển sang đo ở G1 **khi nhánh TEC vẫn ngắt**.
6. Kiểm tra không có dây nào bypass shunt hoặc bypass cầu chì.
7. Ghi tiết diện và cấp dây thực đo của nhánh TEC so với yêu cầu `2 × 2.5 mm²`
   (PHY-SAFE-004, docs/01) kèm cỡ cos/găm đang dùng. Đây là mục audit bắt buộc,
   Member A không tự nới; kết quả đo nằm trong
   `evidence/A/W04/g0-electrical-verification.md`.

**PASS:** mọi continuity khớp map v2; đường hồi và quan hệ GND được ghi rõ;
cầu chì đúng vị trí; nhánh TEC cách ly được; topology input được ghi (kể cả
`NOT VERIFIED`). **FAIL:** bất kỳ sai lệch nào ⇒ không sang G1.

Bằng chứng: `evidence/A/W04/g0-electrical-verification.md` + ảnh đo.

### G1 — ESP32 khởi động, log, TEC OFF (nhánh TEC vẫn ngắt)

Điều kiện: nhánh TEC ngắt (hoặc cầu chì tháo + PSU ngắt ở G1a); chỉ cấp USB/UART
cho board; nạp bản build đã review (việc nạp thuộc người vận hành, sau khi
slice được duyệt).

1. Mở serial 115200 trên cổng CH343G; xác nhận thấy boot log `#CG AUTH`,
   `#CG TEC event=BOOT`, và `#CG TELEM` 1 Hz (đóng U12).
2. Đo RPWM/R_EN/L_EN tại chân ESP32 bằng DMM/scope trong: cold boot, nhấn RESET,
   rút/cắm lại USB, và 10 phút chạy. Cả ba phải giữ mức LOW (≈0 V tại chân
   ESP32) ngoài mọi thời điểm.
3. Gửi `ARM <token>` rồi `START 5`: phải log từ chối (`START_LIMITS_UNRESOLVED`
   hoặc `START_STAGE_UNAVAILABLE`), `tec_state=OFF`, không đổi chân.
4. Gửi `START 5` khi chưa ARM: phải `START_NOT_ARMED`.
5. Gửi `ESTOP`: phải latch (`fault_code` có bit `ESTOP`), outputs OFF; `CLEAR`
   sai token phải bị từ chối; `CLEAR` đúng token đưa về `COOLDOWN`.
6. Chạy `cg_capture.py` 10 phút, build telemetry: toàn bộ dòng phải có
   `output_stage=DISABLED`, `pwm_duty=0`, `fan_command=OFF`.

**PASS:** mọi mục trên đúng; capture sạch (builder exit 0).
**FAIL:** bất kỳ chân nào nhảy mức 1, hoặc có dòng telemetry mâu thuẫn.

Bằng chứng: `evidence/A/W04/g1/SUMMARY.md` + log + file telemetry.
Trạng thái G1 trong bản giao này: **PARTIAL** — các mục đo DMM/oscilloscope tại
GPIO5/6/10 chưa thực hiện; `g1/SUMMARY.md` §G tự khai điều đó và `acceptance.md`
ghi nhận tương ứng.

### G2 — Fan độc lập và đo nhiệt hot-side (TEC vẫn chưa cấp nguồn)

1. Cấp fan theo đúng định mức của fan (đo dòng fan ở nguồn riêng); xác nhận
   quay và luồng khí qua heatsink.
2. Gắn/kiểm tra probe hot-side: tiếp xúc cơ học, keo tản nhiệt, vị trí trên
   block hot-side (không đo không khí).
3. Làm ấm nhẹ block hot-side bằng nguồn nhiệt an toàn bên ngoài (ví dụ tay hoặc
   khí ấm), xác nhận kênh đo tăng và trở lại; ghi độ ổn định 5 phút.
4. Nếu cần gán probe cold-side/hot-side vào role firmware, thực hiện như một
   thay đổi cấu hình có tài liệu (ROM → role), không sửa parser.

**PASS:** fan chạy đúng định mức + probe hot-side phản hồi và ổn định, có mapping
role được ghi. **FAIL:** probe không phản hồi/không ổn định ⇒ không sang G3.

Bằng chứng: `evidence/A/W04/g2-fan-hot-side.md`.

### G3 — Commissioning TEC có giám sát, dòng giới hạn (chỉ sau G0–G2 PASS)

Điều kiện vào: G0, G1, G2 PASS; cầu chì đúng vị trí; PSU đặt giới hạn dòng theo
thông số đã xác minh của đúng SKU TEC (hoặc theo kế hoạch đo bước nhỏ nếu chưa
có datasheet tin cậy); người vận hành có mặt; ESTOP trong tầm tay.

1. Chạy từng bước nhỏ: mỗi bước một duty/thời lượng **được dẫn xuất từ phép đo
   trước**, ghi V, I, T_cold, T_hot, nhiệt IBT-2.
2. Dừng ngay nếu có fault, dòng chạm giới hạn PSU, hoặc IBT-2 nóng bất thường
   (PHY-ACT-004: thermal shutdown không phải điểm vận hành hợp lệ).
3. Sau mỗi bước ổn định, cập nhật bảng giới hạn (mục 4) với nguồn bằng chứng;
   chỉ chuyển mục sang `RESOLVED` khi có số đo thật.
4. Chọn cầu chì cuối theo docs/01 §16.2 (dòng ổn định, quá độ khởi động, dây,
   holder, IBT-2, nhiệt đầu cực, biên an toàn) — không chọn “cầu chì lớn nhất
   không cháy”.

**PASS:** từng điểm vận hành nằm trong giới hạn đã RESOLVED, ổn định, có bằng
chứng; bảng giới hạn đầy đủ `RESOLVED`. **FAIL:** bất kỳ điểm nào ngoài giới hạn
hoặc không ổn định.

Bằng chứng: `evidence/A/W04/g3-supervised-commissioning.md` + CSV/telemetry.

### G4 — Vận hành nhiệt trong hộp cách nhiệt

1. Lắp TEC đúng mặt lạnh/mặt nóng, keo tản nhiệt hai mặt, heatsink + fan phía
   nóng, probe khoang và probe hot-side đúng vị trí.
2. Chạy baseline TEC-OFF trong hộp kín ít nhất 10 phút; sau đó các run có thời
   hạn trong giới hạn đã RESOLVED.
3. Ghi telemetry liên tục; theo dõi hot-side và nhiệt IBT-2; dừng khi chạm bất
   kỳ giới hạn nào.

**PASS:** hot-side luôn dưới `HOT_SIDE_MAX_C` đã RESOLVED; không có
`SENSOR_INVALID/STALE`; có ít nhất một chu trình làm lạnh và hồi nhiệt quan sát
được. **FAIL:** chạm giới hạn hoặc mất cảm biến.

Bằng chứng: `evidence/A/W04/g4-insulated-box.md` + capture.

### G5 — Lặp lại thí nghiệm có nhãn cho ML

1. Mỗi lần chạy: `RUN <label>`, `PHASE G5`, cùng điều kiện ban đầu, lặp N lần.
2. Dùng `cg_build_telemetry.py` xuất JSONL/CSV/ML; giữ capture thô bất biến.
3. Ghi bảng điều kiện (nhiệt độ phòng, vị trí hộp, duty, thời lượng) vào
   `run-manifest`.

**PASS:** đủ N run, mỗi run có telemetry sạch; dataset ML tách riêng và tái tạo
được từ capture thô. **FAIL:** thiếu run, capture lỗi, hoặc trộn dữ liệu dẫn xuất
vào file thô.

Bằng chứng: `evidence/A/W04/g5-repeated-runs/`.

---

## 9. Điều kiện Member A đặt ra trước khi mở output stage của chính bản firmware này

Đây là tiền đề cục bộ của Member A cho output stage production, **không** phải
yêu cầu canonical và **không** ràng buộc bench của thành viên khác: docs/01 §12
chỉ bắt buộc default-OFF chứ chưa từng đòi interlock phần cứng, và các phiên
bench H7/H8 cục bộ của Member A (nằm ngoài repository này) đã chạy mà không có
interlock. Chỉ khi **tất cả** điều kiện sau đúng,
và sau review:

1. G0, G1, G2 PASS với bằng chứng đã ghi.
2. Bảng giới hạn mục 4 `RESOLVED` đầy đủ, mỗi mục có nguồn.
3. Interlock phần cứng đã tồn tại và được đấu vào GPIO có pull-down, đã cập nhật
   map v2 + checker + tài liệu (tiền đề cục bộ của Member A, không phải yêu cầu
   canonical).
4. Probe cold-side/hot-side đã gán role có tài liệu.
5. Adapter thật thay cho adapter từ chối: triển khai PWM/EN/fan đúng thứ tự đã
   kiểm bằng harness.
6. Đặt đồng thời:
   `CG_TEC_OUTPUT_STAGE_ENABLED=1`, `CG_TEC_HARDWARE_GATES_VERIFIED=1`,
   `CG_ACTUATOR_ENABLE_ALLOWED=1` (ba `#error` trong `coldguard_config.h` ép
   điều kiện này).
7. Kiểm tra lại toàn bộ W02/W03/W04 static checks + build ESP-IDF + review.

Không có bước nào ở trên được thực hiện trong bản giao W04 này.

---

## 10. Điều tuyệt đối không làm

- Không **tự ý** cấp nguồn TEC, nạp firmware hoặc flash: mỗi thao tác vật lý
  cần người vận hành phê duyệt tại thời điểm đó. Các phiên đã làm những việc này
  đều có authorization tường minh và log trong `evidence/A/W04/`.
- Không bypass shunt hoặc cầu chì nhánh.
- Không sửa dây khi mạch đang có nguồn.
- Không điền số giới hạn “tạm cho chạy được”.
- Không coi một lần PWM ngắn là bằng chứng vận hành bền.
- Không kết luận “TEC chạy PASS” khi chưa có số đo thật.
- Không đổi code của member khác hoặc viết lại lịch sử W01–W03.

---

## 11. Phần vật lý còn thiếu của W04

G0 và G1 đã chạy và có log trong `evidence/A/W04/`; ảnh H6 đã đo được đáp ứng
điện đầu tiên. W04 canonical vẫn **chưa** đủ điều kiện nghiệm thu. Phần còn
thiếu, khớp với `evidence/A/W04/acceptance.md`:

1. Bản ghi cực tính TEC kèm ảnh (A-W04-06) — mới có kế hoạch, chưa có kết quả.
2. Quét 5 cold boot + 5 reset ở mức chân cho default-OFF (A-W04-04) — mới có
   quan sát logic IDLE/OFF, chưa có quét.
3. Cơ sở chọn cầu chì cuối cùng kèm ảnh tem và vị trí (A-W04-03).
4. Audit cấp dây nhánh TEC `2 × 2.5 mm²` (A-W04-02) — hồ sơ W04 chỉ ghi HW-19
   `UNVERIFIED` và không có ảnh; con số 1.75 mm² xuất hiện duy nhất trong ghi chú
   bench nội bộ của các tuần sau (H7/H8, không nằm trong PR này), nên W04 **không**
   claim một tiết diện đã đo. Mọi hướng xử lý sai lệch đều phải qua review thay
   đổi cấu hình, không tự nới.
5. Đường đáp ứng TEC đầu tiên có kênh nhiệt T1/T2/T3 (A-W04-07) — ảnh H6 chỉ đo
   điện, không đọc DS18B20/BME280.
6. Tệp giao hàng canonical: `power-topology-v1.png`, `fuse-commissioning-note.md`,
   `boot-default-off.csv`, `first-tec-trace.csv`, `first-tec-plot.png`,
   `polarity-photo.md`.

**Sai lệch cần ghi nhận (2026-11-01):** phiên H6 2026-10-29 đã cấp nguồn nhánh
TEC ở PWM 10 % **trước khi** G2 (fan + probe hot-side) hoàn tất và khi fan vẫn
chỉ ở mức `NOT_COMMANDABLE`. Người vận hành đã ủy quyền tường minh cho phép đo
đó, nó chạy trên ảnh bench H6 riêng, và nó **không** là cổng G3 theo thang
G0–G5 ở mục 8, cũng không nghiệm thu `PWR-H5-03` (quan hệ fan–TEC). Giá trị của
nó trong W04 chỉ là đáp ứng điện đầu tiên (A-W04-05).

Mỗi bước đều cần người vận hành phê duyệt và giám sát; tệp này không tự cấp quyền.

---

## 12. Truy vết

- `docs/01-physical-measurement-correctness-contract.md` §11.8, §12, §13, §16.
- `evidence/A/as-built-pinmap-2026-10-27.md` (map v2).
- `firmware/main/cg_tec_control.{c,h}`, `cg_tec_limits.{c,h}`,
  `cg_tec_hw.c`, `cg_telemetry.{c,h}`, `cg_commission.c`.
- Host tools: `firmware/tools/cg_telemetry_schema.py`,
  `firmware/tools/cg_build_telemetry.py`, `firmware/tools/cg_capture.py`.
- Kiểm tra: `firmware/tools/cg_check_firmware_w04.py`,
  `firmware/tools/run_all_checks_w04.py`,
  `firmware/tools/tests/test_cg_tec_state_machine.py`.
