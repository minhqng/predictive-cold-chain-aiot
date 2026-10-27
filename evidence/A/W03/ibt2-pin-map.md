# A-W03-07 — IBT-2 pin map and logic-only safe state (Member A)

**Trạng thái: `CODE IMPLEMENTED / HARDWARE RUN PENDING` + `SAFETY REVIEW PENDING (D)`.**

Phạm vi W03: **logic-only, default OFF**. Không PWM, không chạy TEC, không tuyên bố định mức dòng. Nguồn phần cứng: ảnh W01 `14-ibt2-actual.jpg`; firmware: `cg_actuator.c/.h`, `cg_safety.c`, `coldguard_config.h`.

## 1. Nhãn chân đọc từ module thật (ảnh W01 `14-ibt2-actual.jpg`)

| Header trái (nhìn từ ảnh) | Header phải |
|---|---|
| `VCC` `R_IS` `R_EN` `RPWM` | `GND` `L_IS` `L_EN` `LPWM` |

- Board in `HW-039`; 2 × `BTS7960B`; 1 × `SN74HC244` (buffer logic); cầu đấu xanh 4 vị trí (motor `M+/M-`, nguồn `B+/B-`).
- `R_IS`/`L_IS`: chân sense dòng analog — **không đấu** trong W03 (không cần cho trạng thái OFF; nếu đấu phải qua D vì có thể có điện áp mode-common).
- Đây là **đọc ảnh**, không phải đo điện — nhãn chân đúng thì mới chuyển sang bước log cold-boot.

## 2. Pin map W03 (pin map v1 — `docs/01 §11.7`)

| Tín hiệu module | GPIO | Hành vi W03 |
|---|---|---|
| `RPWM` | **GPIO5** (`CG_ACTUATOR_RPWM_PIN`) | GPIO output; **chỉ ghi 0**; không LEDC/MCPWM |
| `EN` (chân enable được dùng theo đấu dây as-built) | **GPIO6** (`CG_ACTUATOR_ENABLE_PIN`) | GPIO output; **chỉ ghi 0**; xóa trước khi ghi PWM mức |
| `L_EN` | **GPIO10** theo as-built **operator-reported** | **Không được firmware W03 điều khiển**; **xung đột** với DS18B20 của W02 — xem §2.1 |
| `LPWM` | `GND` theo as-built operator-reported | Không điều khiển; tie-off là quyết định của D |
| `R_IS` / `L_IS` | — | không đấu |

### 2.1 Xung đột `GPIO10` — chặn freeze, không tự sửa

`GPIO10` đồng thời là:

- `L_EN` của IBT-2 theo as-built **operator-reported**;
- `CG_PIN_DS18B20_DATA 10` trong `firmware/main/coldguard_config.h` (W02), đã dùng để đọc
  4 ROM ID và 620 mẫu DS18B20 trên bench;
- chân DS18B20 DATA trong `docs/01 §11.7`.

Không thể cùng lúc là bus 1-Wire và enable nửa cầu. W03 **không** đổi pinout firmware, không
đổi dây, không kết luận chân nào "đúng": D + leader phải xác nhận as-built thật và quyết định
(`team-dependencies.md` `TD-W03-03`).

**CẢNH BÁO AN TOÀN / BLOCKER:** Xung đột này có thể dẫn tới hành vi kích hoạt nửa cầu IBT-2 ngoài ý muốn (khi bus 1-Wire kéo mức) hoặc làm tê liệt chuỗi đọc cảm biến nhiệt. **Nghiêm cấm cấp nguồn tải/TEC (energize)** dưới cấu hình xung đột này cho tới khi có phương án phân chân và an toàn được duyệt chính thức. Cho tới khi chốt, mọi kết luận "default OFF ổn định" chỉ là quan sát trên bench logic, không phải bất biến phần cứng đã freeze.

**Thứ tự an toàn (đã implement + kiểm tra tĩnh):** `app_main()` gọi `cg_safety_force_actuator_off()` như hành động đầu tiên; `force_off` xóa `ENABLE` (0) trước, rồi ghi `RPWM` (0); kéo xuống (pulldown) cấu hình để chân không nổi khi chưa được điều khiển.

## 3. Bất biến "không thể bật" trong W03

