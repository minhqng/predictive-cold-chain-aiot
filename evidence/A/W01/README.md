# ColdGuard — Member A — W01 physical audit

**Snapshot:** 2026-10-18 · **Role:** Member A (Embedded & Thermal) · **Status:** `DRAFT / REVIEW REQUIRED` · **hardware_config_id:** `NOT_ASSIGNED` · **Firmware commit:** `NOT_RECORDED` · **Operator:** Member A (không ghi tên cá nhân trong repo)

## Scope and authority

- Thứ tự thẩm quyền: `docs/00` → `docs/01` → `docs/02` → `docs/03` → `docs/04` → `docs/05A`, cụ thể `docs/04 §16` và `docs/05A §2, §10`.
- Dùng **BOM 24 mục đã freeze**; **không** tự ý viết lại Docs 00–01.
- Bộ chứng cứ này tổng hợp **kết quả do người dùng báo và ảnh người dùng tải lên**, không phải một cuộc kiểm kê vật lý đầy đủ do agent chứng kiến. Mọi nhãn `reported` nghĩa là *được báo cáo*, không phải *đã được chứng nhận độc lập*.
- **Bộ ảnh hiện hành là gói 25 ảnh** (`ColdGuard_W01_All_25_Real_Photos_OpenCode.zip`, 2026-10-18, 4.126.980 bytes, SHA-256 `9EB77E77CC1C1436B927E4307B0B14738C4A8EE2F4D7959D0C66A144212986CB`); 10 ảnh trước đó là tập con byte-identical của gói này — claim này đã được xác minh cục bộ bằng so khớp SHA-256 từng file khi hợp nhất, nhưng **không thể** tái kiểm chỉ từ nội dung repo (repo không chứa ZIP gốc). Ảnh chỉ chứng minh **sự hiện diện** của linh kiện; ảnh **không** chứng minh số lượng, định mức hay chất lượng lắp đặt, trừ khi `photo-inventory.csv` ghi rõ là có.
- Toàn bộ tài liệu ở đây là **tài liệu**, **không phải** bằng chứng rằng rà soát an toàn vật lý đã hoàn tất. **Không** cấp nguồn 220 VAC hoặc TEC dòng lớn chỉ dựa trên audit này.

## Provenance vocabulary

Cột `inspection_status` trong `bom-audit.csv` chỉ dùng các giá trị sau:

| Nhãn | Nghĩa |
|---|---|
| `PRESENT_PHOTOGRAPHED` | Có ít nhất một ảnh trong bộ chứng cứ cho thấy linh kiện |
| `PRESENT_PHOTOGRAPHED_PARTIAL` | Có ảnh cho thấy linh kiện nhưng ảnh **không** chứng minh đủ thuộc tính đã freeze (số lượng, định mức hoặc model) |
| `PRESENT_PHOTOGRAPHED_TEST_REPORTED` | Có ảnh **và** có kết quả bench do người dùng báo |
| `PRESENT_REPORTED` | Người dùng báo có linh kiện; **không** có ảnh nào lấy linh kiện đó **làm đối tượng chứng cứ**. Linh kiện có thể **xuất hiện phụ** trong một ảnh toàn cảnh — khi đó `photo_ref` vẫn được ghi để truy vết, nhưng ảnh đó **không** chứng minh số lượng hay định mức |
| `PRESENT_REPORTED_PARTIAL` | Có linh kiện nhưng số lượng/định mức chỉ xác minh được một phần |
| `PRESENT_REPORTED_TEST_REPORTED` | Người dùng báo có linh kiện và có kết quả bench; chưa có ảnh |
| `PARTIAL_QUANTITY` | Số lượng thấp hơn yêu cầu đã freeze |
| `UNAPPROVED_SUBSTITUTION` | Khác linh kiện đã freeze; **cần** change review |
| `UNVERIFIED` | Chưa xác minh được bằng chứng hiện có |

Trong `pin-candidates-v0.md`, phân loại dùng đúng bốn mức canonical `known` / `likely` / `unknown` / `must test`.

Quy ước cột `photo_ref`: ảnh được liệt kê ở đây có thể là **ảnh lấy linh kiện làm đối tượng** (chứng cứ trực tiếp) hoặc **ảnh toàn cảnh nơi linh kiện xuất hiện phụ** (chỉ truy vết, không phải chứng cứ). Trạng thái `inspection_status` cho biết trường hợp nào; các dòng `PRESENT_REPORTED` / `PRESENT_REPORTED_PARTIAL` đi kèm ảnh toàn cảnh thuộc trường hợp thứ hai.

## Files

