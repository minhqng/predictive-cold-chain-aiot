# W03 — Hardware deviation and safety boundaries (Member A)

**Không phải chứng nhận an toàn.** Đây là bản ghi các lệch phần cứng đang mở và ranh giới W03 không được vượt qua. Kế thừa W01 `freeze-deviation-review.md` + `physical-risk-ledger.md`.

## 1. RS-485: TTL485-V2.0 thực tế vs MAX3485 đã freeze — CR-A-W01-01

| Mục | Canonical freeze (HW-07) | Thực tế as-built (ảnh W01 + người dùng báo) |
|---|---|---|
| Module | MAX3485 3.3 V | **TTL485-V2.0**, rail logic **5 V** |
| Chip | MAX3485 (3.3 V) | người dùng báo `MAX13487ESA`; **marking chưa đọc được trong bất kỳ ảnh nào** (W01 acceptance #7 = PARTIAL) |
| Hướng | DE//RE điều khiển bằng GPIO | **auto-direction**, không có chân DE//RE trên header `GND/RXD/TXD/VCC` |
| Mức RX | RO 3.3 V đấu thẳng | TXD idle **5 V** theo báo cáo; phân áp tạm 10k/10k/10k → ~3.314 V **đo được** (vận hành W01), tính ≈ 3.33 V |

**Trạng thái:** `PENDING (D + leader)` — W01 `freeze-deviation-review.md` CR-A-W01-01.

**Quy tắc W03 (bắt buộc):**

1. **Không** đấu 5 V trực tiếp vào GPIO nào của ESP32.
2. **Không** giả định RO/chân trả lời là 3.3 V khi chưa có datasheet/marking xác thực (không được suy luận từ báo cáo người dùng).
3. Phân áp 10k/10k/10k hiện tại là **đấu nối tạm đã được khảo sát**, không phải thiết kế production được duyệt.
4. Chỉ chạy bất kỳ bài UART **sau khi** D + leader chốt CR-A-W01-01; firmware W03 không tự bật bất kỳ thử nghiệm nào (không có chế độ test UART trong build mặc định).
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
- **Không** chạy bất kỳ bài UART phần cứng nào khi mức logic RS-485 chưa được duyệt.
- **Không** ghi register PZEM (không đổi profile, không đổi slave address qua bus).
- **Không** tạo PWM; **không** tồn tại đường code nào ghi mức 1 lên `RPWM`/`ENABLE`.
- **Không** nâng bất kỳ trạng thái nào từ ảnh/unit test: mọi bài cần đo đều `MEASUREMENT REQUIRED`.

## 4. Điều kiện dừng bắt buộc (kế thừa W01, còn hiệu lực)

- Cực tính không chắc, đầu nối ấm/nóng, tia lửa, mùi lạ, PSU hành xử bất thường, fuse nổ hoặc dây lỏng → **ngắt điện lưới** và điều tra.
- Không bắc cầu fuse, không nối tắt PSU để mô phỏng lỗi, không cấp TEC khi quạt/tản nhiệt chưa hoạt động, không dùng jumper mảnh làm dây công suất.
- **W03 không phê duyệt bất kỳ lần chạy tải dòng lớn nào.** Mọi bài đo W03 chỉ được thực hiện khi có mặt D (hoặc người được D ủy quyền), theo checklist tương ứng trong từng file.
