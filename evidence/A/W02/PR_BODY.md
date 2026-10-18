# [A-W02] Sensor Foundation, ROM Mapping and Bench Evidence

> **⚠️ W02 NOT PASS — READ FIRST.** Bộ chứng cứ này là `W02_PARTIAL_EVIDENCE`, **không** phải nghiệm thu W02. Mở PR này **không** đồng nghĩa W02 đã PASS. Lần cập nhật gần nhất bổ sung **build ESP-IDF thật trên CI** (image `espressif/idf:v6.1`, target `esp32s3`, **SUCCESS**, 0 cảnh báo — `build-report-w02.md`) sau khi sửa requirements GPIO; firmware **đã biên dịch** nhưng **chưa** nạp và **chưa** chạy trên board. Hai hạng mục còn treo: `A-W02-06` BME280 (`PENDING_TEST`) và `A-W02-01` H0 mechanical (`DEFERRED`, chờ trưởng nhóm quyết định lịch).

**Base:** `main` · **Head:** `feat/a-w02-sensor-foundation` · **Loại:** NORMAL PR (Ready for Review — không phải Draft)
**Issue/pack:** `A-W02-01` … `A-W02-07`
**Parent docs:** `docs/04 §17` (W02), `docs/05A §11` (Member A W02), `docs/03 §14–§15` (`HW-H0-01/02`, `SEN-H1-01…05`), `docs/01 §6.4–§6.6` (identity contract)
**Reviewer bắt buộc:** Member D (`docs/04 §3.3`: physical wiring / pin / sensing)
**Hardware config affected?:** Chưa — `hardware_config_id` vẫn `NOT_ASSIGNED`. PR này ghi nhận danh tính cảm biến, không thay đổi BOM freeze.
**Evidence path:** `evidence/A/W02/`
**Trạng thái W02:** **`W02_PARTIAL_EVIDENCE` — KHÔNG phải W02 PASS.** Mở PR này **không** đồng nghĩa W02 đã nghiệm thu. Firmware W02 trong repo: `2a5a0dacd2bfa3feb62f4b626f2a403e23bf39bc` — đã **biên dịch thật trên CI** (run 39117530768, SUCCESS; artifact + SHA-256: `build-report-w02.md`), **chưa** nạp và **chưa** chạy.

---

## 1. Member A đã hoàn thành những gì

- **Bản đồ ROM → vai trò DS18B20** (`sensor-rom-map.yaml`): T1 gần cửa `287088CA00000051`, T2 trung tâm `28AEBF2200000006`, T3 đối diện cửa `28CBE9CA00000072`, và một đầu dò dự phòng `283BE5C9000000A9`. Trạng thái ghi đúng là `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` — **đầu dò vật lý chưa được dán nhãn**, không tự nhận là đã xong. Bản đồ này nay **đã được ghi cứng vào firmware** và được đối chiếu tự động từng byte + CRC8.
- **Firmware W02 trong repo** (`firmware/main/`, 7 module C): đọc DS18B20 theo ROM cố định (không phụ thuộc thứ tự discovery), một lần chuyển đổi dùng chung cho cả bus, vòng lặp ~1 Hz theo deadline với `uptime_ms` là thời điểm thật, `nan` khi đọc lỗi/mất đầu dò, MC-38 debounce cấu hình được + không đoán polarity, NVS `boot_count` + khối `#CG ROM` mỗi lần boot, và ép IBT-2 OFF ngay đầu `app_main`; nay **đã được biên dịch thật** trên GitHub Actions (ESP-IDF v6.1, `esp32s3`, SUCCESS, 0 cảnh báo — `build-report-w02.md`). Chi tiết: `firmware-implementation.md`.
- **Công cụ kiểm chứng host** (`firmware/tools/`): parser log, xác minh reboot identity, dựng `sensor-consistency.csv`, dựng `door-test.csv` (bắt buộc `--open-level` do người vận hành quan sát), kiểm tra tĩnh firmware, và một lệnh gộp `run_all_checks.py`. 57 test `unittest` + 39 kiểm tra tĩnh đều PASS trên máy hiện tại.
- **Tổng hợp inter-sensor consistency** (`sensor-consistency-summary.md`): bảng 600 mẫu/đầu dò, chênh lệch trung bình từng cặp và chênh lệch lớn nhất (0.603 °C, DS2 vs DS3), kèm phân tích vì sao các SD (0.018–0.031 °C) thấp hơn một bước lượng tử 12-bit. Ghi rõ đây là **consistency check, KHÔNG phải calibration**.
- **Tổng hợp bài test cửa MC-38** (`door-test-summary.md`): đọc bộ đếm thô, kiểm tra số học `cycles = floor(transitions/2)`, và đối chiếu tiêu chí ≥20 chu kỳ (đạt 24).
- **Hồ sơ truy xuất nguồn ảnh** (`screenshot-provenance.csv`) + **kiểm tra cấu trúc tự động** (`validate_w02.py`) + **acceptance matrix A-W02-01…07** (`acceptance.md`) + `README.md` + **quy trình bench còn thiếu** (`bench-procedure-w02.md`).