| File | Nội dung |
|---|---|
| `bom-audit.csv` | 24 vị trí đã freeze; quan sát, số lượng, truy xuất nguồn, mức không chắc chắn, hành động tiếp theo |
| `photo-inventory.csv`, `photos/` | 25 ảnh người dùng tải lên kèm giới hạn của từng ảnh, tên file nguồn (`source_upload_filename`) và nhãn `cropped`. Tên file trong repo là tên tất định `NN-mo-ta.jpg` |
| `pin-candidates-v0.md` | Đường UART/logic/1-Wire/GPIO candidate; **không** đóng băng GPIO |
| `physical-risk-ledger.md` | Rủi ro điện/cơ và biện pháp kiềm chế bắt buộc |
| `freeze-deviation-review.md` | Bốn sai lệch so với BOM đã freeze, chờ leader + D quyết định |
| `legacy-assumption-check.md` | Loại bỏ kiến trúc cũ và phạm vi rà soát |
| `hardware-audit-w01.md` | Tóm tắt, sai lệch, khoảng trống danh tính, kết luận |
| `acceptance.md` | Checklist W01, blocker, chủ sở hữu hành động (nguồn duy nhất cho trạng thái) |
| `team-w01-member-a-summary.md` | TEAM-W01-01/04: thẩm quyền, 5 invariant, 5 dependency, 3 risk, trả lời walkthrough |
| `validate_w01.py` | Kiểm tra cấu trúc file (24 dòng BOM, ảnh tồn tại). **Không** xác nhận đúng/sai vật lý |
| `PR_BODY.md` | Đề xuất mô tả PR — tài liệu review cục bộ, **chưa** publish |

## Trường bắt buộc theo `docs/05A §8`

`docs/05A §8` yêu cầu mỗi README bằng chứng ghi đủ các trường sau. Bộ W01 này **không** phải một lần chạy thí nghiệm đơn lẻ, nên phần lớn trường mang giá trị cấp-bộ-hồ-sơ:

| Trường | Giá trị |
|---|---|
| `date` | 2026-10-17 (người dùng thao tác vật lý) · 2026-10-18 (hiệu chỉnh tài liệu + hợp nhất 25 ảnh) |
| `operator` | Member A (người vận hành vật lý; không ghi tên cá nhân trong repo) |
| `hardware_config_id` | `NOT_ASSIGNED` — chưa được leader gán |
| `firmware commit` | `NOT_RECORDED` — W01 không nạp firmware mới |
| `test IDs` | `A-W01-01`, `A-W01-02`, `A-W01-03`, `A-W01-04`, `A-W01-05` (chi tiết ở `acceptance.md`) |
| `setup` | Kiểm kê vật lý, **không** cấp nguồn 220 VAC; các phép đo bench là **do người dùng báo** (xem `hardware-audit-w01.md` §Kết quả) |
| `result` | 24/24 dòng BOM được kiểm kê thành dòng; 4 sai lệch chờ quyết định; xem `acceptance.md` |
| `pass/fail` | `NOT PASS` — `W01_PENDING_REVIEW` |
| `anomalies` | 4 CR trong `freeze-deviation-review.md` + 5 mục trong bảng `Watchlist` của cùng file |

Bảng này **không** phải nguồn trạng thái; trạng thái canonical nằm duy nhất ở `acceptance.md`.

## Reproduction / review

1. Chạy `py validate_w01.py` (khuyến nghị trên Windows). Lưu ý: trên một số máy, `python` là alias Microsoft Store bị hỏng và sẽ **không** chạy.
2. Mở `bom-audit.csv`; rà toàn bộ 24 dòng, đặc biệt HW-06, HW-07, HW-16, HW-17, HW-18, HW-19, HW-23.
3. Đối chiếu từng `photo_ref` với `photo-inventory.csv`; các mục HW-19, HW-22, HW-24 vẫn **không** có ảnh (khuyến nghị, **không** thuộc danh sách ảnh canonical `docs/05A §10` A-W01-02).
4. Đọc `pin-candidates-v0.md` — hành vi đã quan sát **không** phải pin map production đã freeze.
5. Leader quyết định bốn sai lệch trong `freeze-deviation-review.md`; D rà soát `physical-risk-ledger.md`.
6. Bổ sung ảnh/SKU còn thiếu, ghi firmware commit, gán `hardware_config_id`, rồi ký `acceptance.md`.

## W01 quality gate

**Chưa PASS.** Cả 24 vị trí đã freeze đều được *kiểm kê thành dòng*, nhưng hai thay thế linh kiện chưa được duyệt (HW-07, HW-17) và nhiều khoảng trống danh tính/số lượng chặn việc tuyên bố đã reconcile vật lý đầy đủ. Artifact ở mức **PR-reviewable**, với blocker được nêu tường minh trong `acceptance.md`.

## Handoffs

- **To C:** `device_id` candidate = `coldguard-001` (cần C xác nhận; xem `backend/fixtures/telemetry_v0.json`); `hardware_config_id` cuối cùng chưa được gán.
- **To D:** `physical-risk-ledger.md`, `freeze-deviation-review.md` — cần ký trước khi thay đổi cách xử lý dòng điện.
- **To leader:** `bom-audit.csv` và các quyết định review; mọi thay đổi Docs 00–01 phải qua cập nhật có kiểm soát.
