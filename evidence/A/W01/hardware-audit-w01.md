# A-W01 — Hardware audit summary

**Ngày biên soạn bằng chứng:** 2026-10-17 (người dùng) · **Ngày hiệu chỉnh tài liệu:** 2026-10-18 · **Operator:** Member A (người vận hành vật lý) · **Reviewer:** Member D + team leader.

**Nguồn:** baseline repository hiện tại (Docs 00–05A), kết quả người dùng báo sau khi thao tác thực tế, và **25 ảnh** người dùng tải lên (gói ảnh hiện hành 2026-10-18). **Không** có phép đo nào được agent tái lập độc lập, và **không** có cuộc kiểm đếm vật lý đầy đủ nào do agent chứng kiến.

## Miền đã freeze

Một board dual ESP32-S3R2, ba DS18B20 chính, một BME280, một MC-38, PZEM-017 + shunt 50 A/75 mV, một module MAX3485 3.3 V (phần cứng thực tế khác), một IBT-2, một TEC1-12715, cụm tản V1 12 V, chamber 6 L, PSU 12 V/33 A, XL4015, bảo vệ bằng fuse ATO, linh kiện phân phối. **Chỉ một nhánh làm lạnh.** Toàn bộ 24 mục được kiểm kê trong `bom-audit.csv`.

## Kết quả thực thi được ghi nhận (dùng để đối chiếu danh tính, không phải PASS của W01)

- **DS18B20:** 4 ROM ID 64-bit duy nhất đọc được qua **GPIO10** (người dùng báo); ba cảm biến vẫn là cảm biến chính, bảng ROM → vai trò còn ở W02.
- **MC-38:** chân **GPIO34**; **24 chu kỳ** đóng/mở đã được quan sát (người dùng báo). Log chu kỳ chưa nằm trong bộ chứng cứ.
- **PZEM-017:** Modbus trả lời hợp lệ CRC qua **GPIO36/37**; đọc **11.95 V** khi nhánh cảm biến 12 V đấu qua fuse 1 A (người dùng báo). Khi ngắt đầu đo: 0.00 V (người dùng báo). **Chưa đo dòng/công suất.**
- **TTL485-V2.0:** nguồn logic 5 V; TXD idle 5 V; đầu ra phân áp ~3.314 V **đo được** tại GPIO37 (giá trị tính theo phân áp ≈ 3.33 V) — tất cả **do người dùng báo**. Bắt buộc có phân áp phù hợp trước khi vào RX của ESP32.
- **XL4015:** đo khoảng 5 V ở đầu ra; TB4506 khoảng 4.99 V (người dùng báo).
- **BTS7960:** đã kiểm tra logic cơ bản; GND logic và B− của nguồn thông mạch. **Chưa** chứng minh hoạt động dòng lớn/thermal.
- **TEC:** **chưa** cấp nguồn và **chưa** đo dòng qua shunt. Không suy dòng định mức từ tên linh kiện.

## Sai lệch so với BOM đã freeze (cần phê duyệt)

Đúng bốn sai lệch, chi tiết ở `freeze-deviation-review.md`:

1. **HW-07** — MAX3485 3.3 V → TTL485-V2.0 5 V (MAX13487ESA do người dùng báo). Thay đổi linh kiện và miền nguồn; phân áp tạm **không** phải phê duyệt production.
2. **HW-17** — TB4504 45 A 4P → TB4506 cầu đấu 6 vị trí. Định mức và độ phù hợp đầu nối chưa xác lập.
3. **HW-18** — PCT-218 ×1 → **×4 chiếc** (chỉ số lượng, người dùng xác nhận đã có).
4. **HW-02** — DS18B20 ×3 → **×4 đầu dò** (chỉ số lượng). Chỉ định 3 cảm biến chính và 1 dự phòng sau khi thống nhất; không tự tạo kênh T4.

## Khoảng trống xác minh (không phải sai lệch BOM)

- **HW-16:** mới xác nhận 1 × 5 A trên yêu cầu `>=2 × 5 A`; fuse 1 A là nhánh đo bổ sung ngoài BOM, không tính là bằng chứng đủ 5 A.
- **HW-23:** 3 × 10 kΩ **người dùng báo là đã đo** (ngoài BOM); 4.7 kΩ pull-up người dùng báo đủ nhưng chưa có ảnh/đo — agent **chưa** tái lập cả hai con số.
- **HW-20:** dây 0.75 mm² với cos FDD2-250 (1.5–2.5 mm²); không được suy ra phù hợp chỉ từ một lần kéo thử.
- **HW-19:** chưa xác nhận `2 × 2.5 mm² ~2 m`.
- **HW-06:** ảnh 18 cho thấy nhãn **in** `50A 75mV` trên thân shunt, và ảnh 04 cho thấy phần tử điện trở khắc `FL-2 0.5`. Marking nay đã khớp BOM; cấp chính xác và profile 50 A của PZEM vẫn chưa xác minh.
- **HW-09:** ảnh 15 đọc rõ marking `TEC1-12715 SR`; seller/SKU vẫn chưa xác minh và **không** suy dòng định mức từ marking.
- **HW-11:** ảnh 27 chỉ chứng nhận **đã nhận kiện** còn bọc; model HS2 và dung tích 6 L **chưa** được ảnh xác thực.
- **HW-24:** ảnh 17 cho thấy hộp kit V1 nhưng **không** nhận diện riêng được tuýp keo.
- **HW-19 / HW-22 / HW-24:** vẫn `photo_ref = NONE` — chưa có ảnh cho tiết diện dây công suất, tồn kho header và tuýp keo tản nhiệt. Đúng ba mục này còn `NONE`.
- **HW-01 / HW-03:** thương hiệu board dual đã xác nhận bằng ảnh 20 (`MAKDRIVERONE`); marking từng chip và die BME280/BMP280 vẫn chưa xác minh.
- **HW-03:** breakout BME280 (silkscreen `GY-BM[P/E] 280`; ký tự giữa E/P không đọc chắc chắn) đã nhận nhưng chưa hàn header và chưa cấp điện.

## Tình trạng ảnh và giới hạn danh tính

`photo-inventory.csv` liệt kê **25 ảnh thật** do người dùng tải lên (10 ảnh đầu đã crop; 15 ảnh bổ sung giữ nguyên khung), không có ảnh tổng hợp. So với bộ 10 ảnh trước, gói mới **đã đóng** khoảng trống ảnh cho board dual (hai mặt), DS18B20, MC-38, IBT-2, marking TEC, tem nguồn, kit V1 kèm quạt, marking shunt, PCT-218 (một chiếc) và hai mặt BME280. **Vẫn thiếu:** ảnh đếm đủ số lượng (4 đầu dò DS18B20, 4 chiếc PCT-218), bảng ROM ID DS18B20, tem HS2/dung tích chamber (kiện chưa mở), marking tiết diện dây công suất (HW-19), tồn kho header (HW-22), tuýp keo tản nhiệt (HW-24), nắp che phần AC, và marking các chip còn lại (MAX13487ESA, chip board dual, XL4015, TB4506).

## Kết luận W01

Bộ chứng cứ W01 là **draft để review PR**. Checklist nghiệm thu, blocker và chủ sở hữu hành động tiếp theo nằm duy nhất tại `acceptance.md` để tránh trùng lặp và lệch trạng thái giữa hai tài liệu.

**Trạng thái hiện tại: `W01_PENDING_REVIEW` — chưa phải `W01_PASS`.** Trạng thái **canonical** chỉ nằm ở `acceptance.md`; dòng trên đây là bản tóm tắt và **không** được dùng làm nguồn trạng thái.