## 2. Bằng chứng thật tương ứng

Ba ảnh log gốc của phiên bench W02, do người dùng cung cấp qua archive `ColdGuard_A_W02_Existing_Test_Screenshots.zip` (81 661 bytes, SHA-256 `383CBB4A…B97429`), được sao chép **nguyên byte** (không crop, không nén lại, không chỉnh sửa):

| Ảnh | Nội dung thật | Ý nghĩa |
|---|---|---|
| `w02_rom_enumeration_4_devices.png` | COM4 Serial Monitor: `DS18B20 found: 4`, 4 ROM hex, `MC38 initial: HIGH`, `PASS: 4 DS18B20 detected`, các khối nhiệt độ `DS1..DS4` với `Valid: 4/4` | 4 ROM phân biệt, cả 4 đọc được giá trị trong cùng phiên |
| `w02_ds18b20_600_samples_summary.png` | 9 dòng CSV cuối (592–600) + `# W02 SUMMARY`: `valid=600/600` và `mean/sd/min/max` cho S1–S4 + `# W02 TEST FINISHED` | Kết quả summary **được hiển thị** cho 600 mẫu/đầu dò |
| `w02_mc38_24_cycles.png` | 6 dòng `MC38: LOW/HIGH \| transitions: 43..48 \| cycles: 21..24`, xen kẽ khối nhiệt độ | Bộ đếm chuyển mức đạt **24 chu kỳ** trong phiên bench |

Số liệu chi tiết (mean 29.882/30.214/29.611/29.935 °C; sd 0.028/0.031/0.026/0.018 °C) được ghi nguyên văn và tính lại công khai trong `sensor-consistency-summary.md`.

**Ảnh xác nhận kết quả đã được hiển thị — ảnh KHÔNG thay thế CSV 600 dòng, KHÔNG thay thế timestamp thật, và ảnh MC-38 KHÔNG tự chứng minh debounce hay polarity.** Không có dữ liệu, log hay kết quả test nào được tạo mới trong PR này.

## 3. BME280 (A-W02-06) — chờ test tối nay

- **Trạng thái:** `PENDING_TEST — USER PLANS TO COMPLETE TONIGHT`.
- **Hiện có:** không có kết quả chip-ID, không có kết quả I²C, không có T/RH.
- Member A sẽ **bổ sung một commit mới vào chính PR này** sau khi test BME280 thật xong. PR này vì vậy được tạo ở trạng thái **Ready for Review** nhưng **chưa** đủ điều kiện để chốt W02.
- **Không** có bất kỳ dòng nào trong PR này đánh dấu BME280 PASS.

## 4. H0 mechanical (A-W02-01) — đề xuất hoãn, cần leader quyết định

