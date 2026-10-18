# ColdGuard — Member A — W02 sensor foundation

**Snapshot:** 2026-10-18 (cập nhật 5: build CI + BME280 bench + MC-38 bench thô + DS18B20 620 mẫu bench) · **Role:** Member A (Embedded & Thermal) · **Status:** `DRAFT / REVIEW REQUIRED — W02 NOT PASS` · **hardware_config_id:** `NOT_ASSIGNED` · **Firmware commit (repo):** `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` · **Build ESP-IDF thật (CI):** `SUCCESS — esp32s3` (`build-report-w02.md`) · **BME280 bench (standalone):** `PASS — 403/403 mẫu` (`bme280/`) · **MC-38 bench thô (standalone):** `PASS — 48 cặp RAW/STABLE, 24 chu kỳ, polarity có dấu` (`mc38/`) · **DS18B20 bench thô (standalone):** `PASS — 620/620 mẫu, 619 s` (`ds18b20/`) · **Firmware sketch bench (nguồn 3 ảnh):** `NOT_IN_REPO` · **Operator:** Member A (không ghi tên cá nhân trong repo)

## Phạm vi và thẩm quyền

- Thứ tự thẩm quyền: `docs/00` → `docs/01` → `docs/02` → `docs/03` → `docs/04` → `docs/05A`; cụ thể `docs/04 §17` (W02), `docs/05A §11` (A-W02-01…07), `docs/03 §14–§15` (`HW-H0-01`, `HW-H0-02`, `SEN-H1-01…05`).
- Bộ này **không** viết lại Docs 00–04, **không** sửa lịch canonical, **không** đánh dấu H0 PASS.
- Bộ này **không** chứa dữ liệu tự tạo. Mọi số liệu trong đây đều bắt nguồn từ ảnh log thật do người dùng cung cấp (W02 bench session), hoặc là đại lượng dẫn xuất được tính lại công khai từ chính các số đó.
- Bộ này **không** phải nghiệm thu vật lý. Nó là hồ sơ bằng chứng để review.

## Provenance của ảnh

- **Archive nguồn:** `ColdGuard_A_W02_Existing_Test_Screenshots.zip` · 81 661 bytes · SHA-256 `383CBB4A323AD4E524C1E76348C30DACA4C161C42E85CD9A20C33586D5B97429`.
- 3 ảnh PNG được sao chép **nguyên byte** vào thư mục này: không crop, không nén lại, không chỉnh màu, không ghi đè chú thích. Kích thước và SHA-256 từng ảnh được khai báo trong `screenshot-provenance.csv` và được `validate_w02.py` kiểm tra lại trên đĩa.
- `source-archive-readme.md` là bản sao **nguyên văn** của `README.md` bên trong archive — chính người dùng viết — dùng làm nguồn truy xuất nguồn và mô tả giới hạn từ phía người tạo ảnh.
- Ảnh là **cửa sổ hiển thị Serial Monitor COM4 @ 115200 baud, `Show timestamp = OFF`**. Việc timestamp bị tắt là một giới hạn thật và được nêu ở mọi file liên quan.

### Ảnh chứng minh gì — và KHÔNG chứng minh gì

| Ảnh | Chứng minh | KHÔNG chứng minh |
|---|---|---|
| `w02_rom_enumeration_4_devices.png` | 4 ROM DS18B20 phân biệt được liệt kê; cả 4 đọc được giá trị trong cùng phiên; firmware tự báo `PASS: 4 DS18B20 detected` | đầu dò vật lý nào là T1/T2/T3; nhãn vật lý; ổn định ROM→role qua reboot; ngữ nghĩa OPEN/CLOSED của MC-38 |
| `w02_ds18b20_600_samples_summary.png` | summary thật với `valid=600/600` và mean/sd/min/max cho từng đầu dò | đủ 600 dòng dữ liệu; timestamp thật; nhịp ~1 Hz; đủ 10 phút theo đồng hồ; ý nghĩa các cột |
| `w02_mc38_24_cycles.png` | bộ đếm chuyển mức đạt 24 chu kỳ | debounce; polarity; timestamp sự kiện; tổng số chu kỳ của phiên |

