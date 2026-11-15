# Tóm tắt trình bày — dữ liệu vật lý hiện có (Member B)

> Bản tóm tắt cho buổi bảo vệ đồ án đại học. Nội dung chỉ dựa trên các nguồn đã kiểm tra SHA-256 trong gói `ml/reports/DataRecovery/`.
> Không có phép đo mới, không huấn luyện mô hình mới và không thay đổi kết luận Gate B.

## 1. Nhóm đã thực sự thu được gì?

- Gói A 20261107 có **18 dòng/đoạn**, **9293 khung**, trên **8 lần khởi động (boot)** khác nhau.
- Có **4 cửa sổ S1** được A chấp nhận (nền nhiệt thụ động) và **5 cửa sổ S2** được A chấp nhận (4 lần mở cửa + 1 cửa sổ định thời).
- Có 4 đoạn làm lạnh thực: H8-C 600 s, H8-E 1800 s và hai lần chạy W07 ở 500‰.
- W21 có 100 khung ghi nhận trên một phiên thiết bị, hai test ID; tầng đầu ra đã bị biên dịch loại bỏ (compiled out).

Điểm quan trọng: 18 dòng/đoạn **không phải** 18 thí nghiệm độc lập. Giới hạn độc lập là số boot (8), không phải số dòng hay số cửa sổ.

## 2. Những quan sát thực có thể tin cậy

- **S1 (nền thụ động):** bốn cửa sổ S1 có nhiệt độ trung bình 29.4624–29.8589 °C; ví dụ trial2 là 29.8021 °C với thay đổi quan sát 0.0417 °C trong cửa sổ khoảng 10 phút. Đây là mô tả nhiệt, không phải kết quả dự báo.
- **S2 (mở cửa):** 5 cửa sổ, mỗi cửa sổ có một lần mở cửa được ghi nhận; thời lượng theo khung ghi nhận 12.9–14.1 s (13–14 khung; log lệnh của người vận hành ghi thời lượng dài hơn, khác biệt do cách đo và độ phân giải 1 Hz, không dùng để suy ra cơ chế). Trong cửa sổ mở cửa, nhiệt độ buồng thay đổi rất nhỏ (ví dụ W10-03-run1: 0.0038 °C so với trước khi mở). Không có ngưỡng tới hạn nào bị vượt qua và không được tạo ra sự kiện tới hạn giả.
- **H8-C 600 s:** giai đoạn làm lạnh có nhiệt độ buồng thay đổi -8.7083 °C; T2 (phía nóng TEC) thay đổi 9.6870 °C. PZEM chỉ đo nhánh làm lạnh, không đo toàn hệ thống.
- **H8-E 1800 s:** TEC chạy 100% và T2 tăng 7.7500 °C, nhưng nhiệt độ buồng gần như không đổi (0.1037 °C). Đây là quan sát thật; không được biến nó thành bằng chứng làm lạnh hiệu quả.
- **W07 500‰:** nhiệt độ buồng thay đổi -2.2500 °C, T2 tăng 3.6875 °C trong khoảng 180 khung.

Các giá trị trên đều có nguồn, quy tắc tính và giới hạn trong `real-observation-summary.csv`.

## 3. Member B đã xử lý như thế nào?

- Kiểm tra SHA-256 của manifest, run index, từng CSV chuẩn hóa và các nguồn W05/W21 trước khi đọc.
- Tách T2 (phía nóng TEC) khỏi mọi phép tính nhiệt độ buồng.
- Chỉ dùng khung có trạng thái kênh `OK`; khung thiếu/không hợp lệ được đếm và công bố, không thay bằng 0.
- Thời gian chỉ là uptime trong một boot; không gọi là thời gian tuyệt đối đã đồng bộ.
- Không tạo nhãn từ ngưỡng tới hạn chưa chốt; không chia train/test theo dòng; không mở W16; không chạy W20.

## 4. Prototype hiện tại chứng minh được gì?

- Pipeline XGBoost tổng hợp (W15) và artifact có kiểm tra hash; mô hình là **SYNTHETIC_SOFTWARE_CONTROL_ONLY**, **NON_DEPLOYABLE**, điểm số chỉ là **RISK_SCORE_ONLY**, không phải xác suất đã hiệu chuẩn.
- Sinh đặc trưng nhân quả, kiểm tra rò rỉ, đánh giá theo nhóm trên dữ liệu tổng hợp; các kết quả này **không phải** kết quả vật lý.
- Kiểm tra chất lượng dữ liệu, độ tươi, shadow parity offline và thống kê cặp trên fixture kiểm thử.
- Chẩn đoán cảm biến/PZEM có giới hạn trong W21; không phải độ chính xác phát hiện lỗi vật lý.

## 5. Những gì chưa được xác minh

- Gate B vật lý: **RED**; bộ dữ liệu dự báo: **NOT_READY**. Đây là kết quả thật của W08, không phải trạng thái của gói demo.
- Chưa có EWT/AIW thực; chưa có AP, recall sự kiện hay độ chính xác dự báo vật lý.
- Chưa có calibration, device identity hay đồng hồ thời gian tuyệt đối; chưa có nhãn sự kiện tới hạn được chốt.
- Raw log W21 không có trong checkout; PR #95 vẫn chưa merge và không được dùng làm bằng chứng chuẩn.

## 6. Câu kết luận nên dùng

"Nhóm đã thu được dữ liệu vật lý thật và xử lý được một tập mô tả có giới hạn: nền S1, 5 cửa sổ mở cửa S2, các bước làm lạnh H8-C/H8-E/W07 và chẩn đoán W21 có giới hạn. Nhóm **chưa** chứng minh được mô hình dự báo vật lý: Gate B vẫn đỏ, chưa có nhãn tới hạn và chưa có thời gian sự kiện tuyệt đối. Vì vậy báo cáo chỉ trình bày mô tả vật lý và prototype phần mềm, không tuyên bố hiệu năng dự báo."

Trạng thái gói demo: **READY**; tái sử dụng dữ liệu hiện có: **READY_FOR_BOUNDED_ANALYSIS**.

