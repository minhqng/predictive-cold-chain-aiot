# ColdGuard — Member A — W03 power / RS-485 / PZEM / IBT-2 logic

**Snapshot:** 2026-10-19 · **Role:** Member A (Embedded & Thermal) · **Status:** `DRAFT / REVIEW REQUIRED — W03 NOT PASS` · **hardware_config_id:** `NOT_ASSIGNED` · **Firmware commit (repo):** see `firmware-tooling-verification.md` (`firmware_commit`) · **Build ESP-IDF thật (CI):** SUCCESS — image `espressif/idf:v6.1`, target `esp32s3`, run `39213118829` (`build-report-w03.md`) · **Operator:** Member A (không ghi tên cá nhân trong repo)

## Phạm vi và thẩm quyền

- Thứ tự thẩm quyền: `docs/00` → `docs/01` → `docs/02` → `docs/03` → `docs/04` → `docs/05A`; cụ thể `docs/04 §18` (W03), `docs/05A §12` (A-W03-01…07), `docs/01 §9` (PZEM), `§10` (RS-485), `§11.7/§11.8` (pin map, actuator default-off), `§12` (IBT-2/TEC), gates `H2–H4`.
- Nhánh này **stacked trên W02** (`feat/a-w02-sensor-foundation`, head `1ff6da6`) vì W02 chưa merge. PR base là `feat/a-w02-sensor-foundation`; khi W02 merge thì retarget `main` (không tự đổi trong PR này).
- Bộ này **không** sửa nhánh W01/W02, **không** merge PR #7/#8, **không** chạy TEC, **không** tuyên bố PASS cho bất kỳ bài đo phần cứng nào chưa chạy.
- Bộ này **không** chứa dữ liệu tự tạo: mọi số liệu tham chiếu đều ghi rõ nguồn (báo cáo người dùng trong W01 hoặc ảnh W01) và mọi thứ chưa đo đều ghi `PENDING` / `MEASUREMENT REQUIRED`.

## Trạng thái tổng quan (chi tiết ở `acceptance.md`)

| Hạng mục | Trạng thái |
|---|---|
| `A-W03-01` XL4015 ~5 V | `VERIFIED BY EXISTING EVIDENCE (W01 user-reported, no-load)` + `MEASUREMENT REQUIRED (loaded/current, có D)` — `logic-power-measurement.md` |
| `A-W03-02` MAX3485 / RS-485 | `SAFETY REVIEW PENDING — Member D + leader (CR-A-W01-01)`; thực tế là **TTL485-V2.0 5 V auto-direction**, không phải MAX3485; firmware chỉ hỗ trợ AUTO (MANUAL là compile-time) — `hardware-deviation-and-safety.md`, `rs485-pin-and-compatibility.md` |
| `A-W03-03` PZEM communication | `CODE IMPLEMENTED / HARDWARE RUN PENDING` (CRC16, framing cấu hình, timeout/retry có giới hạn, phân loại lỗi, timestamp, scaling — có unit test) + `MEASUREMENT REQUIRED` (framing/slave thật trên module) |
| `A-W03-04` 50 A profile | `CODE IMPLEMENTED / HARDWARE RUN PENDING` (READ ONLY, chỉ FC 0x03/0x04) + `MEASUREMENT REQUIRED` — `pzem-register-readback.txt` (PENDING) |
| `A-W03-05` OFF electrical envelope | `MEASUREMENT REQUIRED` (≥10 min TEC OFF, PZEM thật); công cụ dựng CSV + thống kê đã có và đã test — `pzem-register-readback.txt` §3, `pzem-off.csv` **MISSING** |
| `A-W03-06` Shunt installation inspection | `VERIFIED BY EXISTING EVIDENCE (ảnh W01)` cho phần nhìn thấy (nhãn in `50A 75mV`, khắc `FL-2 0.5`) + `MEASUREMENT REQUIRED / SAFETY REVIEW PENDING (D)` cho đường dòng, đầu cốt, kiểm tra có điện |
| `A-W03-07` IBT-2 logic only | `CODE IMPLEMENTED / HARDWARE RUN PENDING` (default OFF, chỉ ghi 0, không PWM, guard từ chối output) + `SAFETY REVIEW PENDING (D)` (tie-off LPWM/L_EN, cold-boot log) — `ibt2-pin-map.md` |

## Files