**Ảnh summary xác nhận rằng kết quả đã được hiển thị. Ảnh không thay thế CSV 600 dòng, không thay thế timestamp thật, và ảnh MC-38 không tự chứng minh debounce hay polarity.**

## Files

| File | Nội dung |
|---|---|
| `sensor-rom-map.yaml` | Ánh xạ ROM → vai trò T1/T2/T3 + SPARE; trạng thái `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`; trạng thái từng test liên quan danh tính; nay khớp từng byte với firmware trong repo |
| `firmware-implementation.md` | Firmware W02 trong repo: bản đồ module, grammar log, ràng buộc canonical ↔ kiểm tra tự động, kết quả chạy, và **các giới hạn đã khai báo** (đã biên dịch thật trên CI, chưa nạp/chạy, không có ROM search, BME280 ngoài phạm vi) |
| `build-report-w02.md` | Build ESP-IDF thật trên GitHub Actions (image `espressif/idf:v6.1`, target `esp32s3`): run URL, log, artifact + SHA-256, lỗi build đầu và cách sửa, giới hạn của tuyên bố compile |
| `bme280/` (×3) | Bằng chứng bench BME280 thật (ESP32-S3, sketch Arduino/Adafruit): log gốc + CSV 403/403 mẫu + báo cáo; SHA-256 ở `acceptance.md §4.1`/§11. **Không** phải firmware ESP-IDF |
| `mc38/` (×3) | Bằng chứng bench MC-38 thật (ESP32-S3, sketch standalone): log thô 48 cặp RAW/STABLE + CSV dẫn xuất + báo cáo; polarity `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` có dấu trong log; SHA-256 ở `door-test-summary.md`/`acceptance.md §4.2`/§12. **Không** phải firmware ESP-IDF |
| `ds18b20/` (×4) | Bằng chứng bench DS18B20 thật — phiên **620 mẫu** (ESP32-S3, sketch standalone): log thô + CSV 620/620 mẫu (619 s, đều 1000 ms) + báo cáo capture + xác minh độc lập; ROM discovery cùng-capture `PENDING` (dời sang bài 5 reboot); SHA-256 ở `acceptance.md §4.3`/§13. **Không** phải firmware ESP-IDF |
| `bench-procedure-w02.md` | Danh sách ngắn các bước **chỉ** làm được bằng phần cứng: nạp firmware đã build, 5 reboot, 10 phút consistency, chu kỳ cửa + polarity, dán nhãn, vị trí gá BME280 cuối — kèm lệnh cụ thể và file phải sinh ra |
| `sensor-consistency-summary.md` | `SEN-H1-03` / `A-W02-05`: phiên **620 mẫu** mới nhập (`ds18b20/`, thống kê tính lại, giới hạn ROM tường minh) + bảng 600 mẫu/đầu dò của phiên cũ, chênh lệch cặp, độ ổn định, danh sách điều **không** chứng minh được |
| `door-test-summary.md` | `SEN-H1-05` / `A-W02-07`: đọc bộ đếm MC-38, đối chiếu tiêu chí, lý do polarity và debounce còn `PENDING` |
| `screenshot-provenance.csv` | Truy xuất nguồn từng ảnh: kích thước, SHA-256, file nguồn trong archive, nội dung, giới hạn |
| `acceptance.md` | **Nguồn trạng thái duy nhất**: acceptance matrix A-W02-01…07, tiêu chí PASS canonical, blocker, quyết định cần leader |
| `validate_w02.py` | Kiểm tra cấu trúc: file bắt buộc, hash ảnh khớp provenance, YAML parse được, không có CSV thiếu cột. **Không** xác nhận đúng/sai vật lý |
| `PR_BODY.md` | Nội dung mô tả PR đề xuất (bản cục bộ để review trước khi publish) |
| `source-archive-readme.md` | Bản sao nguyên văn README trong archive nguồn |
| `w02_*.png` (×3) | Ảnh log gốc, byte-identical |

