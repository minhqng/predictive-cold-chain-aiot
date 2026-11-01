# A-W04-G0 — Power-off electrical verification: evidence reconciliation

**Ngày: 2026-10-29. Người thực hiện: agent (Member A), từ hồ sơ local + số đo do người vận hành báo.**
**Trạng thái: `G0 PARTIAL` — không có sai lệch nào bị phát hiện, nhưng G0 chưa đủ sáu/ sáu mục.**
**Không có phép đo mới nào do agent thực hiện trong tệp này.** Mọi con số vật lý bên dưới là
`USER REPORTED` hoặc lấy từ hồ sơ đã có, trừ khi ghi rõ lớp khác.

## 0. Điều kiện và phạm vi

- Trong suốt task: PSU 12 V OFF, **không** cắm lại cầu chì slot 3 (15 A), **không** cấp TEC,
  **không** PWM, **không** đổi cổng an toàn, **không** nạp lại firmware.
- Không commit/push/merge/rebase; không sửa file của member khác; không sửa thư mục
  `evidence/A/W02`, `W03` hoặc `docs/`.
- Tệp này là **mới** (`evidence/A/W04/` trước đó không tồn tại) nên không ghi đè bằng chứng cũ.
- Đây **không** phải chứng nhận an toàn và **không** mở khóa bất kỳ bài chạy TEC có nguồn nào.

### 0.1 Lớp bằng chứng dùng trong tệp

| Lớp | Nghĩa |
|---|---|
| `VERIFIED_FROM_RAW_EVIDENCE` | Có log/frame/capture gốc trong repo hoặc scratch đã đối chiếu được |
| `OPERATOR_REPORTED` | Người vận hành báo; không có raw capture do agent đọc |
| `INFERRED_ONLY` | Suy ra từ dữ kiện khác, chưa có phép đo trực tiếp cho chính tiêu chí đó |
| `NOT_VERIFIED` | Chưa có bằng chứng nào |
| `BLOCKED_BY_SAFETY_DEPENDENCY` | Không thể đo/đóng cho tới khi một điều kiện an toàn khác được xử lý |

### 0.2 Nguồn đã đọc

| Nguồn | Dùng cho |
|---|---|
| `docs/06-tec-commissioning-safety-and-limits.md` §1.2, §2, §8 (G0), §9, §11 | tiêu chí G0, U1–U12, điều kiện mở output stage |
| `docs/01-physical-measurement-correctness-contract.md` §11.8, §15.3–15.5, §16 | boot contract, nhánh nguồn, hợp đồng cầu chì |
| `evidence/A/as-built-pinmap-2026-10-27.md` §0–§2, §5 | map v2, lớp bằng chứng từng chân, shunt |
| `evidence/A/W03/hardware-2026-10-27/shunt-continuity.md` | các số shunt/GND đã ghi |
| `evidence/A/W03/hardware-2026-10-27/as-built-configuration.md` | as-built, fuse đã ghi, IBT-2 |
| `evidence/A/W03/hardware-2026-10-27/provenance-matrix.md`, `test-131-profile-readback.md`, `README.md` | TEST 131/132B, phân loại claim |
| `evidence/A/W03/hardware-2026-10-27/test-133b-reset-default-off.md` | TEST 133B và giới hạn |
| `evidence/A/W03/hardware-2026-10-27/../hardware-2026-10-20/README.md`, `logic-power-measurement.md` | phiên OFF10, XL4015 |
| `evidence/A/W03/ibt2-pin-map.md`, `hardware-deviation-and-safety.md` | HW-039, SN74HC244, VCC ≈5 V, U4 |
| `A-W01-hardware-audit/evidence/A/W01/{acceptance.md,bom-audit.csv,physical-risk-ledger.md,pin-candidates-v0.md,hardware-audit-w01.md}` | BOM gốc, 5.00 V/4.99 V, pull-down 10 kΩ, R01–R16 |
| `_w04-g1-evidence/SUMMARY.md` + raw G1 logs | xác nhận cầu chì bị tháo có chủ ý, G1 đã chạy |
| `_w04-g2a-evidence/G2A-REPORT.md` | G2-A PARTIAL, T1/T2/T3 |
| `C:\Users\dlbac\Downloads\ColdGuard_W03_Test_Logs_2026-10-20.zip` (giải nén read-only vào `_w04tmp/g0-log-read/`) | phiên 2026-10-20: 11.96 V, 601 mẫu |
| `firmware/main/cg_actuator.c`, `cg_safety.c`, `app_main.c`, `coldguard_config.h` | thứ tự safe-OFF, pull-down nội, map v2 |

---

## A. Tiêu chí G0 thực tế (nguồn: `docs/06 §8`)

Điều kiện: PSU 12 V ngắt; USB ngắt; nhánh TEC không có nguồn; dùng DMM.

