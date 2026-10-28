# A-W03-04 — 50 A profile readback (TEST 131)

**Trạng thái: `OPERATOR-REPORTED — RAW CAPTURE NOT AVAILABLE; CRC RECOMPUTATION VERIFIED`**
**Giới hạn: `RAW CAPTURE FILE NOT AVAILABLE`.** Không có file log gốc cho TEST 131 trong
môi trường này; chỉ có frame hex do người vận hành báo và mô tả chuỗi phản hồi.

## 1. Bằng chứng nhận được

Người vận hành báo TEST 131 trả về:

```text
01 03 02 00 01 79 84
```

| Byte | Ý nghĩa | Giá trị |
|---|---|---|
| `01` | Slave address | `0x01` |
| `03` | Function code | Read Holding Register (`FC 0x03`) |
| `02` | Byte count | 2 byte dữ liệu |
| `00 01` | Register value | `0x0001` |
| `79 84` | CRC16/MODBUS | low byte `0x79`, high byte `0x84` |

## 2. Kiểm tra host-side (độc lập với niềm tin vào summary)

CRC16/MODBUS (init `0xFFFF`, polynomial `0xA001`) tính trên 5 byte đầu:

```text
input  = 01 03 02 00 01
crc    = 0x8479
on-wire= 79 84      (low byte first)
```

→ Frame **tự nhất quán**. `0x0001` = profile **50 A** theo bảng register của `docs/01 §9.3`
(`0x0000 = 100 A`, `0x0001 = 50 A`, `0x0002 = 200 A`, `0x0003 = 300 A`).

Script `verify_test132b.py` trong thư mục này kiểm tra lại phép CRC trên và in
`[PASS] TEST 131 frame ... -> CRC16/MODBUS 0x8479`.

## 3. Chuỗi phản hồi — giữ cả phần chưa hoàn hảo

Người vận hành ghi nhận:

1. **Hai phản hồi đầu không hợp lệ** (không có raw byte được lưu).
2. Sau đó **ba phản hồi hợp lệ liên tiếp**; một trong ba là frame ở §1.

Hai phản hồi lỗi **không bị xóa** khỏi câu chuyện provenance. Hồ sơ này không tuyên bố
"giao tiếp đúng ngay từ đầu", và không suy đoán nguyên nhân hai phản hồi lỗi (không có byte
để phân tích CRC). Đây là khác biệt giữa "ba phản hồi hợp lệ liên tiếp" và "toàn bộ test
luôn hợp lệ".

## 4. Điều KHÔNG được làm

- **Không** ghi register để đổi profile. W03 là read-only: chỉ FC `0x03`/`0x04`.
- **Không** dùng nhãn shunt `50A 75mV` để suy ra register. Nhãn shunt là thuộc tính vật lý
  của shunt, không phải bằng chứng cấu hình PZEM.
- **Không** đồng nhất TEST 131 với lần FC06 `SET50` trong archive 2026-10-20. Lần FC06 đó
  nằm ngoài hợp đồng read-only W03, là `ARCHIVE ONLY — DO NOT FLASH OR EXECUTE`, và vẫn là
  sai lệch quy trình cần được mô tả/xử lý (`TD-W03-07`).
- **Không** yêu cầu người vận hành chạy lại test chỉ để tạo file log mới. Nếu cần
  evidence-grade capture, yêu cầu **file capture gốc** của lần chạy đã có; nếu file không
  còn, ghi nhận khoảng trống thay vì tái tạo.

## 5. Trạng thái acceptance

| Tiêu chí | Kết quả |
|---|---|
| Frame hex hợp lệ về cấu trúc | **PASS** — 7 byte, FC03, byte count 2 |
| CRC16 host-side | **PASS** — `0x8479` → `79 84` |
| Giá trị register | **`0x0001` = 50 A** theo manual |
| Chuỗi 3 phản hồi hợp lệ | **OPERATOR-REPORTED** — không có file log |
| Capture file gốc | **NOT AVAILABLE** |
| Đọc bằng firmware ESP-IDF W03 (`#CG PZEM_RANGE`) | **NOT RUN** |

**Kết luận có phạm vi:** profile 50 A đã được xác nhận bằng một frame Modbus tự nhất quán
và CRC kiểm lại độc lập, nhưng **chưa** có capture file để tái lập. Đây là bằng chứng
operator-reported đã qua kiểm tra toán học, không phải evidence-grade raw capture.
