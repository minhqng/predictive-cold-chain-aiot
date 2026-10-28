# As-built pin map — ColdGuard CG-HW-001 (map v2, bench 2026-10-25..27)

**Trạng thái: `AS-BUILT RECORDED — PHYSICAL CONTINUITY NOT MEASURED`**
**Ngày ghi hồ sơ: 2026-10-28, từ các phiên bench 2026-10-25..27.**

Đây là **một** bản đồ chân hiệu lực duy nhất cho CG-HW-001. Nó thay thế bảng
"Proposed GPIO mapping v1" trong `docs/01 §11.7` (bảng cũ được giữ nguyên làm
lịch sử, chỉ thêm ghi chú supersession có ngày). Firmware W02/W03, checker tĩnh
và tài liệu đang hoạt động phải trỏ về tệp này.

Tệp này **không** freeze BOM và **không** tuyên bố đã đo continuity từ chân module
tới GPIO; đây là bản ghi bản đồ theo lời khai/đo bench, không phải biên bản phê duyệt.

## 0. Lớp bằng chứng (không nâng cấp ngầm)

| Lớp | Nghĩa trong tệp này |
|---|---|
| `MEASURED` | Số đo/khung dữ liệu thật do người vận hành báo từ bench |
| `SOURCE VERIFIED` | Đọc từ ảnh/marking/ datasheet Espressif đã đối chiếu |
| `USER REPORTED` | Người vận hành khai báo, agent chưa tái lập độc lập |
| `INFERRED` | Suy ra từ dữ kiện khác, chưa đo trực tiếp |
| `NOT VERIFIED` | Chưa có bằng chứng |

Mọi dòng trong bảng chân đều ghi lớp bằng chứng. Một dòng `USER REPORTED`
không được đọc như `MEASURED`.

## 1. Nhận dạng phần cứng

| Hạng mục | Giá trị | Lớp | Nguồn |
|---|---|---|---|
| Board | `MAKDRIVERONE` dual ESP32-S3 + CH343G | `SOURCE VERIFIED` | Ảnh W01 bộ 25 ảnh, silkscreen |
| MCU | ESP32-S3R2 (2 MB Quad in-package PSRAM) | `SOURCE VERIFIED` | `docs/01 §11.2`, ảnh marking |
| Flash | W25Q32 (Quad, SPI0/1) | `SOURCE VERIFIED` | `docs/01 §11.2` |
| `hardware_config_id` | `CG-HW-001` (firmware); as-built W03 vẫn `NOT_ASSIGNED` | `NOT VERIFIED` | `evidence/A/W03/hardware-2026-10-27/as-built-configuration.md` §5 |

## 2. Bản đồ chân hiệu lực (map v2)

`CG_PIN_MAP_VERSION = 2`. Một macro chuẩn cho mỗi chức năng; các tên cũ chỉ còn
là alias tương thích (`CG_PIN_IBT2_ENABLE → CG_PIN_IBT2_REN`,
`CG_ACTUATOR_ENABLE_PIN → CG_ACTUATOR_REN_PIN`).

| Chức năng | Macro chuẩn | GPIO | Hướng | Module sở hữu | Lớp bằng chứng |
|---|---|---|---|---|---|
| DS18B20 DATA (1-Wire) | `CG_PIN_DS18B20_DATA` | **33** | open-drain I/O | `cg_onewire.c` / `cg_ds18b20.c` | `MEASURED` (TEST 129D: 4 ROM đọc trên bus 33) |
| BME280 SDA | `CG_PIN_BME280_SDA` | **21** | I²C data | bench Arduino (không có driver ESP-IDF) | `USER REPORTED` |
| BME280 SCL | `CG_PIN_BME280_SCL` | **34** | I²C clock | bench Arduino | `USER REPORTED` (header hàn lại, chuyển từ 33 sang 34) |
| MC-38 door reed | `CG_PIN_MC38` | **35** | input, pull-up nội | `cg_door.c` | `USER REPORTED` (24 chu kỳ bench) |
| RS-485 TX → TTL485 RXD | `CG_PIN_UART_TX_TO_MAX3485_DI` | **36** | UART1 TX | `cg_rs485.c` | `MEASURED` (Modbus trả lời hợp lệ) |
| RS-485 RX ← TTL485 TXD | `CG_PIN_UART_RX_FROM_MAX3485_RO` | **37** | UART1 RX, qua phân áp 10k/10k/10k | `cg_rs485.c` | `MEASURED` (~3.314 V tại GPIO37) |
| IBT-2 RPWM | `CG_PIN_IBT2_COOLING_PWM` | **5** | output, chỉ ghi 0 (W03) | `cg_actuator.c` | `USER REPORTED` |
| IBT-2 R_EN | `CG_PIN_IBT2_REN` | **6** | output, chỉ ghi 0 (W03) | `cg_actuator.c` | `USER REPORTED` |
| IBT-2 L_EN | `CG_PIN_IBT2_LEN` | **10** | output, chỉ ghi 0 (W03) | `cg_actuator.c` | `USER REPORTED` |
| IBT-2 LPWM | — (GND) | — | tie GND trên module | không do firmware điều khiển | `USER REPORTED` |
| IBT-2 R_IS / L_IS | — | — | không đấu | — | `USER REPORTED` |

