# ColdGuard — Member A — W03 power / RS-485 / PZEM / IBT-2 logic

> **Ghi chú 2026-10-28 — pin map v2.** Bản đồ chân hiệu lực:
> `evidence/A/as-built-pinmap-2026-10-27.md` (DS18B20=33, BME=21/34, MC-38=35,
> RS-485 36/37 AUTO, IBT-2 RPWM/R_EN/L_EN=5/6/10; `CG_PIN_MAP_VERSION=2`).
> `cg_actuator_force_off()` xóa R_EN và L_EN trước RPWM; thêm validator
> `firmware/tools/cg_gpio_map.py`. `TD-W03-03` đóng ở mức cấu hình; continuity vật lý
> `GPIO10` **chưa đo**.

**Snapshot:** 2026-10-28 · **Role:** Member A (Embedded & Thermal) · **Dossier status:** `MEMBER A W03 EVIDENCE — IMPLEMENTED & VERIFIED WITHIN TESTED SCOPE` · **Kết luận theo hạng mục:** xem `acceptance.md` §1 (`DONE` / `PARTIAL` / `HARDWARE-LIMITED` / `NOT IMPLEMENTED` / `INFRASTRUCTURE-LIMITED`) · **hardware_config_id:** `NOT_ASSIGNED`
**Firmware commit (repo):** `b85869322fb8c9828e25942346465d1ec6e131d7` — xem `firmware-tooling-verification.md`
**Build ESP-IDF thật:** CI SUCCESS cho commit `ae1744d` (run `39213118829`, image `espressif/idf:v6.1`, target `esp32s3`). Đối với commit đã push `f8587dd`: GitHub Actions CI trên mây bị chặn bởi hạn mức thanh toán tài khoản kho mã (`Billing & plans` — run `40532665748`), nhưng bản build native Windows ESP-IDF v6.1 cục bộ trên đúng mã nguồn commit `f8587dd` đạt **PASS** (1.090 bước Ninja, 0 warning, 0 error, xem `build-native-windows-2026-10-27/` và `build-report-w03.md`). Bản build 2026-10-28 lặp lại trên **working tree W03 trước tích hợp** (`d54250c` + thay đổi chưa commit, có pin map v2 + safe-OFF 3 chân) cũng PASS, 1.090/1.090 bước, 0 warning, 0 error — `build-native-windows-2026-10-28/`. Sau khi đồng bộ W02, **worktree tích hợp** `integration/a-w03-w02-sync` (HEAD `efe6075` + thay đổi W03) cũng PASS, 1.090/1.090 bước, 0 warning, 0 error — `build-native-windows-2026-10-28-integrated/`.
**Operator:** Member A (không ghi tên cá nhân trong repo)

## Phạm vi và thẩm quyền

- Thứ tự thẩm quyền: `docs/00` → `docs/01` → `docs/02` → `docs/03` → `docs/04` → `docs/05A`; cụ thể `docs/04 §18` (W03), `docs/05A §12` (A-W03-01…07), `docs/01 §9` (PZEM), `§10` (RS-485), `§11.7/§11.8` (pin map, actuator default-off), `§12` (IBT-2/TEC), gates `H2–H4`.
- Nhánh này **stacked trên W02** (`feat/a-w02-sensor-foundation`) vì W02 chưa merge. PR base là `feat/a-w02-sensor-foundation`; việc retarget `main` sau khi W02 merge thuộc quy trình tích hợp, không phải điều kiện công nhận phần đã kiểm chứng.
- Bộ này **không** sửa nhánh W01/W02, **không** merge PR #7/#8, **không** chạy TEC, **không** tuyên bố PASS cho bất kỳ bài đo phần cứng nào chưa chạy.
- Bộ này **không** chứa dữ liệu tự tạo: file nào nhận được thì lưu byte-for-byte + hash; phần chỉ có lời khai được ghi `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE`; phần chưa đo giữ `MEASUREMENT REQUIRED` / `PENDING`.
- Phiên này **không** publish PR và **không** flash board; hồ sơ chỉ ghi lại cái gì đã được kiểm chứng bằng máy và cái gì chưa.

## Trạng thái tổng quan (chi tiết ở `acceptance.md`)

