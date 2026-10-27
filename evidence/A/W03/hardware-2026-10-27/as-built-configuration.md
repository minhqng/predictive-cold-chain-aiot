# As-built W03 configuration (bench snapshot 2026-10-27)

**Trạng thái: `AS-BUILT OBSERVED — NOT A FROZEN CONFIGURATION`**
**`hardware_config_id: NOT_ASSIGNED`.** Tài liệu này ghi những gì người vận hành báo và
những gì ảnh W01 cho thấy; nó **không** thay đổi BOM đã freeze và **không** freeze pin map.

## 1. Nguồn lực / rail

| Hạng mục | As-built | Nguồn | Ghi chú |
|---|---|---|---|
| Cooling-branch voltage (TEC OFF) | `11.94–11.95 V` | TEST 132B (bench) | Điện áp nhánh đo bởi PZEM; không suy model PSU |
| XL4015 output | `5.00 V` | W01 `bom-audit.csv` HW-13 (operator-reported) | Ảnh `06-xl4015.jpg`; marking chip bị cắt |
| TB4506 rail | `4.99 V` | W01 HW-13 | TB4506 thay TB4504 — `CR-A-W01-02` PENDING |
| Fuse nhánh XL4015 | `5 A` | W01 HW-16 (operator-reported) | Chỉ xác nhận `1 × 5 A`; BOM yêu cầu `≥2 × 5 A` |
| Fuse PZEM | `1 A` | W01 (ngoài BOM) | Bổ sung ngoài BOM, cần leader biết |
| Logic current tổng | **NOT MEASURED** | — | Không có số đo |
| Ripple / nhiệt XL4015 | **NOT MEASURED** | — | W04/characterization, không phải H2 voltage |

## 2. RS-485 / PZEM

| Hạng mục | As-built | Nguồn | Ghi chú |
|---|---|---|---|
| Module | **TTL485-V2.0**, rail **5 V**, auto-direction | Ảnh W01 `02/03-rs485-*.jpg` + operator | Không phải MAX3485 3.3 V đã freeze |
| Chip | `MAX13487ESA` **operator-reported** | Operator | **Không** ảnh nào đọc được marking; không phải sự thật đã xác minh |
| Header | `GND / RXD / TXD / VCC` | Ảnh W01 | Không có `DE/RE` |
| Kết cuối | 120 Ω có jumper | Ảnh W01 | Trạng thái jumper trong ảnh không xác định |
| UART TX → module RXD | `GPIO36` | Operator + firmware | W03 firmware dùng UART1 |
| UART RX ← module TXD | `GPIO37` | Operator + firmware | Có mạch phân áp bảo vệ phía RX |
| Phân áp RX | `10k/10k/10k` theo W01 operator | W01 | Giá trị đo `~3.314 V` tại GPIO37; **không** đo lại; chưa được D duyệt |
| Framing | `9600 baud, 8N1` | Sketch bench source + `coldguard_config.h` + operator | Địa chỉ Modbus slave 0x01 được cấu hình trong sketch bench và kiểm tra qua logic xác thực phản hồi của sketch; TEST 132B ghi nhận 600/600 mẫu hợp lệ theo trạng thái parser, nhưng file log telemetry không lưu 600 khung phản hồi hex thô nên không tuyên bố đã quan sát trực tiếp byte mở đầu của từng khung từ file log. Cấu hình 9600 baud, 8N1 được đối chiếu với mã nguồn sketch bench V4 và cấu hình canonical firmware (`CG_RS485_BAUD_RATE 9600`), không suy ra trực tiếp từ chuỗi trong CSV/log. |
| DE/RE | Không có | As-built | Firmware mặc định AUTO; MANUAL/GPIO35 là compile-time option cho MAX3485 canonical |
| A/B polarity | Không ghi nhận trong phiên này | — | 600/600 cho thấy polarity hiện tại hoạt động; không chứng minh an toàn |

