# ColdGuard Member A — W23 Runbook & Sơ đồ as-built (bản hiệu chỉnh v2)

**Ngày đối chiếu:** 08/11/2026. **Hardware config:** CG-HW-001, pin map v2. **Phạm vi:** A-W23-01/W23-02, tài liệu tham chiếu vận hành và sơ đồ chức năng; không phải bản chứng nhận ampacity hoặc hồ sơ nghiệm thu đã có chữ ký.

## 1. Tệp kèm

- `ColdGuard_W23_power_v2.png` / `.svg`: sơ đồ nguồn và đường hồi công suất.
- `ColdGuard_W23_signals_v2.png` / `.svg`: sơ đồ tín hiệu ESP32-S3.
- `ColdGuard_W23_so_do_day_va_runbook_v2.pdf`: bản in 5 trang, có bảng trạng thái bằng chứng.

## 2. Cấu hình nguồn thực tế đã ghi nhận

| Vị trí/nhánh | Kết nối và thông số | Lớp bằng chứng |
|---|---|---|
| Hộp ATO khe 1 | 5 A: PSU+ → XL4015 (12 V → ~5 V logic) | Operator confirmed |
| Hộp ATO khe 2 | 1 A: PSU+ → PZEM-017 | Operator confirmed |
| Hộp ATO khe 3 | 15 A: PSU+ → IBT-2 B+; M+/M− → TEC | Operator confirmed; ampacity **not** certified |
| Hộp ATO khe 4 | 1 A: PSU+ → quạt V1 12 V riêng | Operator confirmed |
| Return dòng TEC | IBT-2 B− → shunt 50 A/75 mV → PSU− | Operator topology + continuity observed |
| Dây GND nối tắt | Đã tháo dây IBT-2 GND → cọc A/PSU− riêng | Operator confirmed |
| Nhánh logic | XL4015 → TB4506/phân phối 5 V; khoảng 4,99–5,01 V từng được báo | Operator measurements |

**Phép đo return:** Khi nối shunt, IBT-2 B− ↔ PSU−: **0,2 Ω** trên đồng hồ, que chập **0,1 Ω**. Đây là phép kiểm tra thông mạch, không phải kết quả đo milliohm chính xác của shunt. Ở trạng thái thử tách shunt cũ, phép đọc từng là OL/khoảng 453 kΩ tùy cấu hình. B− vẫn common với GND logic của module; tháo dây nối tắt ngoài không làm B− cách ly tuyệt đối. **Chưa xác minh đường dòng khi đầu shunt bị lỏng/hở**, do đó không được ghi là đã nghiệm thu fault tolerance.

**Dây TEC:** ngày 02/11 operator sửa đơn vị: `1,75 mm` là **đường kính lõi đồng**, không phải `1,75 mm²`. Nếu thực sự là một lõi đồng tròn đặc, diện tích tính toán π×(1,75/2)² ≈ **2,405 mm²**. Đây là phép suy tính có điều kiện, không chứng nhận dây danh định 2,5 mm². Chưa có căn cứ đủ cho ampacity theo lớp cách điện, số sợi, đường đi/bó dây và nhiệt độ; **không tự suy** cầu chì 15 A phù hợp chỉ vì dòng H8 từng đạt đỉnh 9,99 A.

**Cọc TB4506:** biết chức năng nguồn và đường phân phối, nhưng chưa có ảnh/biên bản đánh số lần lượt từng vị trí vật lý trên TB4506. Đừng biến thứ tự hộp ATO thành thứ tự cọc TB4506.

## 3. ESP32-S3 pin map v2 / giao tiếp

| Tín hiệu | Đấu nối as-built |
|---|---|
| DS18B20 | GPIO33 DATA, 4 ROM (T1, T2, T3, SPARE) |
| BME280 | GPIO21 SDA, GPIO34 SCL |
| MC-38 | GPIO35 |
| RS-485 | GPIO36 TX → TTL485 RXD; GPIO37 RX ← TTL485 TXD **qua phân áp** |
| IBT-2 | GPIO5 RPWM; GPIO6 R_EN; GPIO10 L_EN; LPWM nối GND |
| W21 debug console | USB-Serial/JTAG ở firmware a54ba24, **không** đọc lệnh từ UART_NUM_0 |

