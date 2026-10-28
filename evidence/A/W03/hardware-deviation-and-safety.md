# W03 — Hardware deviation and safety boundaries (Member A)

> **Cập nhật 2026-10-28:** map v2 (`evidence/A/as-built-pinmap-2026-10-27.md`)
> xử lý lệch cấu hình `GPIO10` ở mức firmware và thêm safe-OFF 3 chân
> (RPWM/R_EN/L_EN). File này **không** thay đổi bất kỳ ràng buộc an toàn điện nào:
> `CR-A-W01-01`, tie-off `LPWM`/`L_EN`, cold-boot log vẫn `MEASUREMENT REQUIRED`.

**Không phải chứng nhận an toàn.** Đây là bản ghi các lệch phần cứng đang mở và ranh giới W03 không được vượt qua. Kế thừa W01 `freeze-deviation-review.md` + `physical-risk-ledger.md`.

## 1. RS-485: TTL485-V2.0 thực tế vs MAX3485 đã freeze — CR-A-W01-01

| Mục | Canonical freeze (HW-07) | Thực tế as-built (ảnh W01 + người dùng báo) |
|---|---|---|
| Module | MAX3485 3.3 V | **TTL485-V2.0**, rail logic **5 V** |
| Chip | MAX3485 (3.3 V) | người dùng báo `MAX13487ESA`; **marking chưa đọc được trong bất kỳ ảnh nào** (W01 acceptance #7 = PARTIAL) |
| Hướng | DE//RE điều khiển bằng GPIO | **auto-direction**, không có chân DE//RE trên header `GND/RXD/TXD/VCC` |
| Mức RX | RO 3.3 V đấu thẳng | TXD idle **5 V** theo báo cáo; phân áp tạm 10k/10k/10k → ~3.314 V **đo được** (vận hành W01), tính ≈ 3.33 V |

**Trạng thái:** `MEASUREMENT REQUIRED` — change review `CR-A-W01-01` đang mở (W01 `freeze-deviation-review.md`).

**Quy tắc W03 (bắt buộc):**

1. **Không** đấu 5 V trực tiếp vào GPIO nào của ESP32.
2. **Không** giả định RO/chân trả lời là 3.3 V khi chưa có datasheet/marking xác thực (không được suy luận từ báo cáo người dùng).
3. Phân áp 10k/10k/10k hiện tại là **đấu nối tạm đã được khảo sát**, không phải thiết kế production.
4. Chỉ chạy bất kỳ bài UART **sau khi** có phép đo xác nhận mức ≤3.3 V ở GPIO37; firmware W03 không tự bật bất kỳ thử nghiệm nào (không có chế độ test UART trong build mặc định).
5. Firmware mặc định `CG_RS485_DIR_MODE 0` = **AUTO** (đúng cho module auto-direction hiện có). Nhánh MANUAL (GPIO35) chỉ tồn tại như compile-time option cho module MAX3485 canonical và bị `#if` loại khỏi build mặc định — không có code "chạy thử" chạm GPIO35 trong build này.

## 2. Rủi ro kế thừa đang mở (W01 risk ledger)

| ID | Rủi ro | Trạng thái W01 | W03 làm gì thêm |
|---|---|---|---|
| R01 | Đảo cực DC | OPEN | Firmware PZEM không đổi cực tính; cấm cấp tải khi chưa đo cực tính (plan trong `logic-power-measurement.md`) |
| R02 | Ngắn mạch nguồn 33 A / dây nhỏ hơn định mức | OPEN | Không cấp TEC; mọi bài W03 chỉ ở nhánh logic ≤5 V |
| R05 | Shunt đấu sai, nối tắt +12 V/0 V | NOT_TESTED | `A-W03-06`: chỉ kiểm tra bằng mắt khi nguồn OFF, không cấp tải qua shunt trong W03 |
| R06 | IBT-2 bật khi boot/reset | OPEN | `A-W03-07`: firmware ép OFF đầu tiên, không PWM, chỉ ghi 0; cold-boot log vẫn **PENDING** |
| R09 | USB back-feed / vòng GND | OPEN | Không cấp nguồn ngoài cho PZEM trong W03 |
| R10 | Sai miền nguồn/mức logic RS-485 | OPEN / HARDWARE DRIFT | Mục 1 ở trên; là blocker của A-W03-02 |
| R13 | Suy dòng TEC từ tên linh kiện | NOT_TESTED | `ibt2-pin-map.md` §4: không suy định mức liên tục từ `43 A` |
| R16 | Kết quả test bị gán ý nghĩa mạnh hơn bằng chứng | OPEN | Bộ hồ sơ này tách 5 nhãn trạng thái; validator chỉ kiểm tra cấu trúc, không xác nhận vật lý |

## 3. Ranh giới an toàn W03 (điều W03 cố ý KHÔNG làm)

- **Không cấp nguồn TEC, không chạy tải dòng lớn** (đúng tinh thần "without unsafe TEC escalation" của `docs/05A §12`).
- **Không** chạy bất kỳ bài UART phần cứng nào khi mức logic RS-485 chưa được đo/xác nhận.
- **Không** ghi register PZEM (không đổi profile, không đổi slave address qua bus).
- **Không** tạo PWM; **không** tồn tại đường code nào ghi mức 1 lên `RPWM`/`ENABLE`.
- **Không** nâng bất kỳ trạng thái nào từ ảnh/unit test: mọi bài cần đo đều `MEASUREMENT REQUIRED`.

## 4. Điều kiện dừng bắt buộc (kế thừa W01, còn hiệu lực)

- Cực tính không chắc, đầu nối ấm/nóng, tia lửa, mùi lạ, PSU hành xử bất thường, fuse nổ hoặc dây lỏng → **ngắt điện lưới** và điều tra.
- Không bắc cầu fuse, không nối tắt PSU để mô phỏng lỗi, không cấp TEC khi quạt/tản nhiệt chưa hoạt động, không dùng jumper mảnh làm dây công suất.
- **W03 không cho phép bất kỳ lần chạy tải dòng lớn nào.** Mọi bài đo W03 chỉ được thực hiện khi có người thứ hai giám sát, theo checklist tương ứng trong từng file.

## 5. Bench archive 2026-10-20 — phân biệt xác nhận của người vận hành với phép đo

Archive `hardware-2026-10-20/` chỉ là bằng chứng phụ của một phiên Arduino. Nó **không**
thay đổi CR-A-W01-01 và không nâng bất kỳ mục nào trong `acceptance.md`.

| Nội dung | Cách ghi đúng | Không được suy diễn |
|---|---|---|
| TEC OFF trong phiên OFF10 | **Xác nhận của người vận hành** (operator assertion), không được đo độc lập | Không coi là TEC OFF đã chứng minh; 594 mẫu hợp lệ ghi `current_a=0.00` không tự chứng minh TEC không được cấp nguồn |
| IBT-2 VCC ≈ 5 V, bốn chân EN/PWM ≈ 0 V | **Số đo tay của người vận hành** tại thời điểm đó | Không phải log boot/reset/watchdog; không phải bằng chứng cold-boot default-OFF |
| B+/B−/M+/M− đang tháo | **Trạng thái do người vận hành báo** | Không chứng minh module không thể bật khi reset, không chứng minh tie-off |
| Shunt `raw=0x0001` | Log văn bản Arduino; **không có raw FC03 tx/rx**, không có CRC host-side | Không phải A-W03-04 readback; không chứng minh tải 50 A |
| 601 mẫu, 594 `CRC_VALID`, 7 `INVALID` | Kết quả của sketch Arduino V4, gate `COLLECTED_WITH_ERRORS` | Không phải ESP-IDF W03; không chứng minh patch sửa 7 lỗi |

Không có thử tải **50 A thật** và không có lần chạy **ESP-IDF W03** trên board trong
archive này. 594 mẫu hợp lệ đều ghi `current_a=0.00`; 7 mẫu lỗi để trống. Đây chỉ là
quan sát, không phải phép đo tải.

**FC06:** `firmware/ColdGuard_W03_TTL485_SET50A_ONCE_8N1.ino` và `raw/w3testlog.txt` chứa
lệnh FC06. Đây là vật liệu **`ARCHIVE ONLY — DO NOT FLASH OR EXECUTE`**: không nạp lại,
không gửi FC06, không dùng làm bằng chứng W03. Sai lệch quy trình bench được ghi ở
`TD-W03-07` và phải được mô tả/xử lý trong hồ sơ.

**Phân áp:** nhãn `via_existing_5k_10k_divider` trong log là do sketch in, không phải kết
luận topology. Không được gọi các điện trở 10 kΩ (hoặc mắc song song) là "5 kΩ" khi chưa
kiểm tra sơ đồ; giá trị tương đương thay đổi theo cách mắc. Mạch 10k/10k/10k hiện tại vẫn
là đấu nối tạm chưa được đo lại độc lập.

## 6. Phiên bench 2026-10-27 — cùng quy tắc, thêm ba rủi ro mới

Phiên TEST 131/132B/133B **không** thay đổi CR-A-W01-01 và **không** nâng bất kỳ mục nào
trong `acceptance.md`. Nó thêm ba điểm phải theo dõi:

| Nội dung | Cách ghi đúng | Không được suy diễn |
|---|---|---|
| TEST 132B: 600/600 hợp lệ, `11.94–11.95 V`, log tự gate `REVIEW REQUIRED` | Sketch Arduino bench; `MEASURED — BENCH ARTIFACT` trong phạm vi file | Không phải firmware W03; không phải PASS; `I=0.00 A` chỉ dưới độ phân giải |
| TEST 131: `01 03 02 00 01 79 84`, CRC `0x8479` khớp | `OPERATOR-REPORTED` frame đã kiểm CRC host-side | Không có capture gốc → không phải evidence-grade readback |
| `B−` ↔ `GND logic` ≈ `0 Ω` (as-built) | Số đọc DMM của người vận hành | **Failure mode mở**: shunt hở có thể đẩy dòng hồi qua GND logic → D quyết định (`TD-W03-02`) |

Hai rủi ro cấu hình phải chặn freeze:

1. **`GPIO10` vừa là `L_EN` (as-built) vừa là `CG_PIN_DS18B20_DATA` (W02)** — không thể cùng
   một chân; W03 không tự đổi pinout (`TD-W03-03`).
2. **`B−` common với GND logic** — nếu đường shunt/đầu cốt hở, dòng TEC có thể đi qua dây
   GND logic/USB; đây là giả thuyết từ continuity, chưa xảy ra sự cố, nhưng phải được D
   duyệt trước khi chạy tải (`TD-W03-02`).

Không có thử tải **50 A**, không có TEC ON có kiểm soát, và **không** có lần chạy firmware
ESP-IDF W03 trên board trong phiên này. Chi tiết phân loại bằng chứng:
`hardware-2026-10-27/provenance-matrix.md`.