Không còn chức năng nào khác chiếm GPIO. GPIO10 **không** còn là DS18B20 DATA;
GPIO34 **không** còn là MC-38; GPIO33 **không** còn là BME280 SCL.

## 3. Chân bị chặn theo profile ESP32-S3R2 (Quad PSRAM)

| Dải | Ý nghĩa | Quy tắc |
|---|---|---|
| GPIO26–32 | SPI0/1 flash bus (W25Q32) | **Cấm** gán ngoại vi |
| GPIO33–37 | Trống trên S3R2 Quad; bị chiếm trên S3R8/S3R8V Octal | Cho phép **chỉ khi** `CG_HW_PSRAM_OCTAL = 0` |
| GPIO0/3/45/46 | Strapping pins | **Cấm** gán ngoại vi |
| GPIO19/20 | USB-JTAG/Serial native (nếu dùng USB nội) | Không dùng trong map này |

Các quy tắc trên được thực thi **hai lần**: `#error` tại biên dịch trong
`coldguard_config.h`, và `firmware/tools/cg_gpio_map.py` trong checker/unit test.
Bản sao Python dùng cùng bảng `AS_BUILT_PINS`, nên một thay đổi chân không cập
nhật tài liệu sẽ làm checker fail.

## 4. IBT-2 / TEC — trạng thái an toàn và lịch sử GPIO10

- Đấu dây: RPWM=5, R_EN=6, L_EN=10; LPWM nối GND; R_IS/L_IS không đấu.
- Trạng thái OFF dự định: **RPWM LOW, R_EN LOW, L_EN LOW, LPWM vật lý LOW**.
- Firmware W03: `cg_actuator_force_off()` cấu hình cả 3 chân là output, xóa
  **R_EN và L_EN trước**, rồi ghi RPWM=0. Không có PWM (không LEDC/MCPWM),
  không đường nào ghi mức 1 lên 3 chân này. `CG_ACTUATOR_ENABLE_ALLOWED = 0`.
- Lịch sử: map v1 (và `docs/01 §11.7`) **cấu hình** GPIO10 cho DS18B20 DATA, trong khi
  lời khai as-built đặt **L_EN trên GPIO10**. Đây là **lệch giữa cấu hình firmware và
  lời khai đấu dây**, không phải bằng chứng hai dây cùng nằm trên một chân — chưa có
  phép đo continuity. Vì W02 đọc được 4 ROM với cấu hình `GPIO10 = DATA`, trong các
  phiên đó chân này đang phục vụ 1-Wire. Map v2 xử lý ở mức cấu hình: DS18B20 sang
  GPIO33 (đã đọc 4 ROM trên bus 33), giữ L_EN=10. **Không** cần đổi dây IBT-2.
- Ghi chú: TEST 133B chỉ in chuỗi hằng `RPWM/R_EN/L_EN LOW`, không đọc lại chân;
  cold-boot thật vẫn `RAW_EVIDENCE_NOT_AVAILABLE`. Vì vậy trạng thái OFF mới được
  chứng minh ở mức **phần mềm + kiểm tra tĩnh**, chưa phải log phần cứng.

## 5. Nguồn / shunt (không thay đổi trong nhiệm vụ này)