- **Trạng thái:** `DEFERRED — TEAM LEADER SCHEDULE APPROVAL PENDING`.
- **Đề xuất của Member A:** hoãn việc lắp ráp lên thùng sang giai đoạn hoàn thiện cơ khí, hướng tới **W07 geometry freeze**, để các module được test trên bàn trước — lỗi dễ phát hiện hơn và linh kiện dễ thay thế hơn so với khi đã lắp trong thùng.
- **Bốn điểm bắt buộc phải nói rõ:**
  1. **Canonical W02 vẫn yêu cầu H0** — đây là đề xuất, **chưa** được duyệt.
  2. **W07 geometry freeze không tự động thay thế H0 của W02.** Hai mốc khác nhau về thời điểm, mục đích và bằng chứng.
  3. **Trưởng nhóm phải xác nhận điều chỉnh lịch** trước khi đổi bất kỳ trạng thái nào.
  4. **Ảnh hưởng tới W04 thermal commissioning:** W04 cần cụm V1/TEC đã lắp đúng và một plant mô tả được để đo đáp ứng nhiệt/gradient. Nếu H0 chưa xong, W04 chỉ chạy được phần logic/điện (XL4015, MAX3485/PZEM, IBT-2 logic) và **không** tạo được bằng chứng nhiệt có ý nghĩa; **Gate G1** (`docs/04 §19` — Physical/Protocol Preliminary: sensor identity, PZEM valid, IBT-2 default-off, safe first TEC response, real telemetry path, twin separation) có nguy cơ không đạt trong W03–W04 như lịch hiện tại.
- PR này **không** sửa lịch canonical và **không** đánh dấu H0 PASS.

## 5. Những gì CHƯA xác minh (nêu tường minh)

| Hạng mục | Trạng thái | Chi tiết |
|---|---|---|
| Log/CSV dữ liệu thô 600 dòng của **phiên cũ** | **`RAW_EVIDENCE_PENDING`** | Chỉ có 9 dòng CSV hiển thị trong ảnh; **không có** `sensor-consistency.csv` của phiên cũ ⇒ không thể tính lại mean/SD độc lập từ dữ liệu gốc. Công cụ dựng CSV cho phiên mới đã sẵn sàng và đã test |
| `door-test.csv` thô của **phiên cũ** | **`RAW_EVIDENCE_PENDING`** | Chỉ có 6 dòng log hiển thị; không có file. Công cụ dựng CSV cho phiên mới đã sẵn sàng và đã test |
| Log 5 chu kỳ reboot (A-W02-03) | **`IMPLEMENTED — HARDWARE RUN PENDING`** | Cơ chế + công cụ xác minh đã xong và đã test tự động (5 khối dán lặp ⇒ `BOOT_METADATA_INVALID`, không thể giả 5 reboot); **chưa** chạy 5 lần reset trên board ⇒ `no silent remap across reboot` **chưa** được chứng minh |
| Nhãn vật lý T1/T2/T3 | **PENDING** | Đầu dò chưa được nhận diện/dán nhãn ⇒ leader review "chỉ tay vào T1/T2/T3" chưa thực hiện được |
| Timestamp của **phiên cũ** | **KHÔNG có** | Serial Monitor để `Show timestamp = OFF`; nhịp ~1 Hz và độ dài ≥10 phút của phiên cũ chỉ là **suy luận**. Phiên mới sẽ có `uptime_ms` thật trong từng dòng `#CG SAMPLE` |
| Polarity MC-38 (`raw → OPEN/CLOSED`) | **`PENDING_POLARITY_CONFIRMATION`** | Ảnh chỉ có mức thô `LOW/HIGH`. Firmware mới **không** giả định polarity (`state=UNVERIFIED`), công cụ `cg_build_door_csv.py` **bắt buộc** `--open-level` do người vận hành quan sát |
| Debounce MC-38 | **Đã implement — chờ đo trên phần cứng** | `CG_DOOR_DEBOUNCE_MS=50` (cấu hình được) + đếm `raw_edges`/`discarded_edges` làm bằng chứng dội; mô hình debounce đã được test tự động. Chưa có số đo thật |
| Nguồn firmware sketch bench (sinh ra 3 ảnh) | **`NOT_IN_REPO`** | Repo nay có **firmware W02 chính thức mới** (`firmware/main/`), nhưng đó **không** phải nguồn của 3 ảnh — không dùng nó để suy ngược hành vi sketch cũ |
| Error handling khi đọc DS18B20 lỗi/mất | **Đã implement — chưa chạy thật** | `nan` khi thiếu/CRC lỗi/85 °C power-on/ngoài dải; `VALID/DEGRADED/INVALID` theo docs/01 §6.8; chưa có bài test phần cứng rút một đầu dò |
| `sensor-placement.png`, ảnh H0 | **MISSING** | Không vẽ lại từ trí nhớ, không tạo ảnh giả |
| Biên dịch firmware | **PASS trên CI (ESP32-S3)** | GitHub Actions, image `espressif/idf:v6.1` + target `esp32s3`: **SUCCESS**, 0 cảnh báo, artifact + SHA-256 trong `build-report-w02.md`; máy cục bộ vẫn không có ESP-IDF/Docker |
| Nạp + chạy firmware | **CHƯA** | Chưa flash, chưa mở serial, chưa có dòng `#CG …` thật nào |
| Lệch số lượng đầu dò | **Chờ quyết định** | Canonical `SEN-H1-01` ghi 3 ROM; thực tế 4 đầu dò (kế thừa `CR-A-W01-04`) |
| `hardware_config_id`, ngày review | **Chưa gán** | Cần leader gán. `firmware_commit` đã ghi SHA thật (xem mục đầu của body này) |

