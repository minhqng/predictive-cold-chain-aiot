# A-W03-06 — Shunt installation: continuity observations and open failure mode

**Trạng thái: `CONTINUITY / FUNCTIONAL OBSERVATIONS — OPERATOR-REPORTED`**
**`SAFETY ACCEPTANCE: PENDING (Member D)`.** Đây **không** phải nghiệm thu an toàn khi chạy
tải lớn, và không phải phép đo điện trở chính xác.

## 1. Phần nhìn thấy từ W01 (ảnh)

| Quan sát | Nguồn | Ý nghĩa |
|---|---|---|
| Nhãn **in** `50A 75mV` trên thân shunt | W01 `photos/18-shunt-marking-actual.jpg` | Đúng định mức đã freeze **theo nhãn in**; không phải chữ khắc trên phần tử điện trở |
| Khắc `FL-2 0.5` trên phần tử | W01 `photos/04-pzem-shunt.jpg` | Marking của phần tử; không chứng minh cấp chính xác hay cấu hình PZEM |
| Cực đấu, dây sense | **Không** đọc được trong ảnh | Không chứng minh Kelvin sense, đầu cốt, lực kẹp |

Không có ảnh mới trong phiên 2026-10-27. Không yêu cầu chụp lại sơ đồ không thay đổi.

## 2. Số đo continuity do người vận hành báo

| Phép đo | Điều kiện | Giá trị báo | Cách đọc đúng |
|---|---|---|---|
| `IBT-2 B−` ↔ `GND logic` | Trạng thái as-built | **≈ 0 Ω** | B− và GND logic **common** trên board; đây là điểm mấu chốt của failure mode |
| `IBT-2 B−` ↔ `PSU−` | Đã tách đường hồi qua shunt | **≈ 453 kΩ** | Đường hồi bị tách; DMM không thấy short, nhưng không chứng minh cách ly an toàn |
| `GND logic ESP32` ↔ `GND IBT-2` | Sau khi nối lại | **Thông mạch** | Xác nhận common ground khi lắp lại |
| `VCC logic IBT-2` ↔ `GND logic` | Nguồn OFF | **≈ 24–25 kΩ** | Không thấy short tĩnh; không phải kiểm tra dưới tải |
| Dòng PZEM | Một lần PWM 10%, thời gian ngắn | **≈ 0.98 A** | Chứng minh đường dòng **có thể** dẫn; **không** phải thử tải lớn/50 A |

Các giá trị là **số đọc DMM do người vận hành báo**, không có log, model đồng hồ, hoặc ảnh
màn hình. `0 Ω` là "dưới ngưỡng continuity" của DMM, không phải 0.000 Ω tuyệt đối.

## 3. Failure mode phải đưa D review (không tự kết luận)

As-built: shunt nằm trên đường hồi giữa `B−` của IBT-2 và `PSU−`; **`B−` lại common với GND
logic** (`≈ 0 Ω`). Vì vậy:

```text
PSU+ ──► IBT-2 B+ ──► TEC ──► IBT-2 B− ──► shunt ──► PSU−
                                      │
                                      └── GND logic (common, ≈0 Ω)
```

Nếu đường shunt hoặc đầu cốt **lỏng/hở**:

1. `B−` không còn nối cứng về `PSU−` qua shunt.
2. Dòng hồi TEC có thể tìm đường về `PSU−` **qua GND logic** (dây GND ESP32/PZEM/USB, đếm
   bề mặt, hoặc đường tín hiệu) — đường không được định mức cho dòng TEC.
3. Hệ quả tiềm năng: quá nhiệt dây/đầu nối, ground shift làm sai phép đo, hỏng ESP32/PZEM,
   hoặc mất tham chiếu đo; mức độ phụ thuộc topology thực tế và dòng tải.
4. Shunt/PZEM có thể đọc sai hoặc mất tham chiếu khi đường hồi hở.

**Đây là giả thuyết failure mode dựa trên continuity đã báo, không phải sự cố đã quan sát.**
Member D phải quyết định:

- topology return/star-ground có chấp nhận được không;
- có cần đảm bảo **không** dùng GND logic làm return path (ví dụ single-point ground, dây
  return riêng, hoặc cách ly cảm biến dòng) hay không;
- tiêu chí kiểm tra đầu cốt/lực kẹp/thermal trước khi chạy tải lớn;
- có cần fuse/khóa cơ học cho đường shunt hay không.

Task này **không** đấu lại dây, **không** đổi shunt, **không** yêu cầu ảnh mới.

## 4. 0.98 A nói gì và không nói gì

- **Nói:** đường dòng đã dẫn được một ít dòng qua shunt; PZEM nhìn thấy dòng khác 0 trong
  một lần chạy PWM 10% ngắn.
- **Không nói:** shunt chịu được 50 A; đầu cốt chắc; nhiệt độ ổn định; PZEM đo đúng dưới
  PWM; hay hệ thống an toàn khi PWM lâu hơn.
- `docs/01 §9.10 / PHY-PZ-002` yêu cầu characterization trước khi dùng power dưới PWM làm
  claim năng lượng. Một quan sát 0.98 A không thay thế characterization.

## 5. Điều chưa kiểm tra

| Hạng mục | Trạng thái |
|---|---|
| Đường dòng đúng nhánh low-side, Kelvin sense | **NOT VERIFIED** — không nhìn thấy trong ảnh |
| Cỡ dây/đầu cốt/lực kẹp | **NOT VERIFIED** |
| Nhiệt shunt/đầu nối khi có tải | **NOT MEASURED** |
| Tải 50 A | **NOT TESTED** |
| Đường return khi shunt hở | **FAILURE MODE OPEN — D REVIEW** |
| Cách ly/ground reference của PZEM | **NOT VERIFIED** |
| Fuse coordination cho nhánh | **W04** |

## 6. Trạng thái acceptance

| Tiêu chí canonical (`docs/05A §12`) | Kết quả |
|---|---|
| Correct current path | **CHƯA CHỨNG MINH** — chỉ có continuity gián tiếp |
| Secure terminals | **CHƯA CHỨNG MINH** — không có pull-test/ảnh cận cảnh |
| No signal-wire in high-current path | **CHƯA CHỨNG MINH** |
| Physical marking 50 A / 75 mV | **PASS theo nhãn in** (W01 photo 18) |
| An toàn khi chạy tải lớn | **PENDING — Member D** |

**Kết luận:** có bằng chứng chức năng/continuity để tiếp tục review, **không** có nghiệm thu
an toàn. Không được dùng các số này để mở khóa W04 high-current.
