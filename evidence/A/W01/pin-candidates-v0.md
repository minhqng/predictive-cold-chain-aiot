# A-W01-03 — Candidate board pin map v0 (KHÔNG PHẢI PIN MAP ĐÃ ĐÓNG BĂNG)

**Board:** dual ESP32-S3R2 + W25Q32 + CH343G; silkscreen `MAKDRIVERONE` đã xác nhận bằng ảnh 20 (bộ 25 ảnh); sơ đồ mạch/PCB revision **chưa có**. **Trạng thái:** candidate / đã thử trên bench một phần.

Nguồn bằng chứng:

- `BENCH_TESTED_REPORTED` — người dùng báo đã chạy trên bench; kết quả **chưa được agent tái lập độc lập**.
- `SILKSCREEN` — nhìn thấy trên ảnh hoặc silkscreen board.
- `MUST_TEST` / `UNKNOWN` — chưa có bằng chứng.

Phân loại theo `docs/05A §10`: `known` / `likely` / `unknown` / `must test`.

| Signal / function | Candidate ESP32 pin | Classification | Evidence (provenance) | Remaining check |
|---|---|---|---|---|
| DS18B20 shared 1-Wire data | **GPIO10** | known (bench) | `BENCH_TESTED_REPORTED`: 4 ROM ID 64-bit duy nhất đọc được qua GPIO10 | Xác nhận lại bằng log có timestamp; ghi ROM → vai trò T1/T2/T3 ở W02 |
| MC-38 door reed | **GPIO34** | known (bench) | `BENCH_TESTED_REPORTED`: 24 chu kỳ đóng/mở quan sát được | Ghi lại chân vật lý, cực tính pull-up và debounce; lưu log chu kỳ |
| UART TX → TTL485 RXD | **GPIO36** | known (bench) | `BENCH_TESTED_REPORTED`: UART 36/37 và Modbus 9600 trả lời hợp lệ | Xác nhận đúng chip ESP32 nào của board dual và đường mux của board |
| UART RX ← TTL485 TXD | **GPIO37** | known (bench, có phân áp) | `BENCH_TESTED_REPORTED`: TXD idle 5 V, đầu ra phân áp ~3.314 V **đo được** (tính toán ≈ 3.33 V), PZEM trả lời CRC hợp lệ | Không đi dây 5 V trực tiếp; duyệt thiết kế level-shift chính thức cho production |
| Common logic GND | GND trên ESP32 | known | `BENCH_TESTED_REPORTED`: GND chung qua TB4506, UART test thành công | Kiểm tra tuyến cáp và topology star/bus |
| BME280 I²C SDA | UNKNOWN | must test | Chưa hàn header nên chưa cấp điện | Test nguồn 3.3 V, SDA, pull-up |
| BME280 I²C SCL | UNKNOWN | must test | Chưa hàn header nên chưa cấp điện | Test nguồn 3.3 V, SCL, pull-up |
| BTS7960 RPWM | UNKNOWN | must test | `BENCH_TESTED_REPORTED`: logic ra mức thấp/cao quan sát được, nhưng chưa ghi lại số chân | Chốt GPIO; kiểm trạng thái mặc định OFF khi reset/brownout |
| BTS7960 LPWM | UNKNOWN | must test | `BENCH_TESTED_REPORTED`: logic ra mức thấp/cao quan sát được, nhưng chưa ghi lại số chân | Chốt GPIO; kiểm trạng thái mặc định OFF khi reset/brownout |
| BTS7960 R_EN | UNKNOWN | must test | `BENCH_TESTED_REPORTED`: đã lắp pull-down 10 kΩ, chưa ghi lại số chân | Chốt GPIO; đo qua reset/brownout |
| BTS7960 L_EN | UNKNOWN | must test | `BENCH_TESTED_REPORTED`: đã lắp pull-down 10 kΩ, chưa ghi lại số chân | Chốt GPIO; đo qua reset/brownout |
| PSU/PZEM analog sense | không dùng GPIO | n/a | PZEM-017 giao tiếp Modbus qua RS485, không dùng ADC | Giữ nguyên: không đọc shunt bằng ADC |

## Ràng buộc ESP32-S3R2 cần kiểm chứng trước khi đóng băng

Đây là **danh sách phải kiểm chứng**, không phải kết luận:

- Board dual ESP32-S3: chưa xác định GPIO36/GPIO10/GPIO34 thuộc chip nào và có bị board mux hay chia sẻ với chip còn lại hay không.
- Chân strapping của ESP32-S3 có ảnh hưởng tại thời điểm boot; phải đối chiếu trước khi gán actuator hoặc relay.
- Bộ nhớ trong gói ESP32-S3R2 và flash W25Q32 dùng chung nhóm chân SPI; phải đối chiếu datasheet Espressif và silkscreen trước khi gán GPIO.
- Chưa có sơ đồ nhà bán: mọi pin ở trên chỉ là **candidate**, không phải thiết kế đã duyệt.

## Ghi chú đấu dây, **chỉ dùng cho bench**

Số thứ tự TB4506 theo người dùng báo (trái sang phải ở hướng đang quan sát):

- **#1** TTL485 `TXD` (5 V) → điện trở 10 kΩ R1.
- **#2** điểm ra phân áp vào ESP32 **GPIO37** (R1/R2 nối nhau).
- **#3** điểm nối trung gian R2/R3.
- **#4/#5** nối GND (đầu R3); **#5** là GND chung.
- **#6** +5 V từ XL4015 cấp cho logic TTL485/PZEM.

Phân áp đường RX: `TTL485 TXD(5V) ─10k─ GPIO37 ─10k─10k─ GND`; giá trị **tính** theo phân áp ≈ 3.33 V, giá trị **đo** (người dùng báo) ≈ 3.314 V khi không tải. Hai con số này **không** mâu thuẫn: 3.33 V là kết quả tính, 3.314 V là số đọc trên đồng hồ. ESP32 TX GPIO36 đi trực tiếp vào TTL485 RXD ở mức 3.3 V: **đã quan sát hoạt động nhưng chưa chứng minh được mức logic cao theo datasheet IC**. Vì `TTL485-V2.0` thay thế `MAX3485` đã freeze, đây là đấu nối tạm đã được khảo sát, **không phải thiết kế đã được duyệt**.

Linh kiện ngoài BOM đang dùng trên bench: 3 × 10 kΩ cho phân áp TTL485. Không được tính các điện trở này thay cho điện trở 4.7 kΩ pull-up của DS18B20 trong `bom-audit.csv` HW-23.

**Không đóng băng GPIO trong W01:** sơ đồ nhà bán, routing chip và toàn bộ GPIO vật lý, nguồn RS485 và chân boot an toàn của IBT-2 phải được xác minh độc lập trước khi W02/W03 được nghiệm thu.