## Trường bắt buộc theo `docs/05A §8`

| Trường | Giá trị |
|---|---|
| `date` | 2026-10-18 (ngày nhận và kiểm chứng archive; phiên bench do người dùng thực hiện trước đó) |
| `operator` | Member A (người vận hành vật lý; không ghi tên cá nhân trong repo) |
| `hardware_config_id` | `NOT_ASSIGNED` — chưa được leader gán |
| `firmware commit` | `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` → commit firmware W02 trong repo (`firmware/main/`, 7 module C; **không** phải nguồn của 3 ảnh; đã build thật trên CI — `build-report-w02.md`) · sketch bench sinh ra 3 ảnh: `NOT_IN_REPO` |
| `test IDs` | `HW-H0-01`, `HW-H0-02` (chưa thực hiện), `SEN-H1-01` (partial), `SEN-H1-02` (not performed), `SEN-H1-03` (partial), `SEN-H1-04` (partial — bench BME280 standalone PASS; tích hợp ESP-IDF chưa), `SEN-H1-05` (partial) |
| `setup` | Bench không cấp nguồn TEC; 4 đầu dò DS18B20 trên một bus 1-Wire; MC-38 nối vào board; Serial Monitor COM4 @ 115200, không bật timestamp |
| `result` | ROM map 3 vai trò + 1 spare; 600/600 mẫu hợp lệ × 4 đầu dò; MC-38 24 chu kỳ; BME280 bench standalone PASS (403/403 mẫu, chip-ID `0x60`, I²C `0x76`) — chưa tích hợp ESP-IDF |
| `pass/fail` | **`NOT PASS`** — `W02_PARTIAL_EVIDENCE` (chi tiết và blocker ở `acceptance.md`) |
| `anomalies` | Lệch số lượng đầu dò 4 so với canonical 3; **khối `TEMPERATURE` đầu tiên trong ảnh enumeration bị thiếu một dòng có nhãn** (xem §“Bất thường quan sát được”); không có timestamp; không có CSV thô; không có log reboot; chưa freeze polarity MC-38; chưa có H0 |

Bảng này **không** phải nguồn trạng thái; trạng thái canonical nằm duy nhất ở `acceptance.md`.

## Tóm tắt trạng thái W02 (chi tiết ở `acceptance.md`)

| Hạng mục | Trạng thái |
|---|---|
| `A-W02-01` H0 mechanical | `DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING` |
| `A-W02-02` DS18B20 enumeration | ROM→vai trò **đã ghi cứng vào firmware** + đối chiếu tự động; nhãn vật lý vẫn `PENDING`; lệch canonical 3→4 chờ leader |
| `A-W02-03` reboot identity proof | `IMPLEMENTED — HARDWARE RUN PENDING` (cơ chế + công cụ đã test tự động; chưa có log thật) |
| `A-W02-04` acquisition implementation | `IMPLEMENTED — COMPILE VERIFIED (CI)` — `HARDWARE RUN PENDING` (firmware trong repo; build thật SUCCESS trên CI: `build-report-w02.md`; sketch bench cũ vẫn `RAW_EVIDENCE_PENDING`) |
| `A-W02-05` inter-sensor consistency | `BENCH DATA VERIFIED — 620 RAW SAMPLES CAPTURED` (phiên sketch Arduino: 620/620 mẫu, 619 s, thống kê tái lập — `ds18b20/`; ROM cùng-capture `PENDING`, dời sang bài 5 reboot) · phiên 600 mẫu cũ vẫn `RAW CSV MISSING` |
| `A-W02-06` BME280 | `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED` (bài bench thật 403/403 mẫu — `bme280/`; vị trí gá cuối vẫn `PENDING_TEST`) |
| `A-W02-07` MC-38 | `BENCH VERIFIED — ESP-IDF INTEGRATION NOT VERIFIED` — log thô 48 cặp RAW/STABLE (debounce 40 ms, 24 chu kỳ, polarity `NEAR=LOW=CLOSED / FAR=HIGH=OPEN` có dấu trong log — `mc38/`); firmware ESP-IDF vẫn `PENDING` |