| ID | Tiêu chí canonical | Nội dung kiểm | Lớp hiện tại |
|---|---|---|---|
| G0-1 | Nhánh TEC thực sự chết | 0 V tại `IBT-2 B+` **và** `B−` so với `PSU−` | `INFERRED_ONLY` |
| G0-2a | Continuity GPIO5 ↔ header `RPWM` | khớp map v2 | `OPERATOR_REPORTED` |
| G0-2b | Continuity GPIO6 ↔ `R_EN` | khớp map v2 | `OPERATOR_REPORTED` |
| G0-2c | Continuity GPIO10 ↔ `L_EN` | khớp map v2 | `OPERATOR_REPORTED` |
| G0-2d | Continuity GPIO33 ↔ DS18B20 `DATA` | khớp map v2 | `VERIFIED_FROM_RAW_EVIDENCE` (chức năng) |
| G0-2e | Continuity GPIO36/37 ↔ TTL485, **đúng chiều TX/RX** | khớp map v2 | `VERIFIED_FROM_RAW_EVIDENCE` (chức năng) |
| G0-3 | Vị trí shunt trong đường hồi; `B−` ↔ GND logic; ghi **chủ ý hay cầu nối** | không để dòng TEC đi qua GND logic | `OPERATOR_REPORTED`, **intent chưa ghi** |
| G0-4 | Cầu chì nhánh đúng vị trí gần nguồn; ghi nhãn đang lắp (chưa phải chọn cuối) | bộ 10/15/20 A | `OPERATOR_REPORTED`, **chưa có ảnh/nhãn trong repo** |
| G0-5 | Topology input IBT-2: có buffer 5 V không, V_IH bao nhiêu | nếu không xác định được ⇒ ghi `NOT VERIFIED` | buffer `SOURCE VERIFIED`; V_IH `NOT_VERIFIED` |
| G0-6 | Không có dây nào bypass shunt hoặc bypass cầu chì | kiểm bằng mắt/continuity | `NOT_VERIFIED` cho cầu chì; shunt `INFERRED_ONLY` |

**PASS canonical:** mọi continuity khớp map v2; đường hồi và quan hệ GND được ghi rõ; cầu chì
đúng vị trí; nhánh TEC cách ly được; topology input được ghi (kể cả `NOT VERIFIED`).
**FAIL:** bất kỳ sai lệch nào ⇒ không sang G1.

**Ghi chú thứ tự hợp đồng:** `docs/06 §11` đặt G0 trước G1, nhưng G1 đã được chạy trước khi
G0 đóng (phiên 2026-10-29, nhánh TEC chết, cầu chì slot 3 tháo). Đây là **lệch thứ tự có ghi
nhận**, không phải bằng chứng thay thế G0. G1 chỉ chứng minh hành vi TEC-OFF; nó không đo
continuity, không đo topology shunt, không xác nhận cầu chì.

---

## B. Đối chiếu kết quả test lịch sử

### B.1 Test ID được nhắc trong hội thoại trước

| Test | Tìm thấy ở đâu | Nội dung thực nhận được | Lớp | Không được dùng để |
|---|---|---|---|---|
| TEST 119 | **Không tìm thấy** trong repo, `C:\Users\dlbac\Downloads`, các ZIP evidence, hay worktree W01–W03 | — | không có bằng chứng | trích dẫn như đã xảy ra |
| TEST 120 | **Không tìm thấy** (như trên) | — | không có bằng chứng | trích dẫn như đã xảy ra |
| TEST 124 | **Không tìm thấy** | — | không có bằng chứng | trích dẫn như đã xảy ra |
| TEST 125 | **Không tìm thấy** | — | không có bằng chứng | trích dẫn như đã xảy ra |
| TEST 126D / 126E | **Không tìm thấy** | — | không có bằng chứng | trích dẫn như đã xảy ra |
| TEST 129D | Được dẫn trong pinmap §2/as-built; **raw log không có trong repo** | 4 ROM DS18B20 đọc trên bus **GPIO33** | `OPERATOR_REPORTED` (được G1 tái lập gián tiếp) | chứng minh continuity DMM |
| TEST 131 | `evidence/A/W03/hardware-2026-10-27/test-131-profile-readback.md` | frame `01 03 02 00 01 79 84`, CRC `0x8479` kiểm host-side; **không có capture gốc** | `OPERATOR_REPORTED` + CRC toán học | chứng minh readback evidence-grade |
| TEST 132B | `hardware-2026-10-27/raw/test-132b-off-envelope.log` (+ CSV) | 600/600 mẫu, `11.94–11.95 V`, `I=0.00 A`, gate tự chốt **`REVIEW REQUIRED`** | `VERIFIED_FROM_RAW_EVIDENCE` (raw Arduino bench) | chứng minh firmware ESP-IDF, TEC OFF vật lý, hay an toàn tải lớn |
| TEST 133B | `hardware-2026-10-27/test-133b-reset-default-off.md` + sketch | 120/120 mẫu; dòng `RPWM/R_EN/L_EN LOW` là **chuỗi hằng do sketch in**, không đọc lại chân | `OPERATOR_REPORTED` | chứng minh mức chân khi cold boot/reset |

**Kết luận B.1:** TEST 119/120/124/125/126D/126E **không tồn tại ở bất kỳ nơi lưu trữ local
nào** (repo, all worktrees, `_states`, `_repair`, `Downloads`, các ZIP). Đây là **khoảng trống
định vị bằng chứng**, không phải bằng chứng rằng test chưa từng xảy ra. Hồ sơ này **không**
dùng các test đó để đóng bất kỳ mục G0 nào. Nếu người vận hành còn logbook riêng, cung cấp
file gốc; không yêu cầu chạy lại chỉ để tạo file mới.

### B.2 Đối chiếu từng số người vận hành báo với hồ sơ đã có

