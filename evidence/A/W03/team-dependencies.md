# W03 — Team dependencies (quyết định còn chờ D / leader)

**Trạng thái: `W03 TEAM GATE: PENDING_REVIEW`.** File này liệt kê **những gì Member A không
được tự quyết**, ai phải quyết, và quyết định đó mở khóa việc gì. Nó không phải biên bản
họp, không phải phê duyệt, và không thay `acceptance.md`.

Nguyên tắc giữ nguyên trong suốt W03:

1. Không đổi pinout, dây, BOM đã freeze, hay profile PZEM để "cho khớp hồ sơ".
2. Không nâng nhãn trạng thái nào khi chưa có quyết định hoặc phép đo tương ứng.
3. Không ký thay D/leader; mọi mục dưới đây giữ `OPEN` cho tới khi có người trả lời.

## 1. Bảng quyết định

| ID | Nội dung cần quyết | Ai | Vì sao chặn | Mở khóa việc gì | Trạng thái |
|---|---|---|---|---|---|
| `TD-W03-01` | **CR-A-W01-01:** chấp nhận TTL485-V2.0 (5 V, auto-direction) + phân áp RX, hay yêu cầu module 3.3 V đúng freeze MAX3485 | **D + leader** | Mức logic 5 V vào GPIO là rủi ro phần cứng; chưa có phê duyệt thì không được chạy UART thật | Mọi bài UART/PZEM trên board; A-W03-02 | `OPEN` |
| `TD-W03-02` | **Đường hồi shunt:** topology hiện tại (`B−` common GND logic ≈ 0 Ω, shunt trên đường hồi) có chấp nhận được? Có bắt buộc single-point ground / return riêng / cách ly cảm biến dòng? | **D** | Failure mode khi shunt/đầu cốt hở có thể đẩy dòng TEC qua GND logic — chưa có ai duyệt | A-W03-06; điều kiện chạy tải qua shunt; W04 high-current | `OPEN` |
| `TD-W03-03` | **Xung đột `GPIO10`:** as-built báo `L_EN`, nhưng W02 dùng `GPIO10` cho `CG_PIN_DS18B20_DATA` (đã đọc 4 ROM ID/620 mẫu). Chân nào đúng, chân nào phải dời, có bump `pin_map_version`? | **D + leader** | Hai chức năng không thể cùng một chân trong cấu hình freeze; tự sửa sẽ phá W02 hoặc phá an toàn. **Nghiêm cấm cấp nguồn tải/TEC (energize)** khi xung đột chân này chưa có giải pháp duyệt chính thức | Freeze pin map; kết luận "default OFF" có giá trị bất biến; A-W03-07 | `OPEN` |
| `TD-W03-04` | **Cửa sổ mẫu TEST 132B:** 600 mẫu nhưng span timestamp là **598.99 s** (mẫu cuối ở giây 599). Yêu cầu canonical "≥10 phút" được đánh giá theo `DURATION_MS 600000` hay theo span thật? | **D** | Nếu tính theo span, phiên này **thiếu 1.01 s** so với 600 s; hồ sơ không được tự chọn cách tính có lợi | A-W03-05 (OFF envelope) — chấp nhận hay cần phiên mới | `OPEN` |
| `TD-W03-05` | **Capture gốc cho TEST 131 / TEST 133B:** có còn file log gốc không? Nếu không, lời khai của người vận hành có đủ cho review, hay cần capture mới (không chạy lại chỉ để làm đẹp hồ sơ)? | **D** | Hai bài này hiện chỉ có `OPERATOR-REPORTED`; không được tự tạo raw | A-W03-04 (raw FC03) và A-W03-07 (reset log) | `OPEN` |
| `TD-W03-06` | **IBT-2 tie-off và cách log cold-boot:** `LPWM`/`L_EN` để nổi có kiểm soát hay kéo xuống qua trở? Log cold-boot/reset/watchdog bằng gì (chỉ `#CG SAFETY` hay cần đo chân)? | **D** | Trạng thái nổi khi reset là rủi ro R06; phương pháp log phải do D duyệt trước khi cấp nguồn | A-W03-07 hardware evidence | `OPEN` |
| `TD-W03-07` | **FC06 SET50 ngoài hợp đồng:** `hardware-2026-10-20/` chứa một lần ghi register đổi profile. Xử lý như sai lệch quy trình bench thế nào? | **D + leader** | W03 là read-only; hành vi ghi register nằm ngoài phạm vi và ảnh hưởng niềm tin vào log bench | Kết luận về archive 2026-10-20; quy trình bench W04 | `OPEN` |
| `TD-W03-08` | **`hardware_config_id`** cho cấu hình as-built | **Leader** | Hồ sơ chưa có ID cấu hình phần cứng | Truy vết cấu hình; điều kiện W03 PASS | `OPEN` |
| `TD-W03-09` | **XL4015 có tải:** ai chứng kiến, đo ở mức tải nào, có cần đo ripple/nhiệt trong W03 hay đẩy sang W04? | **D + Member A** | W01 chỉ có ~5.00 V no-load; ripple/nhiệt chưa đo | A-W03-01 | `OPEN` |
| `TD-W03-10` | **`pzem-off.csv` canonical:** giữ khai báo `MISSING` (CSV bench chỉ nằm trong bundle ngày) hay đổi chính sách để nhận CSV schema bench? | **Leader** | Đổi chính sách sẽ thay đổi định nghĩa "canonical" của W03 | A-W03-05; validator `validate_w03.py` | `OPEN` |
| `TD-W03-11` | **7 frame INVALID trong archive 2026-10-20:** Hai trong bảy frame là request echo bị lỗi byte (`…F3 CC` và `…80 08 F1 CC`), gợi ý giả thuyết TX-side corruption / grounding / slew rate. Ai sở hữu và xử lý nguyên nhân gốc rễ? | **Member D + Member A** | 600/600 mẫu ở TEST 132B không giải thích nguyên nhân lỗi ở phiên cũ; nếu nguyên nhân vật lý chưa được hiểu thì có thể tái diễn ở tải lớn | Đóng rủi ro đường truyền RS-485 cho W04; A-W03-03; A-W03-05 | `OPEN` |