| Hạng mục | As-built | Lớp |
|---|---|---|
| Nhánh TEC (TEC OFF) | `11.94–11.95 V` (TEST 132B) | `MEASURED` |
| XL4015 ra | `5.00 V` | `USER REPORTED` |
| TB4506 rail | `4.99 V` | `USER REPORTED` |
| Shunt | `50 A / 75 mV`, khắc `FL-2 0.5` | `SOURCE VERIFIED` (ảnh 18/04) |
| Vị trí shunt | đường hồi giữa `IBT-2 B−` và `PSU−` | `USER REPORTED` |
| `B−` ↔ GND logic | `≈ 0 Ω` | `USER REPORTED` |
| Dòng quan sát | `≈ 0.98 A` @ PWM 10%, thời gian ngắn | `USER REPORTED` |

Không có thay đổi phần cứng nguồn, shunt, hay module RS-485 trong nhiệm vụ này.

## 6. RS-485 / PZEM

- Module as-built: **TTL485-V2.0**, 5 V, auto-direction, header `GND/RXD/TXD/VCC`
  — **không có DE/RE**. Khác biệt với MAX3485 đã freeze: `CR-A-W01-01` vẫn PENDING (change review).
- `CG_RS485_DIR_MODE = 0` (AUTO). MANUAL chỉ là compile-time option cho MAX3485
  canonical; chân DE/RE mặc định là GPIO35 và **bị `#error` nếu chọn MANUAL** vì
  GPIO35 là MC-38 door input. Muốn dùng MANUAL phải chọn chân trống khác.
- Framing 9600 8N1, slave 0x01, chỉ đọc (FC03/FC04). Không có FC06.
- Không nối 5 V trực tiếp vào GPIO37.

## 7. Thay đổi so với map v1 và căn cứ

| Tín hiệu | v1 (`docs/01 §11.7`) | v2 (tệp này) | Căn cứ |
|---|---|---|---|
| DS18B20 DATA | 10 | **33** | TEST 129D đọc 4 ROM trên 33 |
| BME280 SDA | 21 | 21 | không đổi |
| BME280 SCL | 33 | **34** | header BME280 hàn lại; 33 nhường DS18B20 |
| MC-38 | 34 | **35** | as-built operator + 24 chu kỳ |
| RS-485 DE/RE | 35 | **không dùng (AUTO)** | TTL485-V2.0 không có DE/RE; 35 là MC-38 |
| RS-485 TX/RX | 36/37 | 36/37 | không đổi |
| IBT-2 RPWM | 5 | 5 | không đổi |
| IBT-2 EN | 6 | 6 (R_EN) | không đổi |
| IBT-2 L_EN | (không có) | **10** | as-built operator; lệch cấu hình cũ với DS18B20 đã xử lý ở map v2 |

## 8. Giới hạn xác minh (phải giữ nguyên nhãn)

1. **Chưa** có đo continuity từ chân module tới GPIO; chưa có sơ đồ nhà bán.
2. BME280 SDA/SCL là `USER REPORTED`; chưa có log I²C của firmware (W02 cố ý
   không thêm driver BME280).
3. MC-38 polarity (mức raw nào = OPEN) **chưa** commissioned;
   `CG_DOOR_POLARITY_CONFIRMED = 0`.
4. RPWM/R_EN/L_EN là `USER REPORTED`; chưa có scope/logic analyzer trên chân.
5. `hardware_config_id` as-built của W03 vẫn `NOT_ASSIGNED`.
6. Không có thay đổi vật lý nào được thực hiện bởi nhiệm vụ hòa giải này.

## 9. Nguồn tham chiếu

- `evidence/A/W01/pin-candidates-v0.md` (map v0, đã superseded — xem ghi chú đầu tệp).
- `evidence/A/W01/hardware-audit-w01.md`, `bom-audit.csv`, `photo-inventory.csv`.
- `evidence/A/W02/sensor-rom-map.yaml`, `evidence/A/W02/acceptance.md`.
- `evidence/A/W03/ibt2-pin-map.md`, `hardware-2026-10-27/as-built-configuration.md`,
  `rs485-pin-and-compatibility.md`, `test-133b-reset-default-off.md`,
  `provenance-matrix.md`.
- `docs/01-physical-measurement-correctness-contract.md` §11.2/§11.4/§11.8.
- Firmware: `firmware/main/coldguard_config.h`, `firmware/tools/cg_gpio_map.py`
  (host validator).
