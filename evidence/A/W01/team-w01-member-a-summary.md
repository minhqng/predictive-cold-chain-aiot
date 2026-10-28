# TEAM-W01-01 / TEAM-W01-04 — Member A architecture understanding

**Owner:** Member A · **Snapshot:** 2026-10-18 · **Status:** draft cho team walkthrough (chưa phải đồng thuận của team).

## Source authority

Thứ tự: `docs/00` scope/BOM → `docs/01` measurement correctness → `docs/02` closed-loop → `docs/03` experiments → `docs/04` execution → `docs/05A` lịch Member A. Thay đổi hardware freeze phải qua review của leader/team và cập nhật có kiểm soát vào tài liệu cha.

## Five non-negotiable invariants

1. **Đúng một** nhánh làm lạnh đã mua (một TEC, một driver, một shunt ngoài), không dùng lại cách đấu hai TEC cũ.
2. Ba vai trò DS18B20 chính T1/T2/T3 gắn với **địa chỉ ROM duy nhất** và vị trí vật lý; thứ tự discovery không phải danh tính.
3. Một command, ACK hoặc duty PWM **không** chứng minh có làm lạnh vật lý; cần phản hồi điện và đáp ứng nhiệt.
4. Chạy tải dòng lớn cần fuse đúng nhánh, định mức dây/đầu nối đúng, V1/quạt tản nhiệt hoạt động, logic BTS mặc định OFF và đã được review.
5. Chuỗi đo mang validity/quality/provenance tường minh; profile shunt PZEM chưa hiệu chuẩn hoặc thiếu số đọc dòng thì không được coi là mẫu công suất hợp lệ.

## Five critical dependencies

1. Đúng BOM/model/SKU/ảnh và `hardware_config_id` được duyệt.
2. PSU an toàn, fuse nhánh, dây dẫn và miền logic 3.3 V/5 V dùng chung nhưng được bảo vệ.
3. Pin map của board, danh tính ROM 1-Wire, I²C của BME và vị trí MC-38.
4. Giao tiếp RS485 của PZEM cùng cấu hình/readback shunt 50 A và bao điện áp/dòng.
5. Interlock BTS7960/TEC/quạt V1 và plant nhiệt tái lập được trước các campaign dữ liệu.

## Three highest priority risks

- **Nguy hiểm điện** từ cọc AC lộ, ngắn mạch 12 V/33 A, cos/sai fuse hoặc đặt shunt sai vị trí.
- **Lệch hardware freeze**, đặc biệt MAX3485 3.3 V đã freeze so với TTL485-V2.0 5 V thực tế, và TB4504 so với TB4506; cả hai cần change review tường minh.
- **Bằng chứng vật lý không đáng tin** do đổi chỗ cảm biến nhiệt, dải đo PZEM chưa xác minh, hoặc suy dòng TEC từ nhãn của người bán.

## Evidence A owns

BOM/module passport W01, pin candidates, risk ledger; log cảm biến H0/H1 và vị trí ROM ở W02; cấu hình RS485/PZEM an toàn và envelope OFF ở W03; các lần chạy TEC/nhiệt vật lý và bằng chứng nghiệm thu từ W04 trở đi. Các contract downstream được phối hợp với B/C/D, không do A định nghĩa lại.

## Walkthrough answers (bản nháp thảo luận nhóm)

1. **Vì sao một TEC?** Đúng BOM hiện tại, tránh phức tạp nhiều nhánh không có căn cứ, và cho phép truy vết một nhánh actuation/đo duy nhất.
2. **PZEM chứng minh điều gì?** Phản hồi **điện** độc lập (điện áp/dòng/công suất khi đã cấu hình và xác minh); một mình nó không chứng minh có bơm nhiệt hay an toàn thực phẩm.
3. **Vì sao ACK ≠ success?** Việc nhận và thực thi ở tầng phần mềm có thể xảy ra mà không có dòng chảy hoặc cải thiện nhiệt; phải kiểm chứng năng lượng nhánh đo được và động học cảm biến.
4. **Ai sở hữu trạng thái `reported`?** Trạng thái do thiết bị báo và nguồn telemetry thuộc firmware A; backend C lưu/duy trì biểu diễn `reported` trong Digital Twin. Các trường desired/policy là ranh giới governance riêng.
5. **Vì sao các dòng không độc lập?** Chuỗi thời gian của cùng một lần chạy chia sẻ điều kiện đầu, động học, môi trường và nhiễu; phải chia/đánh giá theo experiment/run và theo thời gian, không trộn dòng ngẫu nhiên.
6. **Nếu broker biến mất thì sao?** Edge controller phải giữ **SAFE_LOCAL** với ngưỡng/hysteresis xác định và giới hạn an toàn vật lý; an toàn TEC không được phụ thuộc cloud.

**Team signoff required:** Member A / B / C / D / leader chưa ký bản nháp này.