## 6. Điều kiện để W02 được nghiệm thu

W02 chỉ có thể chuyển sang PASS khi tất cả các điều kiện sau được đáp ứng (`acceptance.md §5` là nguồn canonical):

1. `A-W02-06`: kết quả BME280 thật (chip-ID, I²C address, T/RH hợp lý, vị trí gá) — commit bổ sung vào PR này.
2. `A-W02-03`: log ≥5 chu kỳ reboot/discovery chứng minh ROM→role giữ nguyên (chạy `cg_verify_reboots.py` trên log thật).
3. `A-W02-05`: `sensor-consistency.csv` từ phiên ≥10 phút chạy bằng firmware mới (nhịp và độ dài khi đó **đo được**).
4. `A-W02-07`: quan sát vật lý polarity + `door-test.csv` với `--open-level` + số cạnh thô/chu kỳ làm bằng chứng debounce.
5. `A-W02-02`: dán nhãn vật lý T1/T2/T3 (+ SPARE), có ảnh nhãn; nâng trạng thái khỏi `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING`.
6. `A-W02-01`: quyết định của leader về H0 (giữ trong W02 hay dời sang giai đoạn hoàn thiện cơ khí hướng W07), kèm ảnh/checklist nếu chuyển.
7. `A-W02-04`: đã đưa firmware W02 vào repo + ghi `firmware_commit`, và **build log đã có** (CI ESP-IDF v6.1, `esp32s3`, SUCCESS — `build-report-w02.md`); **còn lại** là một lần nạp/chạy thật. Nguồn sketch bench cũ vẫn `NOT_IN_REPO`.
8. Leader xác nhận lệch số lượng đầu dò và gán `hardware_config_id` + ngày review.

Thêm hai điều kiện về tiêu chí: leader xác nhận `A-W02-05` chỉ cần **consistency check** (không cần chuẩn truy vết) ở W02, và chấp nhận việc merge PR này khi W02 vẫn ở trạng thái `PARTIAL` (PR là để review hồ sơ, không phải để tuyên bố PASS).

## 7. Quyết định cần Team Leader phê duyệt

| Nội dung | Vì sao cần leader |
|---|---|
| Cho phép hoãn H0 hay buộc H0 xong trong W02 | Canonical W02 yêu cầu H0; W07 không tự động thay thế |
| Chấp nhận cấu hình 4 đầu dò (3 vai trò + 1 spare) | Lệch với `SEN-H1-01` ("3 unique ROM IDs"); W01 đã ghi `CR-A-W01-04` |
| Xác nhận `A-W02-05` chỉ cần consistency check | `docs/03 §15` cho phép gọi là consistency check, nhưng cần chốt phạm vi |
| Chấp nhận merge PR khi W02 `PARTIAL` | Để không chặn review kỹ thuật và commit BME280 tiếp theo |

## 8. Trọng tâm review cho Member D