| File | Nội dung |
|---|---|
| `logic-power-measurement.md` | A-W03-01: giá trị cũ (báo cáo W01, không đo lại), điều còn thiếu (đo có tải, ripple), kế hoạch đo và điều kiện D |
| `rs485-pin-and-compatibility.md` | A-W03-02: đọc module từ ảnh W01 (header, auto-direction, 120 Ω), ánh xạ chân, mức logic 5 V/3.3 V, điều **không** được giả định |
| `hardware-deviation-and-safety.md` | Lệch freeze TTL485 vs MAX3485 (CR-A-W01-01 PENDING), rủi ro R05/R06/R10, ranh giới an toàn của W03 |
| `pzem-register-readback.txt` | A-W03-04/05: bản ghi **PENDING** có lý do — chưa từng có log PZEM thật trong repo; lệnh + công cụ sinh file thật; schema `pzem-off.csv` |
| `ibt2-pin-map.md` | A-W03-07: pin map từ ảnh `14-ibt2-actual.jpg`, trạng thái default-OFF, câu trả lời "43 A", việc D phải quyết định |
| `firmware-tooling-verification.md` | Firmware + công cụ W03: module, grammar v2, test/check đã chạy, giới hạn, `firmware_commit` |
| `build-report-w03.md` | Build ESP-IDF thật trên GitHub Actions (image `espressif/idf:v6.1`, `esp32s3`): run URL, log, artifact + SHA-256, giới hạn của tuyên bố compile |
| `acceptance.md` | **Nguồn trạng thái duy nhất**: acceptance matrix A-W03-01…07, pass criteria canonical, blocker, quyết định cần D/leader |
| `validate_w03.py` | Kiểm tra cấu trúc hồ sơ + commit firmware + chạy lại static checks; **không** xác nhận vật lý |
| `PR_BODY.md` | Nội dung mô tả PR đề xuất (bản cục bộ để review trước khi publish) |

## Việc W03 cố ý KHÔNG làm

- Không tạo `pzem-off.csv` giả, không tạo ảnh `rs485-wiring.png` từ trí nhớ: hai file canonical này được khai báo **MISSING** trong `acceptance.md` (validator từ chối nếu chúng xuất hiện trên đĩa mà chưa có buổi đo thật).
- Không nạp/chạy firmware W03 trên board trong W03 (phần cứng còn chờ D duyệt mức logic RS-485).
- Không ghi register PZEM, không đổi profile 50 A (chỉ đọc).
- Không tạo PWM, không cấp TEC.

## Reproduction / review

1. `py firmware/tools/run_all_checks_w03.py` từ gốc repo → 5/5 PASS: unittest (W02+W03), static W03, static W02 (regression), `validate_w02.py` (regression), `validate_w03.py`.
2. `py evidence/A/W03/validate_w03.py` → kiểm tra file bắt buộc, khai báo MISSING, nhãn trạng thái trong `acceptance.md`, `firmware_commit` chứa đủ module W03 (đọc bằng `git cat-file`/`git show`), workflow CI tồn tại đúng image/target.
3. Đọc `firmware-tooling-verification.md` để biết firmware/công cụ đã được kiểm chứng tới đâu và **chưa** làm gì.
4. Đọc `hardware-deviation-and-safety.md` trước khi cấp nguồn cho khối RS-485 (mức logic chưa được duyệt là điều kiện chặn).
5. `build-report-w03.md`: build ESP-IDF thật trên CI — run `39213118829` **SUCCESS cả hai job** (idf v6.1/esp32s3 + host checks); run đầu tiên FAIL (lỗi biên dịch thật, đã fix) được **giữ nguyên trong báo cáo** để truy vết.

## Handoffs

- **To C:** field semantics của PZEM (`v/i/p/e`, `status`, `attempts`, `exc`, `ok/fail`) và quy ước lỗi/timeout giữ nguyên token như W03 này định nghĩa (`cg_pzem.h` ↔ `cg_modbus.py`); chưa có số liệu đo thật để thay thế fixture.
- **To D:** mức logic RS-485 (CR-A-W01-01), tie-off `LPWM`/`L_EN`, cold-boot/reset log IBT-2, OFF envelope khi có PZEM thật, và đường dòng của shunt trước khi có tải.
- **To leader:** xác nhận lệch TTL485 vs MAX3485 và gán `hardware_config_id`; chưa có gì được chốt trong W03.
