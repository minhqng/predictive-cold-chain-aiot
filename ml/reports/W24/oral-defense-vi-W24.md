# Chuẩn bị bảo vệ — Member B (W24)

> Tài liệu này dùng cho buổi bảo vệ đồ án. Mọi con số đều lấy từ gói
> `ml/reports/DataRecovery/` và các báo cáo W11–W23 đã kiểm tra SHA-256.
> Không có phép đo mới, không huấn luyện lại mô hình và không thay đổi kết luận
> Gate B.

```text
ORAL_DEFENSE_CONTENT = READY
LIVE_TEAM_REHEARSAL = PENDING
```

## 1. Kịch bản khoảng hai phút

Kính thưa hội đồng,

Em là thành viên B của nhóm ColdGuard, phụ trách phần AI và dữ liệu. Trong học kỳ vừa qua, em đã hoàn thành chuỗi phần mềm từ tuần 01 đến tuần 23: từ từ điển dữ liệu, sinh dữ liệu tổng hợp, sinh đặc trưng nhân quả, chia dữ liệu theo nhóm, huấn luyện và đánh giá XGBoost, cho đến các cổng kiểm soát chất lượng, kiểm tra rò rỉ dữ liệu, giám sát vận hành và bộ máy thống kê cặp.

Điểm quan trọng nhất của tuần cuối là gói phục hồi dữ liệu vật lý hiện có. Nhóm đã kiểm tra SHA-256 toàn bộ nguồn và phân tích được 18 dòng/đoạn dữ liệu thật, tổng cộng 9.293 khung, thuộc 8 lần khởi động thiết bị. Trong đó có 4 cửa sổ nền S1 và 5 cửa sổ S2 do thành viên A chấp nhận (4 cửa sổ mở cửa và 1 cửa sổ định thời). Gói này tạo ra 12 biểu đồ vật lý thật.

Các quan sát chính: nền S1 dao động khoảng 29,46 đến 29,86 độ C. Năm cửa sổ S2 đều có chuyển trạng thái cửa được ghi nhận, kéo dài khoảng 13 đến 14 giây theo khung dữ liệu; nhiệt độ buồng thay đổi rất nhỏ. Thí nghiệm làm lạnh H8-C 600 giây làm nhiệt độ buồng giảm 8,71 độ C trong khi phía nóng TEC tăng 9,69 độ C. H8-E chạy TEC 100% trong 1.800 giây nhưng nhiệt độ buồng gần như không đổi, chỉ 0,10 độ C. Đây là dữ liệu mô tả thật, không phải kết quả dự báo.

Về mặt khoa học, nhóm chưa chứng minh được mô hình dự báo vật lý. Gate B vẫn đỏ vì thiếu đồng hồ thời gian tuyệt đối, thiếu hiệu chuẩn, thiếu định danh thiết bị và thiếu nhãn sự kiện tới hạn. Có 0 lần chạy đủ điều kiện dự báo độc lập. Mô hình XGBoost hiện tại chỉ là mô hình tổng hợp dùng cho kiểm thử phần mềm, không thể triển khai; đầu ra chỉ là điểm rủi ro, không phải xác suất đã hiệu chuẩn. Bài kiểm tra W16 chưa được mở và phân tích A/B vật lý W20 chưa được chạy.

Vì vậy, em bàn giao một gói phần mềm có thể tái lập, cùng các kết quả mô tả vật lý có giới hạn và danh sách rõ ràng những gì còn thiếu. Nhóm không tuyên bố hiệu năng dự báo hay mức cải thiện A/B khi chưa có bằng chứng. Em xin cảm ơn hội đồng.

## 2. Giải thích kỹ thuật chi tiết

### 2.1 Phạm vi và phân loại bằng chứng