1. Cách đọc số liệu consistency: 0.603 °C chênh lệch trung bình lớn nhất **không** được diễn giải thành sai số cảm biến, và **không** có ngưỡng số nào được tự đặt. Kiểm tra xem cách lập luận này có bị hiểu thành "sensor đã đạt yêu cầu" hay không.
2. Xác nhận rằng `ROLE_ASSIGNED_PHYSICAL_LABEL_PENDING` là trạng thái **đúng** và chưa có gì bị nâng cấp quá mức.
3. Xác nhận lập luận vì sao `MC38 initial: HIGH` **không** đủ để freeze polarity.
4. Kiểm tra tác động của việc hoãn H0 lên W04 và lên Gate G1 (phần nhiệt).
5. Xác nhận PR này **không** tuyên bố bất kỳ trạng thái an toàn điện nào (không cấp nguồn TEC, không chạm dải dòng lớn).
6. **Firmware W02 mới (lần cập nhật này):** `docs/04 §3.3` yêu cầu Member D review physical wiring/pin/sensing. Đề nghị D kiểm tra: chân GPIO theo `docs/01 §11.7` (GPIO10/21/33/34/35/36/37/5/6), thứ tự reset 1-Wire (≈480/70/410 µs), chọn 12-bit + 750 ms, ngưỡng/đếm debounce MC-38 (`CG_DOOR_DEBOUNCE_MS=50`), và logic `VALID/DEGRADED/INVALID`. **Lưu ý:** firmware **đã** được biên dịch thật trên CI (`esp32s3`, SUCCESS) nhưng **chưa** được nạp/chạy — review này là review mã nguồn + kết quả compile, không phải review kết quả đo.

## 9. Cập nhật lần này: firmware W02 + công cụ kiểm chứng (không cần phần cứng)

Đây là phần `A-W02-03`, `A-W02-04` (phần code) và `A-W02-07` (phần code) mà trước đó **chưa hề có trong repo**. Tất cả đều nằm trong phạm vi Member A.

| Hạng mục | Nơi | Trạng thái thật |
|---|---|---|
| ROM→role cố định, CRC8, không dùng thứ tự discovery | `firmware/main/cg_rom_map.c/.h`, `coldguard_config.h` | Đã implement + kiểm tra tĩnh |
| Shared conversion, `nan` khi lỗi, `VALID/DEGRADED/INVALID` | `firmware/main/cg_ds18b20.c/.h`, `cg_onewire.c/.h` | Đã implement + kiểm tra tĩnh |
| Nhịp ~1 Hz theo deadline, `uptime_ms` thật, `seq` | `firmware/main/app_main.c` | Đã implement + kiểm tra tĩnh |
| Boot identity ≥5 reboot (NVS `boot_count`, `boot_id`, khối `#CG ROM`) | `firmware/main/app_main.c` | Đã implement + công cụ đòi `boot_id` phân biệt & `boot_count` tăng dần; cần 5 lần reset thật |
| MC-38 debounce cấu hình được + cạnh thô `µs` + không đoán polarity | `firmware/main/cg_door.c/.h` | Đã implement + 3 test mô hình + test công cụ |
| IBT-2 OFF trước mọi khởi tạo (docs/01 §11.8) | `firmware/main/cg_safety.c/.h` | Đã implement + kiểm tra tĩnh |
| Parser log + 4 CLI + kiểm tra tĩnh + 1 lệnh gộp | `firmware/tools/` | 57 test + 39 check PASS |

**Giới hạn đã khai báo, không giấu:** (1) firmware nay **đã được biên dịch thật trên CI** (ESP-IDF v6.1, `esp32s3`, SUCCESS — `build-report-w02.md`); máy cục bộ vẫn không có ESP-IDF/Docker nên các test hành vi vẫn là mô hình Python + kiểm tra tĩnh, **chưa** có golden-run trên target; (2) **chưa** nạp và **chưa** chạy lần nào; (3) **không** cài ROM search ⇒ không phát hiện thiết bị 1-Wire lạ (identity vẫn an toàn vì đọc theo ROM cố định, và dòng `#CG ROMS` không in `unknown=` vì không có gì để đo); (4) BME280 **không** thuộc firmware W02. Quy trình bench còn lại nằm ở `bench-procedure-w02.md`.

## 10. Kiểm tra đã chạy

