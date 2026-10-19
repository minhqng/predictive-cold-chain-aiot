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
| `LPWM` | — | **Chưa đấu vào GPIO nào trong W03** — tie-off là quyết định của D |
| `L_EN` / chân enable còn lại | — | như trên |
| `R_IS` / `L_IS` | — | không đấu |

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
| D duyệt sơ đồ đấu `LPWM`/`L_EN` (tie-off qua trở hay để nổi có kiểm soát) | SAFETY REVIEW | D |
| Log **cold-boot/reset/watchdog** với tải an toàn: ≥5 cold boot + ≥5 reset, chứng minh `RPWM`/`EN` ở 0 trong toàn bộ capture; dùng `cg_capture.py` + đọc `#CG SAFETY` + trạng thái chân nếu có điều kiện đo | MEASUREMENT REQUIRED | Member A + D |
| Xác nhận mức logic các chân theo datasheet module (ngưỡng VIH esp32-s3 3.3 V) | SAFETY REVIEW | D |
| Chỉ khi mọi thứ trên xong mới xét PWM (W04/H4) | ngoài phạm vi W03 | D + leader |

## 6. Ghi chú hồ sơ

- Trang thái default-OFF của **firmware** đã được kiểm chứng bằng: unit test mô hình (guard), kiểm tra tĩnh (không ghi 1, không PWM, thứ tự boot), và compile CI. **Chưa** được chứng minh bằng log phần cứng — đúng như nhãn trạng thái.
- Ảnh chân `LPWM`/`L_EN`/`R_IS`/`L_IS` chỉ đọc được **nhãn**, chưa xác nhận kết nối thực tế phía sau board; không suy diễn.