**Không** đổi sang MAX3485, **không** thêm DE/RE, **không** đổi GPIO36/37 trong task này.

## 3. IBT-2 / actuator

| Tín hiệu | As-built | Firmware W03 |
|---|---|---|
| `RPWM` | `GPIO5` | Chỉ ghi 0; không LEDC/MCPWM |
| `R_EN` | `GPIO6` | Chỉ ghi 0; enable được xóa trước |
| `L_EN` | `GPIO10` | **Không được firmware W03 điều khiển** |
| `LPWM` | `GND` | Không điều khiển |
| `R_IS` / `L_IS` | Không đấu | Không dùng |
| Buffer | `SN74HC244` | — |
| Driver | `2 × BTS7960B` | — |
| Board | `HW-039` | — |

### 3.1 Xung đột `GPIO10` — phải chặn freeze

`GPIO10` đồng thời là:

- `L_EN` của IBT-2 theo as-built operator báo;
- `CG_PIN_DS18B20_DATA` của W02 firmware (`GPIO10`), đã dùng để đọc 4 ROM ID và 620 mẫu
  DS18B20 trên bench;
- chân trong `docs/01 §11.7` cho DS18B20 DATA.

Không thể cùng lúc là bus 1-Wire và enable nửa cầu. Đây là **`TEAM_DEPENDENCY / BLOCKER`**:

- Không tự đổi pinout/firmware/dây.
- **Nghiêm cấm cấp nguồn tải/TEC (energize)** khi xung đột GPIO10 chưa được giải quyết và phê duyệt.
- D + leader xác nhận as-built thật (sơ đồ hoặc đo continuity từ chân module tới GPIO).
- Nếu `GPIO10 = L_EN` là đúng, phải chọn chân khác cho DS18B20 hoặc L_EN và bump
  `pin_map_version`; nếu không, đính chính as-built.
- Cho tới khi chốt, mọi kết luận "default OFF an toàn" chỉ là quan sát trên bench logic.

Chi tiết TEST 133B: `test-133b-reset-default-off.md`.

## 4. Shunt / return path

| Hạng mục | As-built | Nguồn |
|---|---|---|
| Shunt | `50 A / 75 mV`, nhãn **in**; khắc `FL-2 0.5` | Ảnh W01 18/04 |
| Vị trí | Đường hồi giữa `IBT-2 B−` và `PSU−` | Operator |
| `B−` ↔ `GND logic` | `≈ 0 Ω` (common) | Operator continuity |
| Shunt hở | `B−` ↔ `PSU−` từng đo `≈ 453 kΩ` | Operator |
| Dòng quan sát | `≈ 0.98 A` ở PWM 10% thời gian ngắn | Operator/PZEM |

Failure mode khi shunt hở và yêu cầu D: `shunt-continuity.md`.

## 5. Khác biệt so với freeze (không tự hợp thức hóa)

| Ref | Frozen | As-built | Trạng thái |
|---|---|---|---|
| `CR-A-W01-01` | MAX3485 3.3 V | TTL485-V2.0 5 V auto-direction | **PENDING (D + leader)** |
| `CR-A-W01-02` | TB4504 45 A 4P | TB4506 6 vị trí | **PENDING (D + leader)** |
| `CR-A-W01-03` | PCT-218 ×1 | 4 chiếc (operator) | PENDING (leader) |
| `CR-A-W01-04` | DS18B20 ×3 | 4 đầu dò (operator) | PENDING (leader) |
| Pin map | `docs/01 §11.7` | thêm `L_EN=GPIO10`, `LPWM=GND` | **PENDING + xung đột GPIO10** |
| `hardware_config_id` | — | `NOT_ASSIGNED` | Leader |

## 6. Điều task này không làm

- Không đổi dây, không đổi shunt, không đổi module RS-485.
- Không sửa frozen BOM.
- Không freeze pin map.
- Không đánh dấu approval thay D/leader.
