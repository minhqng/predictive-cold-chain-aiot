# Phân tích tiền-closure A-W08-03 + A-W16-01 (2026-11-10)

Phạm vi: **chỉ** A-W08-03 (Hot-side sustainability) và A-W16-01 (Re-run short
characterization). Không tái thẩm định các mục khác; không đổi trạng thái
nghiệm thu nào của thành viên khác. Tài liệu này là bằng chứng host offline,
**không** tuyên bố PASS thân cứng nào cả (cross-check với W16:
`no physical freeze may be declared from host evidence`).

## 1. Kết luận chính

- **A-W08-02 → giữ nguyên NOT_RUN.** Dữ liệu H8-C 600 s là dữ liệu bench thật
  nhưng **không** thỏa criterion trên firmware yêu cầu (stage-enabled W06);
  evaluator chính thức không có đường replay; PASS offline bị cấm bởi
  governance hiện hành (`acceptance-decisions-20261108.md`; một offline PASS
  đã từng bị revert trong phiên 2026-11-08 — giữ quyết định đó).
- **A-W16-01 → giữ nguyên NOT_RUN.** Ba capture (OFF 120 s, ON 120 s, S2 180 s)
  đều yêu cầu thiết bị trực tiếp trên image stage-enabled; chuỗi bị khóa bởi
  prerequisite A-W08-03.
- Khả thi offline còn lại: **không có gì thêm** ngoài các verification dưới đây;
  A-W09-04 và A-W16-02 vẫn là tính thuần **sau** phiên (đã có sẵn tooling/protocol;
  envelope-input của A-W09-04 đã được giữ lại làm measurement-only record, bản
  thân A-W09-04 vẫn NOT_RUN chờ A-W08-03).

## 2. Bằng chứng hiện hữu đã kiểm chứng (OBSERVED, phiên này)

Nguồn canonical: `evidence/A/SOURCES/20261107/datasets/` (bản local đã có
`measurement_summary.csv`/`manifest.json` khớp store).

| Capture | Raw SHA-256 (12) | Cửa sổ (state) | Thông số chính |
|---|---|---|---|
| H8-C 600 s (`raw/h8-c-600s-tec-cooling/monitor-final__telemetry_raw.log`) | `b570057efdc5` | OFF 226 s → **COOLING 600.0 s (600 khung, 1 Hz)** → COOLDOWN 5 s → OFF 126 s | boot `56044b74`; grammar **H8S**, firmware `h8-bench`; T2 max 39.938 / mean 35.4198 °C; I max 9.99 / mean 4.5378 A; P max 117.4 / mean 53.4884 W; chamber_drop 8.7083 °C; **fault_bits 0/957** (lý do `STAGE_DEADLINE` chỉ là lifecycle của stage, không phải fault latch) |
| H8-E 1800 s (`raw/h8-e-1800s-100pct/monitor__telemetry_raw.log`) | `b93f74cc51ed` | OFF 23 s → ARMED 10 s → **COOLING 1800.0 s (1800 khung, 1 Hz)** → COOLDOWN 5 s → **OFF 1077 s** | boot `c4ff0ab3`; grammar H8S; T2 max 37.688 / mean 34.6465 °C; I max 8.75 A; fault_bits 0/2915 |

Đối chiếu kiểm chứng này **khớp từng con số** với các record
`measurements/A-W08-03-*` (OFFLINE_EVALUATION_ONLY_NO_VERDICT) đã lưu trong
store từ 2026-11-08/09. Chất lượng: 957/957 và 2915/2915 dòng hợp lệ, cadence
1 Hz liên tục trong cửa sổ ON.

**Sửa một chi tiết của plan 2026-11-08 (`physical-session-w08-w16-plan.md`, tài liệu phiên cục bộ, không commit):**
bản export chuẩn hóa của H8-C có `voltage_status/current_status = OK`; các
trường thực sự rỗng 957/957 là `physical_output`, `output_stage`,
`cooling_applied` và `slot_t_hot_side_*`. Kết luận chặn **không đổi**: grammar
H8S không có trạng thái applied/output_stage chuẩn W06, không có actuation trace
(SUPERVISE/ARM/START/STOP app), image không phải stage-enabled W06.