| Claim mới | Hồ sơ đã có | Kết luận đối chiếu |
|---|---|---|
| GPIO5↔RPWM 0.2 Ω; GPIO6↔R_EN 0.2 Ω; GPIO10↔L_EN 0.2 Ω | W03 `as-built-configuration` ghi map v2 nhưng **chưa từng có phép đo continuity** (`U1`) | **MỚI**. 0.2 Ω với que đo 0.1 Ω ⇒ thực ~0.1 Ω: đủ kết luận **thông mạch**, không phải điện trở chính xác |
| GPIO5↔GPIO6 / 5↔10 / 6↔10 = 59.1 kΩ | chưa có | **MỚI**. Chỉ chứng minh không short cứng ở điện áp DMM; **không** chứng minh cách ly ở điện áp làm việc. Điều kiện đo (USB cắm hay rút) chưa ghi |
| Shunt `50 A / 75 mV`, khắc `FL-2 0.5` | W01 ảnh 18/04; `shunt-continuity.md` §1 | **KHỚP** |
| B− → shunt → PSU− | `shunt-continuity.md` §3; pinmap §5 | **KHỚP** (`USER REPORTED`) |
| B−↔PSU− có shunt = 0.2 Ω; que đo 0.1 Ω | W03 ghi ≈0 Ω | **KHỚP về bản chất**; 0.2 Ω **không** phải điện trở shunt (1.5 mΩ danh nghĩa) |
| B−↔PSU− khi tách đường hồi = 453 kΩ **hoặc OL** (hai cấu hình) | W03 ghi ≈453 kΩ, **không ghi cấu hình** | **MỘT PHẦN**: hai cấu hình chưa được ghi rõ ⇒ chưa dùng làm kết luận cuối |
| IBT-2 B−↔IBT-2 GND ≈0 Ω | W03 ghi B−↔GND logic ≈0 Ω | **KHỚP** nhưng cách diễn giải cũ ("common trên board") là `INFERRED`, xem B.3 |
| Đã tháo dây GND bypass chuyên dụng | chưa có | **MỚI** — thay đổi cấu hình so với W03 |
| IBT-2 GND nối local với LPWM; **không** có dây GND IBT-2→ESP32; ESP32 GND tại điểm A phân áp, tham chiếu XL4015/PSU−; tín hiệu GPIO vẫn nối ESP32↔IBT-2 | W03 ghi "GND logic ESP32 ↔ GND IBT-2 thông mạch" và vẽ B−→GND logic như một nhánh | **MỚI và có mâu thuẫn diễn giải** — xem B.3 |
| Fuse slot 1 5 A XL4015; slot 2 1 A PZEM; slot 3 15 A IBT-2 B+; slot 4 1 A V1 fan | Repo chỉ có: 5 A XL4015, 1 A PZEM (W01 HW-16, W03 as-built). **Không có slot 3/4, không có nhánh quạt** | **MỚI một phần**. Slot 3 = 15 A khớp với G1 summary ("15 A fuse slot 3 removed") nhưng map 4 slot chưa từng được ghi |
| XL4015 no-load 5.01 V; dưới tải logic 4.99 V | W01 ghi XL4015 ≈5.00 V; **4.99 V là của TB4506** | **5.01 V là lần đọc mới** (lệch 0.01 V, trong dung sai đồng hồ). **4.99 V bị gán nhầm nguồn** trong hồ sơ cũ (TB4506, không phải XL4015) |
| PWM 10% ngắn ≈0.98 A | `shunt-continuity.md` §2/§4 | **KHỚP**; scope chỉ là "đường dòng dẫn được", không phải định mức |
| Fan V1 đã test trên nhánh 12 V riêng | docs/01 §15.4 có nhánh quạt; **không có bản ghi test** nào | **MỚI**, chưa đủ cho G2 |

### B.3 Mâu thuẫn diễn giải phải giữ mở: "B− common với GND logic"

Bản ghi W03 `shunt-continuity.md` §2–§3 kết luận `B−` và "GND logic" **common trên board** vì
đo được ≈0 Ω, rồi vẽ:

```text
PSU+ → IBT-2 B+ → TEC → IBT-2 B− → shunt → PSU−
                              └── GND logic (common ≈0 Ω)
```

Báo cáo mới nói: **không có dây GND chuyên dụng** từ IBT-2 về ESP32; GND IBT-2 nối local với
`LPWM`; ESP32 GND nằm ở điểm A của phân áp, tham chiếu XL4015/PSU−. Hai nguồn **không** nhất
quán ở cách đọc, nhưng **có thể dung hòa**:

- "Thông mạch" giữa GND ESP32 và GND IBT-2 có thể đi **qua shunt** (≈0.1 Ω tổng trở dây+shunt),
  và DMM 2 dây đọc thành "0 Ω". Đây là **continuity**, không phải một nhánh GND song song.
- Bằng chứng ủng hộ cách đọc mới: khi **tách đường hồi**, `B−`↔`PSU−` đo được 453 kΩ/OL chứ
  **không** phải ~0 Ω. Nếu có dây GND song song, phép đo đó phải còn ~0 Ω.
- Vì vậy: **không có dấu hiệu bypass cứng qua GND logic**, nhưng **chủ ý (intentional) hay
  cầu nối vẫn chưa được ghi**, đúng như G0-3 yêu cầu. Câu "common trên board" trong W03 là
  `INFERRED`, cần được ghi lại thành "common **qua shunt** (chưa đo 4 dây)".

**Không tự sửa** `shunt-continuity.md` (file của W03). Ghi nhận tại đây để D review.

---

## C. Bằng chứng được chấp nhận vs bị giới hạn

### C.1 Chấp nhận được (trong phạm vi TEC-OFF)

