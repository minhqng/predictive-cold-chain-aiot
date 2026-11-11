# Bộ câu hỏi và trả lời bảo vệ — Member B (W24)

> Dùng kèm [`oral-defense-vi-W24.md`](oral-defense-vi-W24.md). Mọi câu trả lời
> phải giữ đúng lớp bằng chứng; không biến dữ liệu mô tả thành kết quả dự báo.

## A. Bảy câu hỏi bắt buộc

### 1. Vì sao không chia ngẫu nhiên theo từng dòng dữ liệu?

Vì các dòng cảm biến liên tiếp trong cùng một lần chạy có tương quan rất mạnh.
Nếu chia ngẫu nhiên theo dòng, các dòng gần nhau sẽ xuất hiện ở cả tập huấn luyện
và tập kiểm tra, làm mô hình học gần như thuộc lòng và cho điểm số cao giả tạo.
Nhóm chia theo đơn vị độc lập là lần chạy/nhóm cặp (`run_id + pair_id`), và kiểm
tra rằng không có nhóm nào nằm ở hai phía. Bằng chứng: `ml/reports/W11/cv-fold-manifest.yaml`,
`leakage-audit-W11.md`.

### 2. Vì sao dùng Average Precision?

Sự kiện tới hạn tương đối hiếm so với số khung dữ liệu, nên độ chính xác tổng thể
dễ bị chi phối bởi lớp bình thường. Average Precision tóm tắt đường precision–recall
và nhạy hơn với việc phát hiện lớp sự kiện hiếm. Tuy vậy AP không thay thế các chỉ
số vận hành: precision, recall, số sự kiện bị bỏ sót và số cảnh báo giả vẫn phải
được báo cáo. Điểm AP = 1,0 trong W11/W15 là trên dữ liệu tổng hợp, **không phải**
độ chính xác dự báo vật lý.

### 3. Vì sao điểm của mô hình không phải xác suất?

Mô hình hiện tại trả về điểm rủi ro chưa được hiệu chuẩn trên dân số vật lý. Nhóm
chưa có tập hiệu chuẩn thật, chưa chọn phương pháp hiệu chuẩn và chưa chứng minh
quan hệ giữa điểm số với tần suất sự kiện. Vì vậy không được nói “90% khả năng
hỏng”. Trạng thái đúng là `RISK_SCORE_ONLY`; xem `model-manifest-W15.json` và
`calibration-report.md` của W14.

### 4. Vì sao cảnh báo sớm và hiệu ứng A/B là hai câu hỏi khác nhau?

Cảnh báo sớm hỏi: hệ thống có dự đoán được sự kiện **trước khi nó xảy ra** hay
không, với dữ liệu quan sát bình thường. Phân tích A/B hỏi: khi dùng điều khiển dự
báo, **kết quả vật lý** có tốt hơn điều khiển thường hay không, trên các cặp chạy
so sánh được. Một mô hình dự báo tốt chưa chắc tạo ra cải thiện A/B; ngược lại,
một so sánh A/B không chứng minh năng lực dự báo. W22 chỉ là bộ máy thống kê trên
fixture; W20 chưa chạy nên chưa có kết luận A/B.

### 5. Vì sao chọn XGBoost thay vì LSTM?

Đây là bài toán dữ liệu dạng bảng với số mẫu nhỏ, nhiều đặc trưng thủ công và yêu
cầu tái lập đơn giản. XGBoost là baseline phù hợp, huấn luyện nhanh, ít phụ thuộc
và dễ giải thích hơn. Nhóm đã ghi nhận quyết định **không** theo đuổi mô hình sâu
khi chưa có bằng chứng dữ liệu vật lý đủ mạnh (`deep-model-decision-W15.md`).
Không có tuyên bố XGBoost vượt trội trên tủ lạnh thật.

### 6. Mẫu nhỏ ảnh hưởng thế nào?

Nhiều dòng cảm biến trong cùng một lần khởi động không phải nhiều thí nghiệm độc
lập. Gói A hiện có 18 dòng/đoạn nhưng chỉ thuộc 8 boot, và **0** lần chạy độc lập
đủ điều kiện dự báo. Vì vậy không thể tách tập huấn luyện/kiểm tra vật lý đáng tin
cậy, không thể ước lượng AP, EWT hay AIW thật. Kết luận khoa học bị giới hạn bởi
số đơn vị độc lập, không phải số dòng.

### 7. Điều gì sẽ làm một tuyên bố khoa học mất hiệu lực?

