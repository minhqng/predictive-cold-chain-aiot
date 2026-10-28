# A-W03-07 — IBT-2 pin map and logic-only safe state (Member A)

**Trạng thái: `DONE` (code + unit test + kiểm tra tĩnh) · `HARDWARE-LIMITED` (chưa nạp/chạy
trên board; hạn chế an toàn điện ở §2.1 và §5).**

Phạm vi W03: **logic-only, default OFF**. Không PWM, không chạy TEC, không tuyên bố định mức dòng. Nguồn phần cứng: ảnh W01 `14-ibt2-actual.jpg`; firmware: `cg_actuator.c/.h`, `cg_safety.c`, `coldguard_config.h`.

## 1. Nhãn chân đọc từ module thật (ảnh W01 `14-ibt2-actual.jpg`)

| Header trái (nhìn từ ảnh) | Header phải |
|---|---|
| `VCC` `R_IS` `R_EN` `RPWM` | `GND` `L_IS` `L_EN` `LPWM` |

- Board in `HW-039`; 2 × `BTS7960B`; 1 × `SN74HC244` (buffer logic); cầu đấu xanh 4 vị trí (motor `M+/M-`, nguồn `B+/B-`).
- `R_IS`/`L_IS`: chân sense dòng analog — **không đấu** trong W03 (không cần cho trạng thái OFF; nếu đấu phải đo điện áp mode-common trước — ngoài phạm vi W03).
- Đây là **đọc ảnh**, không phải đo điện — nhãn chân đúng thì mới chuyển sang bước log cold-boot.

## 2. Pin map W03 (map v2 — `evidence/A/as-built-pinmap-2026-10-27.md`)

> **Cập nhật 2026-10-28:** hồ sơ hòa giải W01–W03 đã chốt map v2. Bảng dưới đây
> là map **hiệu lực**; bảng v1 và phân tích lệch `GPIO10` ở §2.1 được giữ làm
> lịch sử (đã xử lý ở mức cấu hình, xem ghi chú cuối §2.1).

| Tín hiệu module | GPIO | Hành vi W03 |
|---|---|---|
| `RPWM` | **GPIO5** (`CG_ACTUATOR_RPWM_PIN`) | GPIO output; **chỉ ghi 0**; không LEDC/MCPWM |
| `R_EN` | **GPIO6** (`CG_ACTUATOR_REN_PIN`, alias `CG_ACTUATOR_ENABLE_PIN`) | GPIO output; **chỉ ghi 0**; xóa trước khi ghi PWM mức |
| `L_EN` | **GPIO10** (`CG_ACTUATOR_LEN_PIN`) | GPIO output; **chỉ ghi 0**; xóa trước RPWM |
| `LPWM` | `GND` theo as-built operator-reported | Không điều khiển; tie-off phải được kiểm chứng trên phần cứng trước khi cấp nguồn |
| `R_IS` / `L_IS` | — | không đấu |

Trạng thái OFF dự định: **RPWM LOW, R_EN LOW, L_EN LOW, LPWM vật lý LOW**.
`cg_actuator_force_off()` cấu hình cả 3 chân là output và xóa R_EN, L_EN trước RPWM.

### 2.1 Lệch `GPIO10` — cấu hình firmware ↔ lời khai đấu dây as-built (đã xử lý ở mức cấu hình 2026-10-28)

Trước hòa giải, cùng số `GPIO10` xuất hiện ở hai nguồn **khác loại**:

- `CG_PIN_DS18B20_DATA 10` trong `firmware/main/coldguard_config.h` (W02) — **giá trị cấu
  hình firmware**; với cấu hình đó W02 đã đọc được 4 ROM ID và 620 mẫu DS18B20 trên bench;
- `L_EN` của IBT-2 theo as-built **operator-reported** — **lời khai dây nối**, chưa có
  phép đo continuity;
- chân DS18B20 DATA trong `docs/01 §11.7` (map v1, đã superseded).

Đây là **lệch giữa cấu hình firmware và lời khai đấu dây**, không phải bằng chứng rằng
hai dây vật lý cùng nằm trên GPIO10 — hồ sơ **không** có phép đo continuity nào. W02 đọc
được 4 ROM khi firmware cấu hình GPIO10 là DATA, nên trong các phiên bench đó chân này
đang phục vụ 1-Wire: IBT-2 hoặc chưa đấu, hoặc dây `L_EN` không nằm ở GPIO10 như báo cáo.
Không được suy ra trạng thái dây hiện tại khi chưa đo.

**Xử lý ở mức cấu hình (map v2):** DS18B20 DATA sang **GPIO33** (TEST 129D đã đọc 4 ROM
trên bus 33), `L_EN` giữ **GPIO10** theo as-built, `CG_PIN_MAP_VERSION = 2`. `#error` ở
`coldguard_config.h` chặn mọi bản đồ gán trùng (bao gồm DS18B20=L_EN). `TD-W03-03` đóng
ở mức cấu hình; **continuity từ chân module tới GPIO vẫn chưa được đo**.