| Bằng chứng | Dùng được cho |
|---|---|
| 0.2 Ω ×3 tuyến GPIO5/6/10 | xác nhận **thông mạch** đúng map v2 ở mức continuity |
| G1 boot log: 4/4 ROM với firmware cấu hình GPIO33 | xác nhận **đường tín hiệu** 1-Wire trên GPIO33 hoạt động (mạnh hơn continuity cho mục đích "đúng chân") |
| Raw Modbus W03 (594/600, 601 mẫu phiên khác) | xác nhận **đường TX và RX** GPIO36/37 hoạt động đúng chiều |
| Ảnh W01 `14-ibt2-actual.jpg` | xác nhận **marking** HW-039, 2×BTS7960B, SN74HC244, nhãn header |
| Shunt `50A 75mV` + `FL-2 0.5` | xác nhận **nhãn** shunt; điện trở danh nghĩa suy ra 1.5 mΩ (tính, không đo) |
| Vị trí shunt trong đường hồi `B−`→`PSU−` | xác nhận **vị trí** theo lời khai (chưa có ảnh cận) |
| TEST 131 frame + CRC | xác nhận profile 50 A **ở mức frame tự nhất quán** |
| Map 4 slot cầu chì | xác nhận **lời khai** về phân nhánh; chưa có ảnh/nhãn |

### C.2 Bị giới hạn — không được nâng cấp ngầm

| Bằng chứng | KHÔNG được dùng để |
|---|---|
| `0.2 Ω` tại shunt | tính/ xác nhận điện trở shunt 1.5 mΩ (que đo 0.1 Ω; DMM 2 dây; 1.5 mΩ dưới độ phân giải) |
| Continuity ≈0 Ω | chứng minh **cách ly** điện; continuity ≠ isolation |
| 453 kΩ khi tách đường hồi | chứng nhận cách ly an toàn; đây chỉ là "không thấy short DC" trong **một** cấu hình chưa ghi rõ |
| 59.1 kΩ giữa các GPIO | chứng minh cách ly ở điện áp làm việc; phép đo có thể bị ảnh hưởng nếu USB đang cấp |
| 0.98 A @ PWM 10% | định mức dòng, duty an toàn, thermal, hay "chạy tải lớn an toàn" |
| 5.01 V / 4.99 V | quan hệ với nhánh 12 V; 4.99 V còn bị gán nhầm giữa XL4015 và TB4506 |
| 11.94–11.95 V (TEST 132B) | điện áp XL4015; đây là **nhánh TEC** đọc bởi PZEM |
| 11.96 V (phiên 2026-10-20) | như trên; phiên khác, không phải 132B |
| G1-02 "OFF" (telemetry) | mức điện áp tại chân; đây là trạng thái phần mềm |
| TEST 133B `RPWM: LOW` | đọc lại chân; là chuỗi hằng do sketch in |
| Fuse 15 A | lựa chọn cuối; docs/01 §16.2 cấm freeze 15 A từ tên TEC |
| Map 4 slot | bằng chứng đã đóng cầu chì đúng vị trí; chưa có ảnh/nhãn |

---

## D. Ma trận G0

Mỗi dòng: (1) tiêu chí, (2) bằng chứng hiện có, (3) điều chứng minh được, (4) điều không
chứng minh, (5) lớp, (6) có cần đo mới **thực sự** không.

### D.1 G0-1 — nhánh TEC chết (0 V tại B+ và B− so với PSU−)

| Trường | Nội dung |
|---|---|
| Bằng chứng | Cầu chì slot 3 **đã tháo có chủ ý** (người vận hành xác nhận trước G1; `_w04-g1-evidence/SUMMARY.md` §B). PSU OFF. Không có phép đo 0 V nào được ghi sau khi tháo |
| Chứng minh | Nhánh `B+` **được thiết kế** để chết vì cầu chì nằm trên đường cấp; `B−` vẫn nối PSU− qua shunt |
| Không chứng minh | Không có dây nào cấp song song vào `B+`; không đo 0 V thực tế; "chết" hiện là suy luận từ trạng thái cầu chì |
| Lớp | `INFERRED_ONLY` |
| Đo mới? | **Có, gián tiếp** — kiểm tra bypass cầu chì ở G0-6 là cách đúng để chứng minh nhánh chết khi PSU OFF (đo 0 V lúc mất nguồn là vô nghĩa vì mọi điểm đều 0 V) |

### D.2 G0-2a/b/c — continuity GPIO5/6/10 ↔ RPWM/R_EN/L_EN

| Trường | Nội dung |
|---|---|
| Bằng chứng | `OPERATOR_REPORTED` ngày 2026-10-29: 0.2 Ω mỗi tuyến; que đo chập 0.1 Ω; chéo 59.1 kΩ |
| Chứng minh | Ba tuyến **thông mạch** đúng map v2; không short cứng giữa ba chân ở điện áp DMM |
| Không chứng minh | Điện trở tiếp xúc thực; dây có đi đúng **một** chân module (không rẽ nhánh); không có short chập chờn; điều kiện đo (USB cắm/rút) chưa ghi |
| Lớp | `OPERATOR_REPORTED` |
| Đo mới? | **Không** — lặp lại chỉ vì kết quả chưa commit là lặp vô ích; 0.2 Ω/0.1 Ω đủ cho tiêu chí continuity. Ghi lại điều kiện đo là đủ |

### D.3 G0-2d — GPIO33 ↔ DS18B20 DATA