**RS-485:** TTL485-V2.0 là module 5 V có tự chuyển chiều (không có DE/RE), nguồn logic từ rail XL4015; PZEM Modbus 9600 8N1, slave 0x01. Phía GPIO37 được báo dùng **3×10 kΩ** phân áp; W01 ghi **khoảng 3,314 V tại GPIO37** (do operator đo/báo), một lần kiểm tra khác báo **3,333 V** nhưng không có ảnh/điểm đo đủ rõ để coi là phép đo cùng nút. Các số đo không tự xác nhận mọi trạng thái điện và tính tương thích 5 V lâu dài; không gộp với FAIL BOM A-W03-02.

## 4. Demo W23-01 — 8 bước

1. **Visual inspection:** quan sát chamber, đầu nối, fuse, dây, quạt, nhãn và cảm biến; ghi các bất thường.
2. **Power-on:** dùng cấu hình được cho phép; xác nhận boot ID và `applied=OFF`, không tự ARM/START.
3. **Sensor check:** T1/T3/SPARE là cảm biến trong thùng; T2 là hot side; BME280 (nếu image có driver), MC-38; theo dõi quality.
4. **PZEM check:** xem dữ liệu V/I/P/Wh, trạng thái, `seq/age`; phân biệt `INVALID` và số 0 thật.
5. **Broker/device:** chỉ đánh giá khi phần C/D hiện thực và tích hợp; nếu thiếu ghi `NOT_RUN`.
6. **Short legal actuation:** chỉ khi có profile TEC ON phù hợp và người giám sát. W21 test image output stage `DISABLED` không đáp ứng ON.
7. **Demo scene:** thực hiện protocol đúng, thu raw telemetry, firmware hash/boot ID và lưu cả attempt lỗi.
8. **Safe shutdown:** STOP/ESTOP nếu cần, xác nhận OFF, cooldown fan, ngắt PSU theo quy trình phiên, seal manifest.

## 5. Checklist và xử lý sự cố

- [ ] Đúng firmware/profile/boot_id và một chủ sở hữu cổng USB/COM4.
- [ ] Output bắt đầu OFF; không tự bật TEC.
- [ ] Cảm biến T1/T2/T3/SPARE, BME280, MC-38, PZEM có quality/status được ghi.
- [ ] Phép thử TEC ON phải được cho phép, không dùng W21 image compile-out để tuyên bố ON.
- [ ] Lỗi: STOP/ESTOP; bảo toàn raw log và lần thử không hợp lệ.
- [ ] Kết thúc OFF, để quạt cooldown khi cần; niêm phong SHA-256 và firmware/boot provenance.

| Hiện tượng | Xử lý |
|---|---|
| W21 `FAULT` không nhận | Kiểm tra firmware a54ba24 dùng USB-Serial/JTAG (không tự chuyển UART0). |
| Một DS18B20 invalid | Ghi ROM/role, không tự remap; nếu đang injection thì `FAULT CLEAR` và xác minh phục hồi. |
| PZEM `INJECT_DISABLED` | Đây là transport injection có chủ ý, không phải timeout vật lý tự nhiên. |
| PZEM `INVALID/nan` | Phân biệt PSU OFF/CRC/timeout/injection; không reuse sample cũ như fresh. |
| Quạt/hot side bất thường | Dừng TEC và ghi log, không tiếp tục chạy chỉ để PASS. |
| Boot ID thay đổi | Kết thúc attempt hiện tại; không ghép các boot. |

## 6. Nguồn đối chiếu

- `evidence/A/as-built-pinmap-2026-10-27.md` — pin map v2, rail logic, return path.
- `evidence/A/W03/hardware-2026-10-27/as-built-configuration.md` — fuse rails, TTL485, shunt.
- `evidence/A/W03/hardware-2026-10-27/shunt-continuity.md` — continuity và nguy cơ shunt hở.
- `evidence/A/W04/fuse-commissioning-note.md` — cầu chì 15 A và giới hạn ampacity.
- `evidence/A/W08/fuse-selection.md` — hiệu chỉnh đường kính lõi 1,75 mm → 2,405 mm² có điều kiện.
- `docs/05A-member-a-embedded-thermal.md` (W23), `docs/01`, `docs/03` — yêu cầu canonical.

**Trạng thái:** Tài liệu hướng dẫn đã soạn. Không tự xác nhận ảnh vật tư W23-02, 3 lần diễn tập W23-04 hoặc bàn giao người thứ hai W24-03.