1. `CG_ACTUATOR_ENABLE_ALLOWED` = **0**: guard `cg_actuator_outputs_allowed()` từ chối **mọi** yêu cầu output (kể cả có `operator_authorized=true`).
2. Không tồn tại mã nguồn ghi mức `1` lên `RPWM`/`ENABLE` — static check khẳng định điều này trên **toàn bộ** `firmware/main`.
3. Không có peripheral PWM nào được cấu hình (`ledc`/`mcpwm` không xuất hiện ở bất kỳ file nào — static check).
4. Guard còn từ chối PWM đối nghịch (hai nửa cầu cùng duty ≠ 0) — bất biến cho lớp W04 sau này.
5. W03 không có đường nào tới TEC: firmware không chạy TEC, hồ sơ không cấp nguồn TEC.

## 4. Vì sao `43 A` KHÔNG phải định mức liên tục của module

(Trả lời câu hỏi leader trong `docs/05A §12` — không suy định mức từ tên linh kiện.)

- `43 A` in trên datasheet **BTS7960B** là **giới hạn dòng của chip** trong điều kiện lý tưởng (junction temperature ở mức thấp, tản nhiệt vô hạn) — không đo bằng module hoàn chỉnh.
- Module thật giới hạn bởi: **điện trở dẫn của đường mạch in**, tản nhiệt qua board nhỏ, ngưỡng chịu dòng của **đầu cốt/cầu đấu xanh**, dây motor, và duty cycle.
- Không có heatsink/thermal measurement cho module trên bench này; tải thật chưa từng chạy.
- Vậy mọi tuyên bố dòng TEC phải đến từ **đo thật** (PZEM/shunt có tham chiếu) ở W04+, không từ con số trên chip.

## 5. Còn thiếu (điều kiện nâng trạng thái)

| Việc | Loại | Ai |
|---|---|---|
| Chốt as-built `GPIO10` (L_EN hay DS18B20 DATA) và `pin_map_version` | TEAM DEPENDENCY (`TD-W03-03`) | D + leader |
| D duyệt sơ đồ đấu `LPWM`/`L_EN` (tie-off qua trở hay để nổi có kiểm soát) | SAFETY REVIEW (`TD-W03-06`) | D |
| Log **cold-boot/reset/watchdog** với tải an toàn: ≥5 cold boot + ≥5 reset, chứng minh `RPWM`/`EN` ở 0 trong toàn bộ capture; dùng `cg_capture.py` + đọc `#CG SAFETY` + trạng thái chân nếu có điều kiện đo | MEASUREMENT REQUIRED | Member A + D |
| Xác nhận mức logic các chân theo datasheet module (ngưỡng VIH esp32-s3 3.3 V) | SAFETY REVIEW | D |
| Chỉ khi mọi thứ trên xong mới xét PWM (W04/H4) | ngoài phạm vi W03 | D + leader |

### 5.1 TEST 133B (2026-10-27) đóng góp được gì

Sketch `hardware-2026-10-27/firmware/ColdGuard_TEST_133B_reset_default_off.ino` là **định
nghĩa test**, không phải firmware W03. Người vận hành báo 6 cửa sổ × 20 mẫu (120/120 hợp lệ,
`0.00 A`, `0.0 W`), 5 lần `ESP.restart()` và cold boot thủ công vẫn OFF.

Ba giới hạn giữ nguyên:

1. Dòng `RPWM: LOW / R_EN: LOW / L_EN: LOW` là **hằng chuỗi do sketch in** — không phải đọc
   lại trạng thái chân, không có scope/logic analyzer.
2. Sketch tự ghi `SCOPE: AFTER FIRMWARE START ONLY` — không chứng minh khoảng **trước**
   `setup()`.
3. Cold boot chỉ là lời khai; không có bảng đếm/timestamp/raw log →
   `RAW_EVIDENCE_NOT_AVAILABLE`.

Vì vậy TEST 133B là quan sát ủng hộ, **không** phải log cold-boot mà §5 yêu cầu; nó cũng
không xử lý được xung đột `GPIO10` ở §2.1.

## 6. Ghi chú hồ sơ

- Trang thái default-OFF của **firmware** đã được kiểm chứng bằng: unit test mô hình (guard), kiểm tra tĩnh (không ghi 1, không PWM, thứ tự boot), và compile CI. **Chưa** được chứng minh bằng log phần cứng — đúng như nhãn trạng thái.
- Ảnh chân `LPWM`/`L_EN`/`R_IS`/`L_IS` chỉ đọc được **nhãn**, chưa xác nhận kết nối thực tế phía sau board; không suy diễn.
