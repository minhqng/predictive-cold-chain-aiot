# A-W03-07 — TEST 133B reset / default-OFF (operator-reported summary)

**Trạng thái: `OBSERVED PASS AFTER FIRMWARE START — OPERATOR-REPORTED`**
**Giới hạn: `RAW LOG NOT AVAILABLE`; `COLD BOOT = OPERATOR-REPORTED`; `PRE-setup() SCOPE NOT PROVEN`.**

## 1. Test được định nghĩa thế nào

Sketch `firmware/ColdGuard_TEST_133B_reset_default_off.ino` (bản người vận hành cung cấp,
SHA-256 `8986a21c…`) mô tả:

| Thành phần | Giá trị |
|---|---|
| Tên test | `TEST 133B` — IBT-2 default OFF / reset test |
| Thời lượng mỗi cửa sổ | `20 s`, lấy mẫu `1 Hz` → tối đa 20 mẫu/cửa sổ |
| Kênh đo | PZEM-017 qua TTL485: FC `0x04`, 8 input register (V/I/P) |
| Chân IBT-2 trong sketch | `RPWM=5`, `R_EN=6`, `L_EN=10`; `LPWM` không điều khiển |
| Hành động | kéo `RPWM/R_EN/L_EN` LOW trong `setup()` và trước mỗi report |
| Reset | lệnh `X` gọi `ESP.restart()` (software reset); `R` replay report |
| Tự chạy | sau mỗi boot, test tự bắt đầu và in CSV + summary |
| TEC | sketch không tạo PWM, không bật TEC |

Sketch in `RESULT: NO CURRENT DETECTED` và **`SCOPE: AFTER FIRMWARE START ONLY`** khi mọi
mẫu hợp lệ và không có dòng. Chính sketch đã giới hạn phạm vi chứng minh.

## 2. Kết quả người vận hành báo

| Cửa sổ | Cách tạo | Mẫu hợp lệ | Dòng hiển thị | Công suất |
|---|---|---:|---|---|
| 1 | boot trước đó, `OTHER_CODE_11` | 20/20 | `0.00 A` | `0.0 W` |
| 2–6 | 5 lần `ESP.restart()` bằng lệnh `X` | 20/20 mỗi lần | `0.00 A` | `0.0 W` |
| **Tổng** | **6 cửa sổ** | **120/120** | **0.00 A** | **0.0 W** |

- Số học: `6 × 20 = 120`, khớp tổng người vận hành báo.
- `OTHER_CODE_11`: sketch chỉ in mã số vì `esp_reset_reason_t` rơi vào nhánh `default`.
  Người vận hành giải thích đây là reset lý do USB; hồ sơ giữ **cả** mã quan sát và cách
  diễn giải là operator-reported (không có header ESP-IDF trong repo để đối chiếu enum).
- Người vận hành cũng báo đã nhiều lần rút/cấp lại nguồn bằng tay và hệ thống vẫn OFF.
  **Không có bảng đếm hoặc timestamp riêng** cho các lần cold boot này.

## 3. Ba mức bằng chứng phải tách

1. **Sau khi firmware bắt đầu chạy:** 120/120 mẫu PZEM hợp lệ, dòng/công suất dưới độ phân
   giải hiển thị. Đây là quan sát điện, **không** phải đo mức logic của chân IBT-2.
2. **Dòng "RPWM: LOW / R_EN: LOW / L_EN: LOW" trong summary là chuỗi hằng số do sketch in**,
   không phải đọc lại trạng thái chân hay đo bằng scope. Không được trích dẫn như phép đo.
3. **Cold boot thủ công:** chỉ là lời khai của người vận hành; không có bảng đếm, timestamp,
   hay capture. Không có bằng chứng oscilloscope/high-speed cho khoảng thời gian **trước khi
   `setup()` chạy**. Vì vậy không được biến quan sát này thành "hardware-level proof".

## 4. Xung đột pin phải được xử lý trước khi freeze

As-built được báo: `GPIO10 → L_EN`. Nhưng W02 dùng **`GPIO10` cho DS18B20 DATA**
(`CG_PIN_DS18B20_DATA 10`, `docs/01 §11.7`) và đã đọc 4 ROM ID / 620 mẫu trên bench qua
GPIO10. Hai chức năng không thể cùng chiếm một chân trong cấu hình freeze.

Đây là **`TEAM_DEPENDENCY`**, không phải lỗi có thể tự sửa trong W03:

- Không đổi pinout firmware hay dây phần cứng trong task này.
- Không kết luận chân nào "đúng" khi chưa có sơ đồ/đo thực tế.
- D + leader phải xác nhận as-built thực tế và quyết định `pin_map_version`/đấu dây.
- Cho tới lúc đó, mọi tuyên bố "default OFF ổn định" chỉ có giá trị quan sát, không phải
  bất biến phần cứng đã freeze.

Chi tiết: `as-built-configuration.md` §3 và `../team-dependencies.md`.

## 5. Điều KHÔNG được suy ra

- Không suy ra **toàn bộ** khoảng boot/reset an toàn; chỉ có cửa sổ sau khi firmware chạy.
- Không suy ra `RPWM`/`R_EN`/`L_EN` đã ở mức 0 trong suốt reset; không có scope/logic analyzer.
- Không suy ra module IBT-2 có thể chịu tải liên tục; `43 A` là giới hạn chip, không phải
  định mức module (`../ibt2-pin-map.md` §4).
- Không suy ra shunt/đường dòng an toàn khi chạy tải lớn (`shunt-continuity.md`).
- Không thay thế phê duyệt tie-off `LPWM`/`L_EN` và mức logic 3.3 V của D.

## 6. Trạng thái acceptance

| Tiêu chí | Kết quả |
|---|---|
| Default OFF sau khi firmware chạy | **OBSERVED PASS** — 120/120 mẫu, 0.00 A, 0.0 W (operator-reported) |
| 5 software reset | **OPERATOR-REPORTED** — không có raw log |
| Cold boot | **OPERATOR-REPORTED** — không có bảng đếm/timestamp |
| Trước `setup()` | **NOT PROVEN** — không có scope/high-speed capture |
| Pin map không xung đột | **FAIL / PENDING** — GPIO10 trùng DS18B20; D + leader phải xử lý |
| An toàn khi có tải TEC | **NOT TESTED** — ngoài phạm vi W03 |