| Trường | Nội dung |
|---|---|
| Bằng chứng | Firmware map v2 dùng GPIO33 (`coldguard_config.h:61`); G1 boot log báo **4/4 ROM present** với cấu hình đó; TEST 129D lịch sử |
| Chứng minh | Đường 1-Wire trên GPIO33 **hoạt động chức năng** với cả 4 đầu dò — mạnh hơn continuity cho mục đích "đúng chân" |
| Không chứng minh | Continuity DMM (điện trở); không chứng minh dây không rẽ nhánh; không chứng minh pull-up 4.7 kΩ nằm ở đâu |
| Lớp | `VERIFIED_FROM_RAW_EVIDENCE` (chức năng) |
| Đo mới? | **Không** cho continuity. **Có, ở G1**, cho câu hỏi pull-up trên GPIO10 (xem E4) |

### D.4 G0-2e — GPIO36/37 ↔ TTL485, đúng chiều

| Trường | Nội dung |
|---|---|
| Bằng chứng | Raw Modbus W03: 594/600 CRC-valid (phiên 2026-10-27), 601 mẫu/594 valid (phiên 2026-10-20); TX và RX đều tham gia |
| Chứng minh | Cả **chiều TX** (ESP32→module) và **chiều RX** (module→ESP32) hoạt động qua GPIO36/37 |
| Không chứng minh | Continuity DMM; mức logic RX an toàn (CR-A-W01-01 vẫn PENDING); dây không rẽ nhánh |
| Lớp | `VERIFIED_FROM_RAW_EVIDENCE` (chức năng) |
| Đo mới? | **Không** — giao dịch hai chiều thành công là bằng chứng mạnh hơn continuity cho tiêu chí này |

### D.5 G0-3 — vị trí shunt + quan hệ B−/GND logic + chủ ý

| Trường | Nội dung |
|---|---|
| Bằng chứng | `B−`→shunt→`PSU−` (OPERATOR_REPORTED); `B−`↔IBT-2 GND ≈0 Ω; `B−`↔`PSU−` có shunt 0.2 Ω; tách đường hồi 453 kΩ **hoặc** OL; không có dây GND chuyên dụng; GND IBT-2 nối local `LPWM`; ESP32 GND ở điểm A phân áp |
| Chứng minh | Shunt nằm trong đường hồi; module logic **tham chiếu tại B−** (phía tải của shunt), không phải tại PSU−; **không có dấu hiệu bypass cứng** qua GND logic (nếu có, phép đo tách shunt phải còn ~0 Ω) |
| Không chứng minh | **Chủ ý hay cầu nối** (G0-3 yêu cầu ghi rõ) — chưa ghi; cấu hình nào cho 453 kΩ, cấu hình nào cho OL — chưa ghi; không chứng minh Kelvin sense; không chứng minh không có dòng TEC qua dây logic **trong trạng thái lỗi shunt hở** |
| Lớp | `OPERATOR_REPORTED`; intent `NOT_VERIFIED` |
| Đo mới? | **Measurement mới không giải quyết được**: 1.5 mΩ dưới độ phân giải DMM 2 dây. Cần **ghi lại cấu hình** của hai phép đo 453 kΩ/OL + ảnh cận shunt; nếu muốn chứng minh bằng số phải dùng 4-wire/milliohm — không có thiết bị. Xem E1/E3 |

### D.6 G0-4 — cầu chì nhánh đúng vị trí, ghi nhãn

| Trường | Nội dung |
|---|---|
| Bằng chứng | Slot 3 = 15 A, IBT-2 B+ (OPERATOR_REPORTED, **không có trong repo**); 15 A **đã tháo có chủ ý** cho G1; bộ 10/15/20 A (W01 HW-15) |
| Chứng minh | Có một cầu chì 15 A từng được lắp ở slot 3 trên nhánh TEC; hiện **không** lắp |
| Không chứng minh | Vị trí "gần nguồn" so với đầu `PSU+`; nhãn/holder đúng định mức; có phải fuse chính hãng; 15 A có phù hợp dây/đầu cốt (chưa đo); **không** chứng minh nhánh đang được bảo vệ (đang tháo) |
| Lớp | `OPERATOR_REPORTED`; record `NOT_VERIFIED` |
| Đo mới? | Không phải "đo" mà là **chụp ảnh + ghi nhãn** hộp cầu chì và vị trí tương đối so với `PSU+`. Việc này không cấp nguồn |

### D.7 G0-5 — topology input IBT-2

| Trường | Nội dung |
|---|---|
| Bằng chứng | Ảnh W01: `SN74HC244` (buffer) + 2×BTS7960B, board HW-039 (`SOURCE VERIFIED` marking). VCC logic ≈5 V đo tay 2026-10-20 (`OPERATOR_REPORTED`). V_IH **chưa đo** |
| Chứng minh | Có buffer 5 V giữa header và BTS7960; mức logic vào buffer phải thỏa ngưỡng của họ 74HC ở VCC≈5 V |
| Không chứng minh | 244 có được nuôi từ đúng rail VCC 5 V không (suy từ topology board, chưa trace); V_IH thực tế; biên độ dự trữ; ảnh hưởng offset shunt |
| Lớp | buffer `SOURCE VERIFIED`; V_IH `NOT_VERIFIED` (hợp đồng G0 **cho phép** ghi `NOT VERIFIED`) |
| Đo mới? | Ở G0: **không** (được phép ghi NOT VERIFIED). Ở G1: đo mức chân khi nhánh TEC chết; xem E2 |

### D.8 G0-6 — không bypass shunt/cầu chì