| Lớp bằng chứng | Ý nghĩa | Ví dụ |
|---|---|---|
| `PHYSICAL_RECORDED_DATA` | Đo thật, chỉ dùng mô tả/chẩn đoán | 18 đoạn, 9.293 khung, 12 biểu đồ |
| `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | Dữ liệu tổng hợp, chỉ kiểm thử phần mềm | W11/W15/XGBoost AP = 1.0 |
| `SOFTWARE_VERIFICATION` | Phần mềm đã kiểm thử, không phải kết quả vật lý | W16–W23, W22 |
| `ON_DEVICE_SOFTWARE_INJECTION` | Chẩn đoán trên thiết bị bằng tiêm phần mềm | W21 |
| `NOT_ESTIMABLE` / `NOT_PRODUCED` | Không thể tính hoặc không được tạo | EWT, AIW, bảng dự báo cuối |

### 2.2 Chuỗi phần mềm đã hoàn thành

- Từ điển dữ liệu, ánh xạ nghiên cứu và đặc tả metric.
- Sinh dữ liệu tổng hợp có kiểm soát; sinh cửa sổ thời gian và nhãn phát triển.
- Chia dữ liệu theo nhóm `run_id + pair_id`, không chia theo dòng.
- Đặc trưng nhân quả, chỉ dùng thông tin có trước điểm dự báo.
- Benchmark XGBoost theo nhóm, kiểm tra rò rỉ và ablation.
- Đánh giá hiệu chuẩn: kết luận `RISK_SCORE_ONLY`, không có xác suất.
- Kiểm tra sẵn sàng khóa test W16: từ chối chạy vì thiếu điều kiện.
- Shadow parity offline, giám sát vận hành, sổ cặp và cổng khóa phân tích.
- Bộ máy thống kê cặp W22 và gói bằng chứng W23.
- Gói phục hồi dữ liệu vật lý hiện có và 12 biểu đồ thật.

### 2.3 Cách xử lý dữ liệu vật lý

- Kiểm tra SHA-256 của manifest, run index, từng CSV chuẩn hóa trước khi đọc.
- Tách T2 (phía nóng TEC) khỏi mọi phép tính nhiệt độ buồng. T1/T3/T4 lần lượt là tâm, đáy và gần cửa buồng.
- Chỉ dùng khung có trạng thái kênh `OK`; khung thiếu được đếm và công bố, không thay bằng 0.
- Thời gian chỉ là uptime trong một lần khởi động, không gọi là thời gian tuyệt đối.
- Không tạo nhãn từ ngưỡng chưa chốt; không chia train/test theo dòng; không mở W16; không chạy W20.

### 2.4 Kết quả vật lý thật

| Nguồn | Quan sát |
|---|---|
| S1 (4 cửa sổ) | Nhiệt độ trung bình 29,4624–29,8589 °C; trial2 là 29,8021 °C, thay đổi 0,0417 °C trong khoảng 10 phút |
| S2 (5 cửa sổ) | Gồm 4 cửa sổ `S2_DOOR` và 1 cửa sổ `S2_TIMING`; cả năm đều ghi nhận chuyển trạng thái cửa; thời lượng theo khung 12,9–14,1 giây; nhiệt độ buồng thay đổi rất nhỏ, ví dụ W10-03-run1 là 0,0038 °C |
| H8-C 600 s | Nhiệt độ buồng giảm 8,7083 °C; T2 tăng 9,6870 °C |
| H8-E 1800 s | TEC 100%; T2 tăng 7,7500 °C; nhiệt độ buồng chỉ đổi 0,1037 °C |
| W07 500‰ | Nhiệt độ buồng giảm 2,2500 °C; T2 tăng 3,6875 °C trong khoảng 180 khung |

Các giá trị này là mô tả có nguồn và có giới hạn trong
`real-observation-summary.csv`. Không có ngưỡng tới hạn nào bị vượt qua và
không có sự kiện tới hạn giả nào được tạo.

### 2.5 Vì sao chưa có kết quả dự báo vật lý

1. Không có nhãn sự kiện tới hạn: ngưỡng Tmean tới hạn và nhiệt độ đại diện chưa được chốt.
2. Không có thời gian tuyệt đối: thiếu đồng hồ thiết bị và bằng chứng đồng bộ.
3. Không có hiệu chuẩn và định danh thiết bị.
4. 18 đoạn chỉ thuộc 8 boot; các cửa sổ lặp lại không phải lần chạy độc lập. Không có nhóm kiểm tra độc lập.
5. Vì vậy AP, recall sự kiện, EWT, AIW và độ chính xác dự báo vật lý đều `NOT_ESTIMABLE`.

### 2.6 Mô hình W15

- Thuật toán: XGBoost trên đặc trưng dạng bảng.
- Dữ liệu huấn luyện: 1.936 mẫu tổng hợp từ 16 lần chạy phát triển; không dùng locked test.
- Hiệu năng trên fixture tổng hợp: AP = 1,0; đây là kiểm soát phần mềm, không phải độ chính xác vật lý.
- Đầu ra: điểm rủi ro trong khoảng [0, 1], chưa hiệu chuẩn thành xác suất.
- Trạng thái: `SYNTHETIC_NON_DEPLOYABLE_CANDIDATE`; không được điều khiển Controller B.
- Chẩn đoán nội tại: 27/28 đặc trưng không được dùng; cây chỉ chia theo `time_since_open`. Đây là lý do mô hình không thể triển khai, không phải bằng chứng dự báo.

### 2.7 Các cổng khoa học

| Cổng | Trạng thái | Lý do chính |
|---|---|---|
| Gate B | RED | Thiếu thời gian tuyệt đối, hiệu chuẩn, định danh thiết bị, run ID, nhãn tới hạn |
| G3 | NO-GO / FIX DATA | Chưa có benchmark dự báo vật lý |
| G4 | NOT_READY | Thiếu bằng chứng khóa test, AIW, shadow thật, an ninh, SAFE_LOCAL |
| G5 | NOT_ESTABLISHED | Chưa có phê duyệt cuối và vận hành vật lý |
| W16 | NOT_OPENED | 24 lý do từ chối; chưa có phê duyệt và điều kiện khoa học |
| W20 | NOT_RUN | Chưa có cặp vật lý hợp lệ và chưa được cấp quyền |

## 3. Giới hạn cần nói rõ

- Phần mềm hoàn chỉnh không đồng nghĩa với chấp nhận khoa học cuối cùng.
- 18 đoạn không phải 18 thí nghiệm độc lập; giới hạn độc lập là 8 boot.
- Năm cửa sổ S2 nằm trong cùng một phiên vật lý.
- Không có kết quả dự báo, EWT, AIW, hiệu ứng A/B, CI hay p-value thật.
- Không có người thứ hai tái lập độc lập (`INDEPENDENT_TEAM_MEMBER_REPLAY = PENDING`).
- Không có buổi tổng duyệt thực tế (`LIVE_TEAM_REHEARSAL = PENDING`).
- Các giá trị thiếu không được thay bằng 0 hoặc bằng số liệu tổng hợp.

## 4. Bản đồ bằng chứng

| Tuyên bố | Bằng chứng | Lớp | Kết luận được phép | Kết luận bị cấm |
|---|---|---|---|---|
| Hệ thống đã ghi được nhiễu cửa thật | `source-inventory.json`, 12 biểu đồ | `PHYSICAL_RECORDED_DATA` | Đã ghi nhận trạng thái cửa và nhiệt độ | AI dự báo chính xác sự cố nhiệt |
| Có mô hình XGBoost | `W15/model/model.ubj`, model card | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | Pipeline huấn luyện/suy luận tồn tại | Mô hình được duyệt cho Controller B |
| Có phương pháp thống kê cặp | W22 engine và test | `SOFTWARE_VERIFICATION` | Có thể tính toán khi có dữ liệu cặp hợp lệ | Controller B đã chứng minh lợi ích vật lý |
| Dữ liệu vật lý đã được phục hồi | `recovery-manifest.json`, CSV, 12 SVG | `PHYSICAL_RECORDED_DATA` | Có bảng mô tả và biểu đồ thật | Đã có kết quả dự báo vật lý |
| W16 đã sẵn sàng | `locked-test-result.md` | `SOFTWARE_VERIFICATION` | Quy trình từ chối đúng | Bài kiểm tra khóa đã hoàn thành |
| Phần mềm tái lập được | W23/W24 runbook và receipt | `SOFTWARE_VERIFICATION` | Người khác có thể chạy lại | Một người khác đã thực sự chạy lại |

## 5. Câu kết luận nên dùng

“Nhóm đã thu được dữ liệu vật lý thật và xử lý được một tập mô tả có giới hạn:
nền S1, 5 cửa sổ S2 (4 mở cửa + 1 định thời), các bước làm lạnh H8-C/H8-E/W07 và
chẩn đoán W21 có giới hạn. Nhóm **chưa** chứng minh được mô hình dự báo vật lý:
Gate B vẫn đỏ, chưa có nhãn tới hạn và chưa có thời gian sự kiện tuyệt đối. Vì
vậy báo cáo chỉ trình bày mô tả vật lý và prototype phần mềm, không tuyên bố hiệu
năng dự báo.”