| Hạng mục | Trạng thái |
|---|---|
| `A-W03-01` XL4015 ~5 V | `PARTIAL` — `VERIFIED BY EXISTING EVIDENCE (W01 operator-reported, no-load)` + `MEASUREMENT REQUIRED` (có tải/ripple/nhiệt) — `logic-power-measurement.md` |
| `A-W03-02` MAX3485 / RS-485 | `PARTIAL` — thực tế là **TTL485-V2.0 5 V auto-direction**, không phải MAX3485; bench Arduino trao đổi 600/600 ở 9600 8N1, **chưa** chạy UART bằng firmware W03. Hạn chế an toàn điện: phải xác nhận mức ở GPIO37 ≤3.3 V trước khi đấu (`CR-A-W01-01` change review mở) — `hardware-deviation-and-safety.md`, `rs485-pin-and-compatibility.md` |
| `A-W03-03` PZEM communication | `DONE` (parser/CRC/read-only + unit test) + `HARDWARE-LIMITED` (chưa chạy firmware W03 trên board) + `MEASURED — BENCH ARTIFACT` (TEST 132B: 600/600 hợp lệ, Arduino, gate `REVIEW REQUIRED`) |
| `A-W03-04` 50 A profile | `DONE` (parse word-order + scaling + unit test) + `PENDING_READBACK` (firmware W03) + `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` (TEST 131: `0x0001`, CRC `0x8479` khớp host-side) — `hardware-2026-10-27/test-131-profile-readback.md` |
| `A-W03-05` OFF electrical envelope | `PARTIAL` — `MEASUREMENT REQUIRED` cho canonical + `MEASURED — BENCH ARTIFACT` (600 mẫu, span **598.99 s**, TEC OFF operator-reported, gate `REVIEW REQUIRED`); `pzem-off.csv` canonical **MISSING** — `team-dependencies.md` `TD-W03-04`/`TD-W03-10` |
| `A-W03-06` Shunt installation inspection | `PARTIAL` — `VERIFIED BY EXISTING EVIDENCE (ảnh W01)` cho marking + `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE` cho continuity + `MEASUREMENT REQUIRED` cho topology return/failure mode — `hardware-2026-10-27/shunt-continuity.md` |
| `A-W03-07` IBT-2 logic only | `DONE` (default OFF, chỉ ghi 0, không PWM, guard từ chối mọi output + kiểm tra tĩnh) + `HARDWARE-LIMITED` (chưa có log cold-boot trên board) + `OPERATOR-REPORTED` (TEST 133B: 120/120 mẫu); lệch cấu hình `GPIO10` continuity chưa đo — `ibt2-pin-map.md` |

## Files

| File | Nội dung |
|---|---|
| `acceptance.md` | **Nguồn trạng thái duy nhất**: acceptance matrix A-W03-01…07, pass criteria canonical, phần còn lại, artifact |
| `team-dependencies.md` | Bảng đầu vào còn thiếu `TD-W03-01…11`: mục nào thiếu, vì sao cần, mở khóa việc gì |
| `logic-power-measurement.md` | A-W03-01: giá trị W01 (operator-reported), điều còn thiếu, kế hoạch đo, điều kiện đo |
| `rs485-pin-and-compatibility.md` | A-W03-02: module từ ảnh W01, ánh xạ chân, mức logic 5 V/3.3 V, điều **không** được giả định |
| `hardware-deviation-and-safety.md` | Lệch freeze TTL485 vs MAX3485 (CR-A-W01-01 PENDING), rủi ro W01, ranh giới an toàn, ba rủi ro mới của phiên 2026-10-27 |
| `pzem-register-readback.txt` | A-W03-04/05: `PENDING_READBACK`; block TEST 131 + TEST 132B; archive 2026-10-20; schema `pzem-off.csv` canonical |
| `ibt2-pin-map.md` | A-W03-07: pin map từ ảnh, default-OFF, TEST 133B, lệch cấu hình `GPIO10`, giới hạn chip `43 A` |
| `firmware-tooling-verification.md` | Firmware + công cụ W03: module, grammar v2, test/check đã chạy, giới hạn, `firmware_commit` |
| `build-report-w03.md` | Build ESP-IDF thật trên GitHub Actions: run URL, log, artifact + SHA-256, giới hạn của tuyên bố compile |
| `review-w03.md` | Biên bản review tĩnh nội bộ (2026-10-19, R1–R15); bản ghi lịch sử, không phải nghiệm thu hiện tại |
| `validate_w03.py` | Kiểm tra cấu trúc hồ sơ + commit firmware + chạy lại static checks + chạy hai bundle verifier; **không** xác nhận vật lý |
| `hardware-2026-10-20/` | Archive bench Arduino: 7 file raw byte-for-byte + hash, 601/594/7, CRC audit, FC06 archive-only |
| `hardware-2026-10-27/` | Bundle bench mới: TEST 131/132B/133B, shunt continuity, as-built, provenance matrix, verifier |
| `build-native-windows-2026-10-27/` | Bundle build native Windows ESP-IDF v6.1 trên commit `f8587dd`: log thô 10-set-target + 20-idf-py-build, checksum artifact, verifier `verify_build.py` |
| `build-native-windows-2026-10-28/` | Bundle build native Windows ESP-IDF v6.1 trên **working tree W03 trước tích hợp** (`d54250c` + thay đổi chưa commit; pin map v2 + safe-OFF 3 chân + comment IBT-2 đã sửa): log thô, `SHA256SUMS.txt`, verifier `verify_build.py`, README |
| `build-native-windows-2026-10-28-integrated/` | Bundle build native Windows ESP-IDF v6.1 trên **worktree tích hợp** `integration/a-w03-w02-sync` (HEAD `efe6075` + thay đổi W03): log thô, `SHA256SUMS.txt`, verifier `verify_build.py`, README — chứng minh **mã nguồn firmware** sẽ giao biên dịch sạch |
| `PR_BODY.md` | Nội dung mô tả PR (bản cục bộ để review trước khi publish) |