| Trường | Nội dung |
|---|---|
| Bằng chứng | Shunt: 453 kΩ/OL khi tách đường hồi (hai cấu hình chưa ghi) ⇒ **không có bypass cứng** ở cấu hình đã đo. Cầu chì: **không có phép đo nào** `B+`↔`PSU+` khi tháo cầu chì |
| Chứng minh | Shunt có khả năng là đường hồi **duy nhất** ở mức DC (không thấy nhánh song song) |
| Không chứng minh | Cầu chì có bị bypass hay không; bypass AC/transient; cấu hình chưa ghi của phép đo shunt |
| Lớp | shunt `INFERRED_ONLY`; cầu chì `NOT_VERIFIED` |
| Đo mới? | **CÓ — đây là phép đo duy nhất thực sự thiếu và quyết định** (xem H) |

### D.9 Tổng hợp ma trận

| Nhóm | Số mục | Trạng thái |
|---|---:|---|
| `VERIFIED_FROM_RAW_EVIDENCE` | 2 | G0-2d, G0-2e (chức năng, không phải continuity DMM) |
| `OPERATOR_REPORTED` | 4 | G0-2a/b/c, G0-3 (intent chưa ghi), G0-4 |
| `INFERRED_ONLY` | 2 | G0-1, G0-6 (shunt) |
| `NOT_VERIFIED` | 2 | G0-5 V_IH, G0-6 (cầu chì) |
| `BLOCKED_BY_SAFETY_DEPENDENCY` | 0 ở G0; 1 ở G1 (default-OFF điện, E4) | — |

---

## E. Rủi ro an toàn điện còn mở

### E1. Shunt hở / đầu cốt lỏng (TD-W03-02)

- **Cơ chế:** shunt mất tiếp xúc ⇒ `B−` mất đường hồi chuẩn về `PSU−`. Vì `B−` **common với
  GND logic module**, điện thế tham chiếu của 244/GPIO trôi theo `B−`; nguồn 5 V logic mất
  đường hồi; PZEM mất tham chiếu.
- **Không phải** "50 A chạy vào GND logic" trong điều kiện bình thường — vì **không có dây GND
  chuyên dụng**; nhưng **đường hồi thay thế duy nhất khi lỗi** là cặp dây 5 V và ba dây GPIO.
- **Đầu cốt lỏng** là rủi ro nhiệt riêng: điện trở tiếp xúc tăng ⇒ phát nhiệt ở 10 A+.
- **Không được** làm thí nghiệm hở shunt có nguồn. Cần: pull-test/ảnh cận đầu cốt, đo nhiệt
  tiếp điểm ở mức dòng thấp có kiểm soát (giai đoạn sau), và biện pháp chặn dòng sự cố (E3).
- Kết luận: **chưa chấp nhận được cho chạy TEC có nguồn**; **không** chặn G0/G1 TEC-OFF.

### E2. Tương thích 3.3 V ESP32 ↔ SN74HC244 nuôi 5 V (U4)

- Họ 74HC: `V_IH(min) = 0.7 × VCC` ⇒ ở VCC≈5 V là **≈3.5 V**; ESP32-S3 `V_OH` ở rail 3.3 V
  thực tế ≈3.2–3.3 V. **Biên dự trữ đảm bảo là âm** (không đạt datasheet), dù ngưỡng điển
  hình ~2.5 V giải thích vì sao bench vẫn chuyển mạch được (0.98 A).
- Offset shunt làm xấu thêm: module GND ở `B−` cao hơn `PSU−` **15 mV @10 A / 75 mV @50 A**,
  nên mức HIGH tương đối giảm đúng bằng offset.
- Đây là **suy luận từ datasheet họ 74HC + marking**, không phải phép đo V_IH; ghi `NOT_VERIFIED`.
- **Không** phải blocker G0 (hợp đồng cho phép ghi NOT VERIFIED), nhưng là **blocker trước khi
  chạy TEC có nguồn**.
- Hướng xử lý rẻ nhất (không mua thêm): cấp VCC cho 244 bằng **3.3 V** (V_IH ≈2.31 V) — phải
  kiểm tra ngưỡng input của BTS7960 trước; hoặc thay 74HCT244 (ngưỡng TTL) — can thiệp board;
  hoặc level-shift 3.3→5 V. Quyết định thuộc D.

### E3. Đường hồi qua GPIO / nguồn logic

- Bình thường: dòng TEC đi `B−`→shunt→`PSU−`; **không** qua ESP32 GND (không có dây).
- Bất thường (shunt hở): dòng sự cố tìm đường qua cặp 5 V (ngược qua XL4015) và/hoặc ba dây
  GPIO — không được định mức cho dòng lớn.
- Biện pháp không mua thêm: **trở nối tiếp ~330 Ω trên mỗi tuyến GPIO5/6/10** để chặn dòng sự
  cố (vẫn đủ nhanh cho PWM ≤25 kHz với tải ~10 pF), và/hoặc cầu chì nhỏ trên nhánh 5 V cấp
  IBT-2. Cần D duyệt vì là thay đổi đấu dây.
- **Không** tự đề xuất mua module cách ly; chỉ dùng nếu E2+E3 không thể chấp nhận.

### E4. Default-OFF **điện** (U5) — chưa được chứng minh

- Firmware: `cg_actuator_force_off()` là hành động đầu tiên của `app_main`
  (`app_main.c:218`), cấu hình cả 3 chân output + **pull-down nội**, ghi `R_EN=0`,
  `L_EN=0`, rồi `RPWM=0` (`cg_actuator.c:13–32`). Đây là bằng chứng **phần mềm**.