- Ánh xạ cảm biến sai (ví dụ dùng T2 phía nóng như nhiệt độ buồng).
- Sai thời điểm sự kiện hoặc thiếu đồng bộ thời gian.
- Thiếu hiệu chuẩn hoặc mất định danh thiết bị.
- Không xác minh được danh tính lần chạy.
- Huấn luyện và kiểm tra chồng lấn nguồn.
- Nhãn được bịa từ ngưỡng chưa chốt.
- So sánh vật lý không hợp lệ hoặc đổi chính sách giữa thí nghiệm.
- Mất tính toàn vẹn nguồn hoặc diễn giải vượt quá lớp bằng chứng.

## B. Câu hỏi bổ sung

### 8. Member B đã thực sự hoàn thành những gì?

Chuỗi phần mềm W01–W23: từ điển dữ liệu, sinh dữ liệu tổng hợp, sinh đặc trưng
nhân quả, chia nhóm, benchmark XGBoost, kiểm tra rò rỉ, hiệu chuẩn (kết luận chỉ
điểm rủi ro), kiểm tra sẵn sàng W16, shadow parity, giám sát vận hành, sổ cặp,
cổng khóa phân tích, chẩn đoán W21, bộ máy thống kê W22 và gói bằng chứng W23.
Ngoài ra là gói phục hồi dữ liệu vật lý hiện có với 12 biểu đồ thật. Tất cả đều
có báo cáo, manifest và test.

### 9. Dự án có dữ liệu vật lý thật nào?

Gói A 20261107: 18 dòng/đoạn, 9.293 khung, 8 boot, 4 cửa sổ S1 và 5 cửa sổ S2
(4 cửa sổ `S2_DOOR` + 1 cửa sổ `S2_TIMING`) được A chấp nhận, cùng các đoạn làm
lạnh H8-C, H8-E và W07. Ngoài ra có 100 khung chẩn đoán W21 trên thiết bị (tiêm
phần mềm, tầng đầu ra đã bị biên dịch loại bỏ). Không có lần chạy nào đủ điều
kiện dự báo độc lập.

### 10. 12 biểu đồ vật lý cho thấy gì?

Hai biểu đồ nhiệt độ buồng (chamber-air), ba biểu đồ làm lạnh H8-C/H8-E/W07, năm
biểu đồ cửa, một biểu đồ thiếu dữ liệu và một biểu đồ chẩn đoán W05. Chúng hiển
thị nhiệt độ theo thời gian uptime, trạng thái cửa, công suất nhánh làm lạnh và
khoảng thiếu dữ liệu. Mỗi biểu đồ ghi rõ nguồn, revision, SHA-256, đơn vị độ C và
nhãn `PHYSICAL_RECORDED_DATA`. Chúng **không** phải biểu đồ dự báo.

### 11. Quan sát làm lạnh thật cho thấy gì?

H8-C 600 giây: nhiệt độ buồng giảm 8,71 °C, phía nóng TEC tăng 9,69 °C. H8-E
1.800 giây: TEC chạy 100%, phía nóng tăng 7,75 °C nhưng nhiệt độ buồng gần như
không đổi (0,10 °C). W07 500‰: nhiệt độ buồng giảm 2,25 °C, phía nóng tăng
3,69 °C. Đây là các quan sát thật; không được biến thành kết luận “hệ thống làm
lạnh hiệu quả” hay “AI dự báo đúng”.

### 12. Vì sao mô hình W15 không thể triển khai?

Vì mô hình huấn luyện trên dữ liệu tổng hợp, chưa hiệu chuẩn, chưa có dân số vật
lý, chưa khóa ngưỡng và chưa có phê duyệt. Manifest ghi
`SYNTHETIC_SOFTWARE_CONTROL_ONLY`, `NON_DEPLOYABLE_CANDIDATE`,
`RISK_SCORE_ONLY`. Chẩn đoán nội tại cho thấy 27/28 đặc trưng không được dùng.

### 13. Việc mô hình phụ thuộc `time_since_open` có nghĩa gì?

Cây quyết định chỉ chia theo thời gian kể từ lần mở cửa. Trên fixture tổng hợp,
đây là lối tắt học được từ cách sinh dữ liệu, không phải quan hệ nhân quả với sự
cố nhiệt. Đó là một lý do khoa học để không triển khai mô hình, không phải bằng
chứng mô hình dự báo giỏi. Chi tiết trong `A3-model-inspection-W15.json`.

### 14. Vì sao Gate B vẫn đỏ?