## Bất thường quan sát được (khai báo tường minh)

1. **Ảnh `w02_rom_enumeration_4_devices.png`, khối `TEMPERATURE` đầu tiên sau dòng `PASS: 4 DS18B20 detected` không đầy đủ:** khối đó in `DS1: 29.81 C` → `29.56 C` (**không có tiền tố nhãn**) → `DS4: 29.88 C` → `Valid: 4/4`, tức **thiếu một dòng có nhãn** so với 6 khối sau (mỗi khối sau đều đủ `DS1`/`DS2`/`DS3`/`DS4`). Bộ chứng cứ này **không** suy đoán nguyên nhân (lỗi in của sketch, mất ký tự trên đường serial, hay hiện tượng ghi đè dòng đều có thể giải thích). Đây là lý do bổ sung để cần **nguồn sketch bench** và **log thô** trước khi kết luận về hành vi in của phiên cũ — firmware W02 trong repo là bản triển khai mới, **không** phải nguồn của ảnh này, nên không dùng nó để suy ngược hành vi sketch cũ.
2. **Khối `TEMPERATURE` cuối cùng của ảnh `w02_mc38_24_cycles.png` bị cắt:** ảnh dừng ở `DS2: 30.19 C`, nên không thấy `DS3`/`DS4`/`Valid` của khối đó.
3. **Một khối trong ảnh enumeration in `DS3: 29.50 C`** trong khi các khối khác in `29.56 C` (đã ghi ở `sensor-consistency-summary.md §5`; nằm ngoài cửa sổ 600 mẫu).

Cả ba điểm trên đều **không** làm thay đổi kết luận của hồ sơ, nhưng được khai báo vì hồ sơ này đặt chuẩn “nêu tường minh”.

## Reproduction / review

1. Chạy `py firmware/tools/run_all_checks.py` từ gốc repo: chạy 3 lớp kiểm tra không cần phần cứng (57 test công cụ + 39 kiểm tra tĩnh firmware + `validate_w02.py`). Exit code 0 chỉ khi cả ba PASS.
2. Chạy riêng `py validate_w02.py` trong thư mục này. Script kiểm tra cấu trúc, SHA-256 ảnh, ROM map khớp firmware, `firmware_commit` trỏ tới một commit thật **chứa đủ 5 module W02** (`app_main.c`, `cg_onewire.c`, `cg_rom_map.c`, `cg_ds18b20.c`, `cg_door.c`) với ROM bytes trong `coldguard_config.h` khớp từng byte; **không** chạy bất kỳ phép xác minh vật lý nào.
3. Kiểm tra ảnh khớp với `screenshot-provenance.csv`: `Get-FileHash .\w02_*.png -Algorithm SHA256`.
4. Kiểm tra lại **archive gốc** (an toàn hơn kiểm tra ảnh trên đĩa, vì khoá tin cậy không nằm trong repo): `Get-FileHash "$env:USERPROFILE\Downloads\ColdGuard_A_W02_Existing_Test_Screenshots.zip" -Algorithm SHA256` phải trả về `383CBB4A323AD4E524C1E76348C30DACA4C161C42E85CD9A20C33586D5B97429` (81 661 bytes).
5. Đối chiếu từng con số trong `sensor-consistency-summary.md` với ảnh `w02_ds18b20_600_samples_summary.png` (đặc biệt 4 dòng `# S1…S4`).
6. Đối chiếu số học bộ đếm MC-38 trong `door-test-summary.md` §2 với ảnh `w02_mc38_24_cycles.png`.
7. Đọc `firmware-implementation.md` để biết firmware trong repo làm gì, đã được kiểm chứng tới đâu, và **chưa** làm gì.
8. Đọc `acceptance.md` để biết chính xác hạng mục nào PASS/PARTIAL/PENDING và ai cần quyết định gì.
9. Đọc `build-report-w02.md` để xem build ESP-IDF thật trên CI (run URL, log, artifact, SHA-256) và giới hạn của tuyên bố compile.
10. Đối chiếu 3 tệp trong `bme280/` với SHA-256 ghi ở `acceptance.md §4.1`/`§11` (log gốc, CSV, báo cáo).
11. Đối chiếu tệp trong `mc38/` với SHA-256 ghi ở `acceptance.md §4.2`/`§12`: log gốc giữ nguyên byte (CRLF), CSV tái dựng được từ log bằng script xác minh (48/48 cặp +40 ms, bộ đếm 1..48, 24 chu kỳ).
12. Đối chiếu tệp trong `ds18b20/` với SHA-256 ghi ở `acceptance.md §4.3`/`§13`: 620 mẫu liên tục, uptime 42 014→661 014 (619 s, đều 1000 ms), 4 vai trò hợp lệ 620/620, CSV khớp log từng dòng; raw log chứa **0 dòng ROM** — cảnh báo ROM được giữ như bản gốc.