**HẠN CHẾ AN TOÀN ĐIỆN vẫn hiệu lực:** không cấp nguồn tải/TEC cho tới khi (a) có phép đo
continuity xác nhận đấu dây as-built và (b) phương án tie-off `LPWM`/`L_EN` được kiểm
chứng trên phần cứng. Trạng thái default-OFF mới được chứng minh ở mức phần mềm + kiểm
tra tĩnh.

**Thứ tự an toàn (đã implement + kiểm tra tĩnh):** `app_main()` gọi `cg_safety_force_actuator_off()` như hành động đầu tiên; `force_off` xóa `R_EN` (0) và `L_EN` (0) trước, rồi ghi `RPWM` (0); kéo xuống (pulldown) cấu hình để chân không nổi khi chưa được điều khiển.

## 3. Bất biến "không thể bật" trong W03

1. `CG_ACTUATOR_ENABLE_ALLOWED` = **0**: guard `cg_actuator_outputs_allowed()` từ chối **mọi** yêu cầu output (kể cả có `operator_authorized=true`).
2. Không tồn tại mã nguồn ghi mức `1` lên `RPWM`/`R_EN`/`L_EN` — static check khẳng định điều này trên **toàn bộ** `firmware/main`.
3. Không có peripheral PWM nào được cấu hình (`ledc`/`mcpwm` không xuất hiện ở bất kỳ file nào — static check).
4. Guard còn từ chối việc cùng lúc cấp duty cho **cả hai** nửa cầu — cùng duty cho ra
   hai đầu ra bằng nhau nên **không** có điện áp vi sai (không phải lệnh đảo chiều);
   chênh lệch duty là vi sai mà lớp W03 không tạo ra. Bất biến cho lớp W04 sau này.
5. W03 không có đường nào tới TEC: firmware không chạy TEC, hồ sơ không cấp nguồn TEC.

## 4. Vì sao `43 A` KHÔNG phải định mức liên tục của module

(Làm rõ tiêu chí trong `docs/05A §12` — không suy định mức từ tên linh kiện.)

- `43 A` in trên datasheet **BTS7960B** là **giới hạn dòng của chip** trong điều kiện lý tưởng (junction temperature ở mức thấp, tản nhiệt vô hạn) — không đo bằng module hoàn chỉnh.
- Module thật giới hạn bởi: **điện trở dẫn của đường mạch in**, tản nhiệt qua board nhỏ, ngưỡng chịu dòng của **đầu cốt/cầu đấu xanh**, dây motor, và duty cycle.
- Không có heatsink/thermal measurement cho module trên bench này; tải thật chưa từng chạy.
- Vậy mọi tuyên bố dòng TEC phải đến từ **đo thật** (PZEM/shunt có tham chiếu) ở W04+, không từ con số trên chip.

## 5. Còn thiếu (điều kiện nâng trạng thái)

| Việc | Loại | Ai |
|---|---|---|
| Đo continuity xác nhận đấu dây `GPIO10`/`L_EN` | **Cấu hình đã chốt 2026-10-28** — `TD-W03-03`: DS18B20→GPIO33, L_EN=GPIO10, map v2; phép đo continuity **chưa thực hiện** | Member A (đo) |
| Kiểm chứng tie-off `LPWM`/`L_EN` trên phần cứng (qua trở hay nổi có kiểm soát) | `HARDWARE-LIMITED` (`TD-W03-06`) | Member A (đo) |
| Log **cold-boot/reset/watchdog** với tải an toàn: ≥5 cold boot + ≥5 reset, chứng minh `RPWM`/`EN` ở 0 trong toàn bộ capture; dùng `cg_capture.py` + đọc `#CG SAFETY` + trạng thái chân nếu có điều kiện đo | MEASUREMENT REQUIRED | Member A |
| Đo mức logic chân module so với ngưỡng VIH của ESP32-S3 (3.3 V) | `HARDWARE-LIMITED` | Member A (đo) |
| PWM chỉ xét sau khi các mục trên có bằng chứng vật lý (W04/H4) | ngoài phạm vi W03 | W04 |

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
không đo continuity cho `GPIO10` ở §2.1.

## 6. Ghi chú hồ sơ

- Trang thái default-OFF của **firmware** đã được kiểm chứng bằng: unit test mô hình (guard), kiểm tra tĩnh (không ghi 1, không PWM, thứ tự boot), và compile CI. **Chưa** được chứng minh bằng log phần cứng — đúng như nhãn trạng thái.
- Ảnh chân `LPWM`/`L_EN`/`R_IS`/`L_IS` chỉ đọc được **nhãn**, chưa xác nhận kết nối thực tế phía sau board; không suy diễn.