- `py firmware/tools/run_all_checks.py` → **3/3 PASS**: (a) 57 test `unittest` của công cụ, (b) 39 kiểm tra tĩnh firmware, (c) `validate_w02.py`.
- **Build ESP-IDF thật (CI, không cần phần cứng):** GitHub Actions, image `espressif/idf:v6.1`, target `esp32s3` → **SUCCESS**, 0 cảnh báo, `coldguard_firmware.bin` = 0x31360 bytes — run [39117530768](https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117530768) (push) + [39117534103](https://github.com/minhqng/predictive-cold-chain-aiot/actions/runs/39117534103) (pull_request); chi tiết + SHA-256: `build-report-w02.md`. Run đầu (`39117011427`) **FAIL** vì thiếu `esp_driver_gpio` trong requirements — đã sửa tại commit `2a5a0da…` rồi build lại.
- `py validate_w02.py` → **W02 STRUCTURE PASS**: 14 file bắt buộc, 4 bản ghi truy xuất nguồn được xác minh bằng kích thước + SHA-256 (3 ảnh gốc + 1 ghi chú archive), ROM map đúng 3 vai trò + 1 spare (mỗi đầu dò đều `physical_label: PENDING`), `firmware_commit` trỏ tới commit thật **chứa đủ 5 module W02** (`app_main.c`, `cg_onewire.c`, `cg_rom_map.c`, `cg_ds18b20.c`, `cg_door.c`) và ROM bytes trong `coldguard_config.h` khớp từng byte với `sensor-rom-map.yaml` (đọc từ chính commit bằng `git cat-file`/`git show`), `acceptance.md` bao phủ `A-W02-01…A-W02-07`, firmware static checks PASS.
- Kiểm tra tĩnh firmware gồm: ROM trong `coldguard_config.h` khớp **từng byte** với `sensor-rom-map.yaml` và **CRC8 Dallas hợp lệ** cho cả 4 ROM (bắt lỗi chép sai ký tự); hàm đọc từng đầu dò **không** chứa bất kỳ token/call `convert` nào (không chỉ `CONVERT_T`); nhánh polarity `#if`/`#else` bị kiểm tra **ngữ nghĩa** (đảo nhánh vẫn bị từ chối); không có gán vai trò theo chỉ số vòng lặp; `CG_DOOR_POLARITY_CONFIRMED` vẫn `0`; `CG_DOOR_DEBOUNCE_MS`/`CG_SAMPLE_PERIOD_MS` là macro cấu hình; `#CG ROMS` không in `unknown=`; BME280 bị quét trong **mọi** `.c`/`.h` của `firmware/main`; thứ tự gọi an toàn trong `app_main`; `CMakeLists.txt` liệt kê đủ mọi file `.c`.
- Test CLI end-to-end: thiếu `--open-level` ⇒ **mọi dòng dữ liệu CSV** mang `state=UNVERIFIED`, exit 1; `nan` ⇒ ô CSV rỗng (không bao giờ 0.0); < 600 mẫu hợp lệ ⇒ `WINDOW NOT USABLE` + exit 1; < 20 chu kỳ ⇒ exit 1; 5 khối boot dán lặp hoặc `boot_count=0` ⇒ `BOOT_METADATA_INVALID` + exit 1; capture cửa trải nhiều boot ⇒ từ chối cho tới khi có `--boot N`.
- Băm lại archive gốc đối chiếu `source_archive_sha256` (xem `README.md` §Reproduction bước 4).
- `git diff --cached --check` → không có lỗi whitespace/conflict marker.
- **Phản biện độc lập vòng 2** (không do tác giả thực hiện; đọc trực tiếp firmware/công cụ của lần cập nhật này và chạy lại toàn bộ kiểm tra) đã phát hiện **BLOCKER F01–F04** (hồ sơ in output kiểm tra không tái lập được khi `firmware_commit` còn là placeholder) + **MAJOR F05** (đảo dấu chênh lệch cặp) + các MINOR F06–F14/N01–N06 — **tất cả đã được xử lý trong chính PR này** (F13 ghi nhận là giới hạn: test hành vi vẫn là mô hình + kiểm tra tĩnh; lớp **biên dịch thật** bằng ESP-IDF trên CI nay đã bổ sung — xem `firmware-implementation.md` §5.6). Vòng phản biện trước đó trên **lớp bằng chứng 3 ảnh** (đọc 3 ảnh gốc, băm lại archive, tính lại số dẫn xuất) ghi nhận không có BLOCKER/MAJOR trong phạm vi 3 ảnh.
- **Không có test vật lý nào được chạy trong PR này; firmware đã được biên dịch trên CI nhưng chưa nạp và chưa chạy.**

## 11. Ngoài phạm vi

Không cấp nguồn TEC, không chạy tải dòng lớn, không thay đổi BOM freeze, không sửa `docs/00`–`docs/05A`, không đổi lịch canonical, không tạo dữ liệu giả, không merge PR, không bắt đầu W03.