Vì thiếu các điều kiện vật lý tối thiểu: thời gian tuyệt đối và đồng bộ đồng hồ,
hiệu chuẩn, định danh thiết bị, run ID nhất quán, cấu hình phần cứng được xác
minh, dân số lần chạy độc lập đủ lớn và nhãn sự kiện tới hạn được chốt. W08 ghi
12 mã lý do. Việc phần mềm W08 chạy đúng (`GREEN`) không làm cổng vật lý xanh.

### 15. Vì sao W16 không được thực thi?

Vì 24 điều kiện tiên quyết chưa đạt: chưa có dân số vật lý, chưa khóa target và
horizon, chưa khóa ngưỡng và persistence, chưa có phê duyệt của B/A/C/D/trưởng
nhóm và chưa có quyền chạy. W16 là bản đăng ký trước và báo cáo từ chối
(`NOT_EXECUTED_PREREQUISITES_UNMET`), không phải bài kiểm tra đã chạy.

### 16. Vì sao chưa có EWT và AIW thật?

EWT cần quỹ đạo vật lý không bị can thiệp, có mốc cảnh báo và mốc sự kiện đáng
tin cậy. AIW cần chuỗi độ trễ đo được từ cảnh báo đến hành động. Hiện chưa có
nhãn sự kiện, chưa có thời gian tuyệt đối và chưa có chuỗi hành động vật lý được
xác minh, nên cả hai là `NOT_ESTIMABLE`. Không được biểu diễn chúng bằng 0.

### 17. Vì sao chưa có kết quả cải thiện A/B vật lý?

Vì chưa có cặp chạy vật lý hợp lệ, chưa khóa mục tiêu cặp, chưa có phê duyệt
chiến dịch và Controller B chưa được cấp quyền. W20 giữ khóa phân tích; W22 chỉ
kiểm thử bộ máy thống kê trên 8 cặp đồ chơi. Vì vậy không có hiệu ứng, CI hay
p-value thật.

### 18. Công việc còn lại thuộc về ai?

- Thành viên A: danh tính lần chạy, đồng bộ thời gian, hiệu chuẩn, định danh thiết
  bị, cấu hình phần cứng và dân số chạy độc lập.
- Thành viên C: nguồn gốc thời gian telemetry, shadow trace thật, tích hợp
  Controller B và độ bền broker.
- Thành viên D: chính sách, ngưỡng tới hạn, persistence, an toàn và phê duyệt.
- Trưởng nhóm: phê duyệt đóng băng, duyệt phát hành, tổng duyệt demo và chấp nhận
  cuối cùng.
- Member B: bàn giao phần mềm, tài liệu, tái lập và các hành động sửa lỗi trong
  phạm vi B.

### 19. Có thể trình diễn gì một cách trung thực tại buổi bảo vệ?

Có thể trình diễn: pipeline phần mềm chạy được, test tái lập, kiểm tra hash mô
hình, bảng mô tả vật lý thật, 12 biểu đồ thật, quy trình từ chối W16/W20 và bộ máy
thống kê W22 trên fixture. Không thể trình diễn: độ chính xác dự báo vật lý, EWT,
AIW, cải thiện A/B, CI hoặc p-value thật.

### 20. Nếu hội đồng hỏi “mô hình có tốt không?”

Trả lời: trên dữ liệu tổng hợp, pipeline hoạt động và cho AP = 1,0; nhưng đây là
kiểm soát phần mềm, không phải bằng chứng vật lý. Trên dữ liệu thật, chưa có kết
quả vì chưa đủ điều kiện khoa học. Vì vậy không thể kết luận mô hình tốt hay xấu
cho tủ lạnh thật.

### 21. Nếu hội đồng hỏi “tại sao không dùng số liệu tổng hợp thay thế?”

Vì mục tiêu của đồ án là đánh giá trên thiết bị thật. Số liệu tổng hợp chỉ dùng để
kiểm thử phần mềm và phát hiện lỗi pipeline. Thay thế kết quả vật lý bằng số liệu
tổng hợp sẽ là tuyên bố khoa học sai. Nhóm giữ trạng thái `NOT_PRODUCED` thay vì
tạo bảng giả.

### 22. Nếu hội đồng hỏi “ai đã tái lập độc lập?”

Hiện chưa có người thứ hai tái lập. Trạng thái là `INDEPENDENT_TEAM_MEMBER_REPLAY =
PENDING`. Nhóm đã chuẩn bị runbook và mẫu biên nhận, nhưng không được bịa tên,
chữ ký hay thời điểm. Đây là hành động bàn giao tiếp theo.