- Bảo đảm **vật lý** khi boot/reset chỉ có thể đến từ pull-down ngoài 10 kΩ trên `R_EN`/`L_EN`
  (W01 `pin-candidates-v0.md`, `OPERATOR_REPORTED`, **chưa đo**). `RPWM` không có pull-down
  ngoài được báo; may mắn là `RPWM` một mình không tạo output khi `R_EN` thấp.
- **Câu hỏi chưa ai trả lời:** GPIO10 từng là **DS18B20 DATA** ở W02 và cần **pull-up 4.7 kΩ**.
  Nếu điện trở pull-up đó **vẫn còn trên GPIO10** (nay là `L_EN`) và pull-down 10 kΩ vẫn ở đó,
  `L_EN` bị phân áp ≈2.2–2.4 V khi bus thả — **có thể đủ gần ngưỡng** của 244. Chưa có ảnh/đo
  xác nhận pull-up đã chuyển sang GPIO33.
- Vì vậy: default-OFF điện = `BLOCKED_BY_SAFETY_DEPENDENCY` cho mọi bài có nguồn; đo được ở
  **G1** khi nhánh TEC chết (DMM/scope tại chân ESP32 qua cold boot/reset). TEST 133B **không**
  đóng mục này (chuỗi hằng).

### E5. Bảo vệ nhánh và định mức dây/đầu cốt (U8, R02, R04, R12, HW-19)

- 15 A là **cầu chì test**, không phải lựa chọn cuối (docs/01 §16.2); hiện **đã tháo**
  ⇒ PHY-FUSE-001 cấm **mọi** bài chạy TEC có nguồn cho tới khi chọn + lắp lại.
- Dây công suất 2.5 mm² **chưa xác minh** (HW-19 `UNVERIFIED`); TB4506 thay TB4504 **chưa duyệt**
  (CR-A-W01-02) và định mức chưa xác minh; cos `FDD2-250` (1.5–2.5 mm²) đang dùng trên dây
  0.75 mm² (R12) — sai dải.
- Không thể chọn cầu chì cuối trước khi có dòng ổn định đo được; nhưng không được chạy dòng
  lớn trước khi có bảo vệ đúng. Đây là vòng lặp cần **characterization có giới hạn** (dòng thấp,
  thời gian ngắn, có giám sát) — thuộc G3, không thuộc G0.

### E6. Vòng GND / USB back-feed (R09) — OPEN

- ESP32 cấp bằng USB (PC ground) và XL4015/PZEM tham chiếu `PSU−`. Khi PSU ON **và** PC cắm,
  có vòng ground; nếu shunt hở, PC ground trở thành đường hồi khả dĩ.
- Trong G0/G1 hiện tại PSU OFF ⇒ chưa hoạt động. Trước bài có nguồn: dùng USB isolator, hoặc
  ngắt PC (cấp ESP32 từ rail 5 V cách ly), hoặc chấp nhận có kiểm soát và ghi rõ. Chưa đo.

### E7. Trạng thái cầu chì: đã lắp trước đây vs **đã tháo có chủ ý** hiện nay

| Thời điểm | Trạng thái slot 3 (15 A) | Ý nghĩa |
|---|---|---|
| Các phiên trước (tới 2026-10-20/27) | **Đã lắp** 15 A | Nhánh TEC có bảo vệ; 0.98 A @10% chạy trong cấu hình này |
| Trước G1 (2026-10-29) | **Đã tháo có chủ ý** | Nhánh chết; G1 an toàn; **không** được coi là "nhánh đang được bảo vệ" |
| Hiện tại (G0) | **Vẫn tháo** | Đúng cho G0; **PHY-FUSE-001** chặn mọi bài có nguồn cho tới khi lắp lại |

Không được ghi "cầu chì đúng vị trí" như một mục PASS hiện tại: đúng vị trí **khi lắp**, nhưng
hiện **không lắp**. Đây là hai sự kiện khác nhau và phải giữ tách biệt.

### E8. Chất lượng provenance của các số mới

- Không có ảnh màn hình DMM, model đồng hồ, hay điều kiện đo (USB cắm/rút; PSU cắm AC hay
  không; shunt còn nối hay tách) cho loạt số 2026-10-29.
- Hai phép đo `453 kΩ` và `OL` **không ghi cấu hình** ⇒ chưa thể dùng để kết luận về đường hồi.
- Đây là lý do G0-3 dừng ở `OPERATOR_REPORTED`/intent `NOT_VERIFIED`, không phải `FAIL`.

---

## F. Có cần thay đổi vật lý không?

| Phạm vi | Kết luận | Cơ sở |
|---|---|---|
| **G0/G1 (nhánh TEC chết)** | **Không** cần thay đổi vật lý | G0 còn thiếu 1 phép đo continuity (H); G1 chỉ cần USB + log; không cần đấu lại dây |
| **Characterization TEC có nguồn (G3+)** | **Có**, cần quyết định/thay đổi trước | E2 (V_IH), E3 (dòng sự cố qua GPIO/5 V), E5 (dây/đầu cốt/cầu chì), E6 (vòng GND) |
| Module cách ly | **Không** yêu cầu tự động | Topology hiện tại có thể chấp nhận nếu E2+E3 được xử lý bằng thay đổi rẻ (VCC 3.3 V + trở nối tiếp). Chỉ cân nhắc cách ly nếu D bác các thay đổi đó |

Các thay đổi tối thiểu đề xuất cho D (không mua thêm linh kiện lớn):