Cơ sở W16-02 (so sánh sau phiên, các tham chiếu baseline đã PASS trong store):
A-W04-05: `current_mean_a` 4.424 A, `chamber_drop_c` 0.6188 °C,
`thermal_delay_s` 36.02 s (dịch chuyển cho phép do Evaluator A-W16-02: ±2.0 A,
±2.0 °C, ±30 s).

## 3. Ma trận phân loại theo subcriterion

### A-W08-03 — criterion: "valid run / hot side ≤55 °C / no fault / response stable" (handler `run_series` COOLING_STEP, 600 s, ≥180 khung, `requires_actuation`)

| Subcriterion | Phân loại | Căn cứ |
|---|---|---|
| prereq A-W04-05, A-W08-01 PASS | SATISFIED_BY_EXISTING_EVIDENCE | hai kết quả PASS trong store; raw này không đổi |
| Cửa sổ 600 s @1 Hz, ≥180 khung, coverage — về dữ liệu | SATISFIED_BY_EXISTING_EVIDENCE (bench) | H8-C có đúng 600.0 s/600 khung trong state COOLING |
| Valid run canonical: firmware stage-enabled W06, output_stage ENABLED, ARM/START/STOP ack, applied_state ON, V/I/P status qualified | PHYSICAL_TEST_REQUIRED | image hiện tại là h8-bench (H8S); `physical_output/output_stage/cooling_applied` rỗng 957/957; evaluator cấu hình headless **ch chắn `NO_DEVICE_CONNECTED`**, thiết bị H8 sẽ **chặn `H8_BENCH_IMAGE`**; không có đường replay |
| Hot side ≤ 55 °C | OFFLINE_ANALYSIS_NEEDED → đã xong; phổ biến đồng thời PHYSICAL_TEST_REQUIRED + EXTERNAL_DEPENDENCY | bench quan sát max 39.938 °C (thỏa bound); nhưng **bản thân 55 °C còn PROVISIONAL** chờ Member D freeze (`cg_tec_limits.h`, `HOT_SIDE_LIMIT_NOT_ESTABLISHED`) |
| No fault | SATISFIED_BY_EXISTING_EVIDENCE (bench) — cần tái quan sát trên run canonical | fault_bits 0/957; run mới vẫn bắt buộc |
| "Response stable" + quan sát nhiệt terminal/IBT-2/cable (bullet 4) | PHYSICAL_TEST_REQUIRED | chưa có measurement nhiệt nào của terminal/IBT-2 trong H8-C/H8-E |
| Cầu chì slot-3 (giá trị an toàn) | PHYSICAL_TEST_REQUIRED | **fuse 15 A đang tháo khỏi slot 3** (A-W08-02 note); cần cold inspection + ampacity basis trước khi lắp lại |
| 6 TEC operating limits + hot-side stop số | EXTERNAL_DEPENDENCY | UNRESOLVED, chờ Member D freeze |

### A-W16-01 — criterion: "OFF envelope / ON response / S2 response" (handler `recharacterization`)

| Subcriterion | Phân loại | Căn cứ |
|---|---|---|
| prereq A-W10-03 PASS | SATISFIED_BY_EXISTING_EVIDENCE | store PASS (4 S2 runs 2026-11-07) |
| prereq A-W08-03 PASS | PHYSICAL_TEST_REQUIRED (kế thừa) | evaluator cấu hình scratch xác nhận **`PREREQUISITE_INCOMPLETE A-W08-03`** |
| OFF envelope 120 s (default-off + off-current) | PHYSICAL_TEST_REQUIRED | H8-C pre-OFF 226 s là bench grammar không có trạng thái W06; W03-05 là off-envelope W03-era, không phải tái đặc trưng W16 |
| ON step 120 s (capture 125 s, duty trong limits đã resolve, actuation trace) | PHYSICAL_TEST_REQUIRED | cần ARM/START/STOP trực tiếp qua app trên stage-enabled W06 |
| S2 disturbance 180 s (MC-38 là timing authority) | PHYSICAL_TEST_REQUIRED | S2 2026-11-07 là đối tượng phân tích, không phải tái chạy "no anomaly since W08" |
| Precheck: fuse/fan unchanged, operator present, no anomaly since W08 | PHYSICAL_TEST_REQUIRED | xác nhận tại-place trước khi chạy |

