# W03 — Đầu vào còn thiếu và việc được mở khóa

**Trạng thái: `MEMBER A W03 EVIDENCE — IMPLEMENTED & VERIFIED WITHIN TESTED SCOPE`.**
File này liệt kê **những gì Member A không thể tự tạo ra** — phép đo vật lý, dữ liệu gốc,
change review, cấu hình — và việc gì được mở khóa khi có chúng. Đây **không** phải biên
bản phê duyệt chéo thành viên và không thay `acceptance.md`.

Nguyên tắc giữ nguyên trong suốt W03:

1. Không đổi pinout, dây, BOM đã freeze, hay profile PZEM để "cho khớp hồ sơ".
2. Không nâng nhãn trạng thái nào khi chưa có phép đo hoặc dữ liệu tương ứng.
3. Mục nào chưa có dữ liệu thì ghi rõ đang thiếu loại dữ liệu gì, không gán kết luận thay.

## 1. Bảng đầu vào còn thiếu

| ID | Cần gì | Loại đầu vào | Vì sao cần | Mở khóa việc gì | Trạng thái |
|---|---|---|---|---|---|
| `TD-W03-01` | **CR-A-W01-01:** kết luận change review cho TTL485-V2.0 (5 V, auto-direction) + phân áp RX, hoặc quyết định thay module 3.3 V đúng freeze MAX3485 | Change review + phép đo mức logic | Mức 5 V vào GPIO là rủi ro phần cứng; chưa xác nhận ≤3.3 V ở GPIO37 thì không chạy UART thật | Mọi bài UART/PZEM trên board; A-W03-02 | `THIẾU — VẬT LÝ` |
| `TD-W03-02` | **Đường hồi shunt:** đánh giá topology hiện tại (`B−` common GND logic ≈ 0 Ω, shunt trên đường hồi) và failure mode khi shunt/đầu cốt hở | Phân tích an toàn + đo | Failure mode hở mạch có thể đẩy dòng TEC qua GND logic | A-W03-06; điều kiện chạy tải qua shunt; W04 high-current | `THIẾU — VẬT LÝ` |
| `TD-W03-03` | **Lệch `GPIO10`:** as-built báo `L_EN`, W02 lại **cấu hình** `CG_PIN_DS18B20_DATA=GPIO10` (đã đọc 4 ROM ID/620 mẫu với cấu hình đó). Cần **đo continuity** để xác nhận dây thật; hiện chỉ là lệch cấu hình ↔ lời khai, **không** có bằng chứng hai dây vật lý cùng chân | Phép đo continuity | Hai chức năng không thể cùng một chân trong cấu hình freeze. **Nghiêm cấm cấp nguồn tải/TEC (energize)** khi continuity chưa đo | Freeze pin map vật lý; A-W03-07 | `ĐÓNG (CẤU HÌNH) 2026-10-28` — map v2: DS18B20→GPIO33, L_EN=GPIO10, `pin_map_version=2`; continuity `MEASUREMENT REQUIRED` |
| `TD-W03-04` | **Cửa sổ mẫu TEST 132B:** 600 mẫu nhưng span timestamp là **598.99 s** (mẫu cuối ở giây 599). Tiêu chí canonical "≥10 phút" tính theo `DURATION_MS 600000` hay theo span thật? | Tiêu chí kỹ thuật bằng văn bản | Nếu tính theo span, phiên này **thiếu 1.01 s** so với 600 s; hồ sơ không được tự chọn cách tính có lợi | A-W03-05 | `THIẾU — TIÊU CHÍ` |
| `TD-W03-05` | **Capture gốc cho TEST 131 / TEST 133B:** có còn file log gốc không? Nếu không, cần capture mới (không chạy lại chỉ để làm đẹp hồ sơ) | Dữ liệu gốc | Hai bài này hiện chỉ có `OPERATOR-REPORTED`; không được tự tạo raw | A-W03-04 (raw FC03) và A-W03-07 (reset log) | `THIẾU — DỮ LIỆU GỐC` |
| `TD-W03-06` | **IBT-2 tie-off và cách log cold-boot:** `LPWM`/`L_EN` để nổi có kiểm soát hay kéo xuống qua trở? Log cold-boot/reset/watchdog bằng gì (chỉ `#CG SAFETY` hay cần đo chân)? | Phép đo + phương pháp | Trạng thái nổi khi reset là rủi ro R06; phải xác nhận tie-off trước khi cấp nguồn | A-W03-07 hardware evidence | `THIẾU — VẬT LÝ` |
| `TD-W03-07` | **FC06 SET50 ngoài hợp đồng:** `hardware-2026-10-20/` chứa một lần ghi register đổi profile. Sai lệch quy trình bench này được mô tả/xử lý thế nào? | Mô tả quy trình | W03 là read-only; hành vi ghi register nằm ngoài phạm vi và ảnh hưởng niềm tin vào log bench | Kết luận về archive 2026-10-20; quy trình bench W04 | `THIẾU — QUY TRÌNH` |
| `TD-W03-08` | **`hardware_config_id`** cho cấu hình as-built | Cấu hình | Hồ sơ chưa có ID cấu hình phần cứng | Truy vết cấu hình | `THIẾU — CẤU HÌNH` |
| `TD-W03-09` | **XL4015 có tải:** đo ở mức tải nào, có cần ripple/nhiệt trong W03 hay đẩy sang W04? | Phép đo | W01 chỉ có ~5.00 V no-load; ripple/nhiệt chưa đo | A-W03-01 | `THIẾU — VẬT LÝ` |
| `TD-W03-10` | **`pzem-off.csv` canonical:** giữ khai báo `MISSING` (CSV bench chỉ nằm trong bundle ngày) hay đổi định nghĩa "canonical" để nhận CSV schema bench? | Chính sách dữ liệu | Đổi chính sách sẽ thay đổi định nghĩa "canonical" của W03 | A-W03-05; validator `validate_w03.py` | `THIẾU — CHÍNH SÁCH` |
| `TD-W03-11` | **7 frame INVALID trong archive 2026-10-20:** Hai trong bảy frame là request echo bị lỗi byte (`…F3 CC` và `…80 08 F1 CC`), gợi ý TX-side corruption / grounding / slew rate. Cần điều tra nguyên nhân gốc rễ | Điều tra | 600/600 mẫu ở TEST 132B không giải thích lỗi ở phiên cũ; nếu nguyên nhân vật lý chưa hiểu thì có thể tái diễn ở tải lớn | Đóng rủi ro đường truyền RS-485 cho W04; A-W03-03; A-W03-05 | `THIẾU — ĐIỀU TRA` |