## Việc W03 cố ý KHÔNG làm

- Không tạo `pzem-off.csv` canonical hay `rs485-wiring.png` từ trí nhớ: hai file này được khai báo **MISSING**; validator từ chối nếu chúng xuất hiện trên đĩa. CSV bench trong bundle ngày **không** được copy lên root.
- Không tạo log/hex/ảnh thay cho TEST 131, TEST 133B hay shunt continuity: chỉ có lời khai thì ghi là lời khai.
- Không chạy lại test chỉ để sinh file mới; nếu thiếu capture gốc thì ghi `RAW_EVIDENCE_NOT_AVAILABLE`.
- Không dùng archive/bundle Arduino làm bằng chứng ESP-IDF: chúng chỉ chứng minh các byte/log đã có.
- Không nạp/chạy lại sketch SET50 và không gửi FC06 (`ARCHIVE ONLY — DO NOT FLASH OR EXECUTE`).
- Không nạp/chạy firmware W03 trên board trong phiên này (chưa xác nhận mức logic RS-485 ≤3.3 V ở GPIO37).
- Không ghi register PZEM và không đổi profile 50 A (chỉ FC 0x03/0x04).
- Không tạo PWM, không cấp TEC, không đổi pinout/dây/BOM đã freeze.
- Không xử lý lệch `GPIO10` ở mức phần cứng (chỉ đổi cấu hình firmware sang map v2) và không kết luận topology shunt: cả hai còn `MEASUREMENT REQUIRED`.

## Reproduction / review

1. `py firmware/tools/run_all_checks_w03.py` từ gốc repo → **5/5 PASS**: unittest (W02+W03), static W03, static W02 (regression), `validate_w02.py`, `validate_w03.py`. Lớp `validate_w03.py` bao gồm cả hai bundle verifier (2026-10-20 và 2026-10-27).
2. `py evidence/A/W03/validate_w03.py` → file bắt buộc, khai báo MISSING, nhãn trạng thái, `firmware_commit` (git cat-file/show), workflow CI, content anchors, static checks, và hai bundle verifier.
3. `py evidence/A/W03/hardware-2026-10-27/verify_test132b.py` → hash, 600 hàng, min/max/mean, `rx_len`, span `598.99 s`, gate `REVIEW REQUIRED`, CRC TEST 131.
4. `py evidence/A/W03/hardware-2026-10-20/verify_capture.py` → 7/7 hash, 601/594/7, 7 frame CRC, shunt log `0x0001` không có raw FC03, cảnh báo FC06.
5. Đọc `provenance-matrix.md` để biết câu nào là đo / lời khai / suy luận / chưa đo.
6. Đọc `hardware-deviation-and-safety.md` trước khi cấp nguồn cho khối RS-485.
7. `build-report-w03.md`: build ESP-IDF thật trên CI — run `39213118829` **SUCCESS cả hai job** cho commit `0171d0a`; run đầu FAIL (lỗi biên dịch thật) được giữ nguyên để truy vết. Patch echo/prefix **chưa** có run CI mới.

## Handoffs

- **Giao diện cho C:** field semantics của PZEM (`v/i/p/e`, `status`, `attempts`, `exc`, `ok/fail`) và quy ước lỗi/timeout giữ nguyên token như W03 định nghĩa (`cg_pzem.h` ↔ `cg_modbus.py`); chưa có số liệu ESP-IDF thật để thay fixture.
- **Đầu vào còn thiếu — phép đo/kiểm chứng vật lý:** `TD-W03-01` (mức logic RS-485), `TD-W03-02` (topology return/failure mode shunt), `TD-W03-03` (continuity `GPIO10`), `TD-W03-04` (cách tính cửa sổ 598.99 s), `TD-W03-05` (capture gốc TEST 131/133B), `TD-W03-06` (tie-off + log cold-boot), `TD-W03-09` (XL4015 có tải).
- **Đầu vào còn thiếu — cấu hình/quy trình:** `TD-W03-07` (FC06 SET50 trong archive), `TD-W03-08` (`hardware_config_id` as-built), `TD-W03-10` (chính sách `pzem-off.csv` canonical), cùng change review `CR-A-W01-01` (lệch TTL485).