**Không còn OFFLINE_ANALYSIS_NEEDED nào trước phiên** — toàn bộ phần còn lại là
physical + EXTERNAL (D). Các bước offline (A-W09-04, A-W16-02) chỉ kickoff sau
khi A-W08-03 và A-W16-01 có PASS.

## 4. ONE phiên vật lý tối thiểu (khớp plan `physical-session-w08-w16-plan.md` — tài liệu phiên cục bộ, không commit; đã verify + bổ sung)

Nguyên tắc: một phiên giám sát duy nhất sau khi **4 cổng an toàn đóng**; thứ tự
capture bắt buộc A-W08-03 (600 s) → A-W16-01 (OFF 120 s + ON 120 s + S2 180 s);
**không lặp** H8-E 1800 s — bằng chứng 1800 s + recovery OFF 1077 s đã tồn tại
và criterion handler chỉ yêu cầu 600 s (đề xuất Gate-A về ≥1800 s là tùy chọn
của D, không phải ngưỡng handler).

**Cổng an toàn (xin phép riêng từng cổng; không tự energize, không tự flash):**
1. Gate A — Member D freeze 6 TEC limits + hot-side stop (số, không còn PROVISIONAL).
2. Cold inspection + chọn rating cầu chì phòng thủ (ampacity: dây, insulation
   class, run length, bundling); lắp lại fuse slot 3.
3. Rebuild + flash image W06 stage-enabled (chỉ sau Gate A) + boot proof:
   `output_stage=ENABLED`, firmware canonical, 6 TEC_LIMIT RESOLVED.
4. Operator ARM/START consent cho phiên này (ủy quyền W21 không bao gồm TEC).

**Thiết bị/phần cứng chính xác:** ESP32-S3R2 (COM4, console đọc+ghi lệnh),
nhánh TEC đã có cầu chì slot 3 + IBT-2 + TEC1-12715 trong assembly V1, quạt V1
hot-side chạy, probe T2 (hot-side) + T1/T3 + BME280 + MC-38 + PZEM-017 với
shunt 50 A/75 mV; PSU 12 V/33 A; đồng hồ đo (multimeter) cho pre/post check;
nhiết kế (touch-free) để quan sát terminal/IBT-2 trong Capture 1 (bullet 4).

**Firmware:** image `stage-enabled W06` — build trước khi flash; app sẽ khước từ
mọi kết quả trên H8 image (không báo canonical PASS).

**Thời lượng ước tính (giám sát):** chuẩn bị cold + lắp cầu chì ~15′; build+flash
+ boot proof ~20′; pre-baseline + Capture 1 (600 s + START/STOP + quan sát nhiệt)
~15′; Capture 2 (120 s OFF + 125 s ON + 180 s S2 + door protocol) ~12′; safe
shutdown + debug log ~5′ → **tổng ≈ 65–75 phút ngồi tại PSU** (không tính thời
chờ Gate A của D và thời gian build lớn hơn nếu cần).

## 5. Thay đổi trạng thái store trong phiên này

- **Không** ghi bất kỳ result mới cho A-W08-03/A-W16-01 (giữ NOT_RUN theo
  governance). Chỉ thêm record `OFFLINE_EVALUATION_ONLY_NO_VERDICT` gộp cho
  A-W08-03 (verification khớp) và record phân loại pre-session cho A-W16-01.
- Bằng chứng của các thành viên khác và mọi PASS lịch sử được bảo toàn.

## 6. Người/khâu phụ trách tiếp theo

- **Member D:** freeze hot-side limit + 6 operating limits (khối lớn duy nhất
  của EXTERNAL_DEPENDENCY).
- **Operator/owner:** cold inspection cầu chì; cho phép rebuild + flash; ARM/START.
- Sau phiên: A-W09-04 + A-W16-02 chạy offline (đã có evaluator; không cần thêm
  phép đo); A-W16-03 ký cùng B.