## 2. Những gì Member A đã tự quyết trong phạm vi được phép

Các mục này nằm trong phạm vi kỹ thuật của Member A và đã được ghi rõ trong hồ sơ:

| Quyết định | Lý do |
|---|---|
| Không tạo `rs485-wiring.png` từ trí nhớ | Sơ đồ chính thức cần ảnh thật + kết luận change review `CR-A-W01-01` |
| Không copy CSV bench lên `evidence/A/W03/pzem-off.csv` | Schema bench ≠ schema canonical `#CG PZEM_CFG`; xem `TD-W03-10` |
| Không chạy lại TEST 131/132B/133B để tạo file | Tránh biến "thiếu file" thành "chạy lại cho đẹp"; dữ liệu thiếu được khai báo |
| Không sửa **dây/pinout vật lý** để né lệch `GPIO10` | Chỉ đổi cấu hình firmware sang map v2; continuity là việc đo (`TD-W03-03`) |
| Giữ nguyên archive `hardware-2026-10-20/` | Là provenance của 7 frame lỗi và lần FC06; xóa sẽ mất dấu sai lệch |

## 3. Phần còn lại của W03 (không phải điều kiện phê duyệt)

Không mục nào dưới đây là cổng phê duyệt chéo thành viên; mỗi mục là việc chưa có dữ
liệu hoặc chưa chạy trên board:

1. `TD-W03-01`: xác nhận mức logic ≤3.3 V ở GPIO37 (kèm kết luận change review TTL485).
2. `TD-W03-03`: đo continuity xác nhận `L_EN` = GPIO10 và DS18B20 nối GPIO33 trên board.
3. Một phiên ESP-IDF thật thu được `#CG PZEM_CFG` + `#CG PZEM_RANGE` + chuỗi `#CG PZEM` OK.
4. OFF envelope canonical đủ span, hoặc áp dụng cách tính được ghi bằng văn bản (`TD-W03-04`).
5. Trước khi cấp tải/TEC: kiểm chứng tie-off LPWM và topology đường hồi (`TD-W03-02`, `TD-W03-06`) — **hạn chế an toàn điện**.
6. `TD-W03-08`: gán `hardware_config_id`.
7. Review độc lập phần đã implement (không phải điều kiện để công nhận phần đã kiểm chứng bằng máy).

## 4. Liên kết

- `acceptance.md` — trạng thái từng hạng mục A-W03-01…07.
- `hardware-2026-10-27/provenance-matrix.md` — câu nào là đo, câu nào là lời khai.
- `hardware-2026-10-27/as-built-configuration.md` §3 — chi tiết lệch cấu hình `GPIO10`.
- `hardware-2026-10-27/shunt-continuity.md` §3 — chi tiết failure mode đường hồi.
- `review-w03.md` — biên bản review tĩnh nội bộ 2026-10-19 (bản ghi lịch sử, không phải nghiệm thu hiện tại).
