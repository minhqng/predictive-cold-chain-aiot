# A-W01-04 — Physical risk ledger (candidate, cần D review)

**Scope:** hệ PSU 12 V/33 A, nguồn AC/DC vỏ hở có điện áp lưới, logic ESP32 3.3 V, PZEM/shunt, IBT-2/TEC, mặt nóng V1 và chamber. Đây là **risk register**, không phải chứng nhận an toàn.

Nguồn bằng chứng: kết quả người dùng báo trên bench + ảnh trong `photo-inventory.csv`. Không có kết quả nào được agent tái lập độc lập.

| ID | Risk | Impact | Observation/current state | Mitigation and required evidence | Owner | Status |
|---|---|---|---|---|---|---|
| R01 | Đảo cực DC | High | PZEM đọc 11.95 V; chưa có ảnh từng dây | Cách ly nguồn; đo cực tính tại đầu nối trước khi cấp điện; dán nhãn dây | A | OPEN |
| R02 | Ngắn mạch nguồn 33 A / dây nhỏ hơn định mức | Critical | Nguồn 12 V dòng lớn; dây phụ nhỏ đang dùng trên bench | Đặt fuse từng nhánh tại gốc theo định mức dây và đầu nối; cos đúng chuẩn; không để sợi dây hở | A + D | OPEN |
| R03 | Đầu cọc 220 VAC lộ / tiếp địa | Critical | Chưa ai có chuyên môn kiểm tra cách ly AC, tiếp địa, nắp che; **ảnh 16 cho thấy cọc AC vào (L, N, nối đất) lộ ra ở đáy vỏ nguồn** | Cần người có chuyên môn rà soát; vỏ bảo vệ, chống kéo căng, tiếp địa, điểm ngắt an toàn; cấm chạm khi đang cấp | A + D | OPEN |
| R04 | Sai định mức / sai vị trí fuse | High | 5 A cho XL4015, 1 A cho PZEM; 10/15/20 A chưa được duyệt cho dây nhỏ | Ghi lại sơ đồ phân phối và vị trí fuse theo từng nhánh; xác nhận fuse/holder chính hãng; chọn fuse TEC sau khi đo dòng | A + D | OPEN |
| R05 | Shunt đấu sai, nối tắt +12 V/0 V | Critical | Shunt chưa được thử có tải; ảnh 18 đọc được nhãn **in** `50A 75mV`, ảnh 04 khắc `FL-2 0.5` | Shunt mắc **nối tiếp ở nhánh low-side** của đúng một nhánh làm lạnh; dây sense Kelvin riêng; đúng profile 50 A; review ảnh trước khi cấp điện | A + D | NOT_TESTED |
| R06 | IBT-2 bật khi boot/reset | Critical | Đã test logic và pull-down 10 kΩ, chưa log trạng thái cold-boot/reset | Phần cứng mặc định OFF; log 5 cold boot + 5 reset + watchdog với tải an toàn trước khi cấp TEC | A + D | OPEN |
| R07 | Quạt/tản nhiệt thiếu hoặc dừng khi TEC ON | Critical | Quạt CJY 12 V 0.20 A chưa chạy trong cụm V1 hoàn chỉnh; ảnh 17 xác nhận quạt nằm trong hộp kit V1 | Interlock quạt trước TEC; kiểm tra tiếp xúc mặt nóng, keo tản nhiệt và lực ép; giám sát nhiệt và ngắt ngay | A + D | NOT_TESTED |
| R08 | Ẩm/ngưng tụ vào khối điện tử | High | Chưa lắp xong chamber | Điện tử nằm ngoài vùng ẩm; chống kéo căng và tạo vòng nhỏ giọt cho cáp; kiểm tra cách điện sau mỗi lần chạy | A | OPEN |
| R09 | USB back-feed / vòng GND | High | ESP32 USB và GND logic PSU cùng tồn tại trên bench; PZEM từng dùng micro-USB | Kiểm tra không có đường cấp ngược về PC; GND logic dùng chung đúng cách; không ghép nguồn tùy tiện | A + D | OPEN |
| R10 | Sai miền nguồn/mức logic RS-485 | High | TTL485 TXD idle 5 V; phân áp tạm 10k/10k/10k cho khoảng 3.314 V **đo được** (tính toán ≈ 3.33 V) | Không đi 5 V trực tiếp vào GPIO; phê duyệt transceiver 3.3 V hoặc level-shift chính thức; xác minh part number và ngưỡng vào | A + D | OPEN / HARDWARE DRIFT |
| R11 | Thay thế cầu đấu / đầu nối lỏng | High | TB4506 lắp thay TB4504 45 A 4P; định mức chưa xác minh | Xác minh định mức dòng, khoảng cách cách điện, lực kẹp và cỡ dây; đưa vào hardware change review | A + D | OPEN / HARDWARE DRIFT |
| R12 | Cos sai dải dây | High | Cos xanh FDD2-250 (1.5–2.5 mm²) dùng trên dây mềm 0.75 mm² | Thay bằng cos/ferrule đúng dải dây; dùng kìm bấm đúng chuẩn; pull-test và chống kéo căng | A | OPEN |
| R13 | Suy dòng TEC từ tên linh kiện | High | Ảnh 15 đọc rõ marking `TEC1-12715 SR`; seller/SKU vẫn chưa xác minh | Không mặc định dòng 15 A; đo bằng PZEM/shunt có tham chiếu; theo dõi nhiệt IBT-2 và dòng nguồn | A + D | NOT_TESTED |
| R14 | Xung đột GPIO/PSRAM trên board dual ESP | Medium | GPIO10/34/36/37 chạy được trên tuyến đã thử; các chân khác chưa biết | Đối chiếu sơ đồ nhà bán và routing ESP32-S3R2; tránh xung đột flash/bootstrapping | A | OPEN |
| R15 | Phân bổ connector PCT-218 | Medium | Ảnh 22/23/24 xác nhận **một chiếc** PCT-218 8 cổng (khắc nổi `PCT-218`); tổng **4 chiếc** vẫn là người dùng xác nhận; chưa đưa vào lắp | Chụp đủ 4 chiếc trong một khung; chốt phân bổ dùng chính/dự phòng; nếu phải đấu tạm thì ghi rõ và không dùng jumper/Dupont cho đường dòng lớn | A + leader | OPEN |
| R16 | Kết quả test bị gán ý nghĩa mạnh hơn bằng chứng | High | PZEM chỉ PASS phần điện áp, chưa PASS dòng/công suất; TEC chưa chạy | Ghi rõ scope PASS cho từng test; `hardware_config_id` và log bằng chứng bất biến | A + reviewer | OPEN |

## Điều kiện dừng bắt buộc

- Cực tính không chắc, đầu nối ấm/nóng, tia lửa, mùi lạ, PSU hành xử bất thường, fuse nổ hoặc dây lỏng → **ngắt điện lưới** và điều tra.
- Không được bắc cầu fuse, không nối tắt PSU để mô phỏng lỗi, không cấp TEC khi quạt/tản nhiệt chưa hoạt động, không dùng jumper mảnh làm dây công suất.
- **W01 không phê duyệt bất kỳ lần chạy tải dòng lớn nào.**