## Handoffs

- **To B:** ngữ nghĩa vị trí sẽ dùng cho feature spatial — nhưng hiện **chưa** có vị trí vật lý đã freeze; `sensor-consistency-summary.md` chỉ là consistency check, **không** phải calibration. Chưa dùng được cho dataset.
- **To C:** fixture JSON cho cảm biến thật **chưa** được cung cấp trong PR này; schema bench (`index,giây,DS1..DS4,valid,…`) **khác** `backend/fixtures/telemetry_v0.json` nên không được nhầm hai thứ này.
- **To D:** chưa có hành vi `physical-quality` trên cảm biến thiếu; `A-W02-04` mới chỉ có bằng chứng gián tiếp nên chưa thể chốt semantics degraded.
- **To leader:** quyết định lệch số lượng đầu dò (kế thừa `CR-A-W01-04`), lịch H0 (`A-W02-01`), và xác nhận tiêu chí nghiệm thu còn thiếu cho W02.

## Cổng chất lượng W02

**Chưa PASS.** Có bốn nhóm bằng chứng thật (enumeration, consistency summary, door cycles, **bench BME280**), một bản đồ ROM vai trò đã ghi cứng vào firmware, một lớp công cụ + test tự động đã chạy PASS và **firmware đã được biên dịch thật trên CI** — nhưng vẫn thiếu dữ liệu thô, thiếu timestamp cho phiên cũ, thiếu **tích hợp BME280 vào firmware ESP-IDF** (bài bench standalone đã xong), thiếu log reboot, thiếu H0, và firmware **chưa** được nạp/chạy. Hồ sơ ở mức **PR-reviewable** với blocker nêu tường minh, không che giấu phần còn thiếu.

### Phân biệt hai loại "đã xong" (quan trọng khi review)

| Loại | Nghĩa | Ví dụ trong PR này |
|---|---|---|
| **Đã làm xong, có bằng chứng máy kiểm được** | Chạy lại được bằng một lệnh, kết quả khớp | Công cụ + test (`run_all_checks.py` 3/3 PASS: 57 test + 39 check tĩnh + validator hồ sơ); ROM map ↔ firmware ↔ CRC8; parser/CSV/debounce |
| **Đã implement + compile thật, chưa chạy trên phần cứng** | Code có trong repo, logic đã được kiểm tra tĩnh và **đã biên dịch thật trên CI**, nhưng **chưa** nạp/đo | Firmware W02 (`A-W02-03/04/07` phần code; build: `build-report-w02.md`) |
| **Chưa thể làm nếu không có phần cụ thể** | Cần người thao tác | 5 reboot, 10 phút consistency, polarity cửa, dán nhãn, vị trí gá BME280 cuối, H0 |