1. **Chuyển VCC logic IBT-2 sang 3.3 V** (sau khi xác nhận ngưỡng input BTS7960) — xóa rủi ro
   V_IH; hoặc level-shift. Không dùng 5 V cho 244 khi drive bằng 3.3 V.
2. **Trở nối tiếp ~330 Ω ×3** trên GPIO5/6/10 — chặn dòng sự cố khi shunt hở.
3. **Pull-test + ảnh cận** đầu cốt shunt/TB4506; thay cos đúng dải (R12); xác minh tiết diện dây.
4. **Chọn cầu chì cuối từ dòng đo được**, lắp lại, chụp ảnh nhãn + vị trí; 15 A chỉ là test fuse.
5. (Tùy chọn) USB isolator hoặc ngắt PC khi chạy có nguồn (R09).

---

## G. Kết luận G0

**`G0 PARTIAL`.**

| Điều kiện PASS canonical | Kết quả |
|---|---|
| Mọi continuity khớp map v2 | **MỘT PHẦN** — 3 tuyến IBT-2 operator-reported; 33/36/37 chứng minh chức năng (không DMM); không có sai lệch |
| Đường hồi và quan hệ GND được ghi rõ | **CHƯA** — vị trí có, nhưng "chủ ý hay cầu nối" và cấu hình 453 kΩ/OL chưa ghi |
| Cầu chì đúng vị trí | **CHƯA** — map 4 slot operator-reported, không có ảnh/nhãn; hiện đã tháo có chủ ý |
| Nhánh TEC cách ly được | **SUY LUẬN** — cầu chì tháo; chưa kiểm bypass |
| Topology input được ghi (kể cả NOT VERIFIED) | **ĐẠT** — buffer SOURCE VERIFIED; V_IH `NOT_VERIFIED` |

- **Không có `FAIL`:** không phát hiện sai lệch continuity, không có short, không có dấu hiệu
  bypass shunt cứng.
- **Không `PASS`:** thiếu G0-1/G0-3-intent/G0-4-record/G0-6-fuse; theo hợp đồng, G0 PASS cần
  **tất cả** sáu mục.
- **Không `BLOCKED`:** các mục thiếu đều đóng được bằng một phép đo power-off + ghi hồ sơ;
  không có phụ thuộc an toàn nào ngăn việc đo.
- **Hệ quả:** G0 **chưa** cho phép chuyển sang bất kỳ bài có nguồn nào. G1 đã chạy trước đó
  (lệch thứ tự đã ghi) chỉ có giá trị cho TEC-OFF.

---

## H. Hành động tiếp theo — DUY NHẤT

**Một phép đo power-off: kiểm tra bypass cầu chì nhánh TEC (`B+` ↔ `PSU+` khi slot 3 trống).**

Điều kiện:

1. PSU 12 V **OFF** và **rút AC**; USB **rút**; cầu chì slot 3 **vẫn để trống** (không cắm lại);
   shunt/GND/TEC giữ nguyên; không chạm dây khi có nguồn.
2. Đồng hồ số ở thang thấp nhất (200 Ω hoặc thang thông mạch); chập hai que, ghi `R_leads`.
3. Đo giữa **cực `PSU+` của nguồn** và **đầu `IBT-2 B+`** (đầu vào phía tải của holder cầu chì).
4. Kỳ vọng: **hở (`OL` / ≫1 MΩ)** vì cầu chì đã tháo.
5. Nếu đọc được giá trị hữu hạn (≲10 kΩ) ⇒ **G0 FAIL**: có đường bypass cầu chì. Dừng, chụp ảnh,
   ghi lại, không tiếp tục bất kỳ bước nào.
6. Ghi: giá trị, `R_leads`, model đồng hồ, ngày, người đo, ảnh hộp cầu chì (slot 3 trống + nhãn).

**Vì sao chọn đúng phép đo này:**

- Đây là mục G0 **duy nhất chưa có bất kỳ bằng chứng nào** (G0-6 cầu chì) và nó cũng là cách
  đúng để chứng minh G0-1 (nhánh chết) khi PSU OFF — đo 0 V lúc mất nguồn không chứng minh gì.
- Kết quả **nhị phân**: hở = không bypass; thông = FAIL rõ ràng. Không phụ thuộc độ phân giải
  miliohm như câu hỏi shunt.
- Thực hiện được **ngay** với cầu chì đang tháo có chủ ý; **không** cần cắm lại, **không** cấp
  nguồn, **không** tháo shunt.
- Trực tiếp bảo vệ **PHY-FUSE-001**: không bài có nguồn nào được phép bỏ qua cầu chì nhánh.

**Không yêu cầu** đo lại continuity GPIO (đã đủ), không yêu cầu đo lại shunt bằng DMM 2 dây
(không thể phân giải 1.5 mΩ), không yêu cầu chạy lại TEST 119/120/124/125/126.

Sau phép đo này: **dừng, chờ người vận hành nhập kết quả.** Không có hoạt động nào khác được
thực hiện trong task này.

---

## Phụ lục — những gì task này KHÔNG làm

- Không cấp PSU, không cắm lại cầu chì, không cấp TEC, không PWM, không đổi GPIO/cổng an toàn.
- Không nạp lại firmware; không mở cổng serial.
- Không sửa `docs/`, `evidence/A/W02`, `W03`, `as-built-pinmap-2026-10-27.md`, hay file của
  thành viên khác.
- Không commit/push/merge/rebase; không xóa/ghi đè bằng chứng cũ.
- Không tạo số đo, phê duyệt, định mức cầu chì hay giới hạn nhiệt.