## 2. Những gì Member A đã tự quyết trong phạm vi được phép

Các mục này **không** cần D/leader, và đã được ghi rõ trong hồ sơ:

| Quyết định | Lý do |
|---|---|
| Không tạo `rs485-wiring.png` từ trí nhớ | Sơ đồ chính thức thuộc buổi duyệt CR-A-W01-01 |
| Không copy CSV bench lên `evidence/A/W03/pzem-off.csv` | Schema bench ≠ schema canonical `#CG PZEM_CFG`; xem `TD-W03-10` |
| Không chạy lại TEST 131/132B/133B để tạo file | Tránh biến "thiếu file" thành "chạy lại cho đẹp"; dữ liệu thiếu được khai báo |
| Không sửa firmware/pinout để né xung đột `GPIO10` | Thuộc `TD-W03-03` |
| Giữ nguyên archive `hardware-2026-10-20/` | Là provenance của 7 frame lỗi và lần FC06; xóa sẽ mất dấu sai lệch |

## 3. Điều kiện để W03 chuyển khỏi `PENDING_REVIEW`

Không có mục nào dưới đây được coi là đã xong chỉ vì hồ sơ đã được đẩy lên PR:

1. `TD-W03-01` có quyết định bằng văn bản (chấp nhận kèm ràng buộc, hoặc thay module).
2. `TD-W03-03` chốt pin map không xung đột.
3. Một phiên ESP-IDF thật thu được `#CG PZEM_CFG` + `#CG PZEM_RANGE` + chuỗi `#CG PZEM` OK.
4. OFF envelope được D chấp nhận (theo cách tính ở `TD-W03-04`) hoặc chạy lại đủ span.
5. `TD-W03-02`, `TD-W03-06` được D duyệt trước khi bất kỳ tải/TEC nào được cấp.
6. `TD-W03-08` có `hardware_config_id`.
7. PR được review độc lập và **không** tự merge.

## 4. Liên kết

- `acceptance.md` — trạng thái từng hạng mục A-W03-01…07.
- `hardware-2026-10-27/provenance-matrix.md` — câu nào là đo, câu nào là lời khai.
- `hardware-2026-10-27/as-built-configuration.md` §3 — chi tiết xung đột `GPIO10`.
- `hardware-2026-10-27/shunt-continuity.md` §3 — chi tiết failure mode đường hồi.
- `review-w03.md` — những gì đã kiểm bằng máy (không thay review của D).
