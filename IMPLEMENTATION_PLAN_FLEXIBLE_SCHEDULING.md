# Kế hoạch triển khai mở rộng hệ thống xếp lịch linh hoạt

## 1) Mục tiêu

Giữ nguyên toàn bộ luồng hoạt động hiện tại để không ảnh hưởng các client đang dùng ổn định, đồng thời mở rộng hệ thống theo hướng:

- Thêm các endpoint mới cho từng loại nhu cầu xếp lịch khác nhau.
- Cho phép mỗi endpoint mới nhận một kiểu yêu cầu riêng, có thể tùy biến ràng buộc và tham số thuật toán.
- Bên server chỉ cần tiếp nhận yêu cầu đã được chuẩn hóa, ánh xạ về một mô hình nội bộ chung, chạy thuật toán NSGA-II hiện có, rồi trả kết quả theo đúng định dạng đầu ra mà từng bên mong muốn.
- Giữ khả năng tương thích ngược với API hiện tại.

## 2) Ý tưởng cốt lõi

Kiến trúc nên được tách thành 4 lớp rõ ràng:

1. **Lớp API theo use case**
   - Mỗi nhóm bài toán xếp lịch có một endpoint riêng.
   - Endpoint chỉ làm nhiệm vụ nhận request, xác thực cơ bản, và gọi lớp chuyển đổi.

2. **Lớp chuẩn hóa nội bộ**
   - Chuyển mọi request khác nhau về một schema nội bộ chung.
   - Schema này chứa dữ liệu nghiệp vụ, ràng buộc, cấu hình optimizer, profile, và metadata.

3. **Lớp thuật toán lõi**
   - Giữ nguyên NSGA-II và các service hiện tại.
   - Nhận schema nội bộ chung, không phụ thuộc từng endpoint ngoài.

4. **Lớp adapter response**
   - Chuyển kết quả nội bộ thành đúng format đầu ra theo từng endpoint hoặc từng khách hàng.
   - Có thể hỗ trợ nhiều kiểu response khác nhau mà không sửa thuật toán.

## 3) Định hướng kiến trúc đề xuất

### 3.1 Giữ nguyên luồng hiện tại

Luồng hiện tại vẫn nên giữ như sau:

- `POST /api/v1/schedules/run`
- Payload hiện tại vẫn được chấp nhận như cũ.
- Job được đưa vào queue.
- Worker lấy job và chạy thuật toán.
- Kết quả trả về theo format hiện hành.

Điều này đảm bảo:

- Không làm gián đoạn hệ thống đang chạy.
- Không bắt buộc các client cũ phải thay đổi ngay.
- Có thể triển khai song song luồng mới.

### 3.2 Thêm endpoint mới theo loại lịch

Nên bổ sung thêm các endpoint theo mục đích sử dụng, ví dụ:

- `POST /api/v1/schedules/run` → giữ nguyên, cho luồng legacy.
- `POST /api/v1/schedules/run/general`
- `POST /api/v1/schedules/run/department`
- `POST /api/v1/schedules/run/custom`
- `POST /api/v1/schedules/run/{schedule_type}`

Hoặc theo profile:

- `POST /api/v1/schedules/run?profile_id=hospital_a_day_shift`
- `POST /api/v1/schedules/run` với body chứa `profile_id`.

Mỗi endpoint mới nên có nhiệm vụ:

- Nhận loại lịch cần xếp.
- Nhận các tham số ràng buộc tương ứng.
- Xác thực theo từng loại request.
- Chuẩn hóa về request nội bộ chung.
- Gọi chung một pipeline xử lý.

## 4) Mô hình request đề xuất

### 4.1 Request ngoài API

Request bên ngoài nên có 3 nhóm thông tin:

- **Thông tin nghiệp vụ**
  - Danh sách bác sĩ hoặc nguồn lực.
  - Phạm vi ngày.
  - Số phòng/ca/nhu cầu nhân sự.

- **Loại lịch / profile**
  - `schedule_type`
  - `profile_id`
  - `tenant_id` hoặc `department_id`

- **Override cấu hình**
  - `optimizer_population_size`
  - `optimizer_generations`
  - `random_seed`
  - `randomization_strength`
  - giới hạn ràng buộc bổ sung
  - trọng số objective

### 4.2 Schema nội bộ chung

Nên chuẩn hóa mọi request thành một DTO nội bộ kiểu như:

- `SchedulingJobRequestDTO`
  - `request_id`
  - `schedule_type`
  - `profile_id`
  - `tenant_id`
  - `input_payload`
  - `business_constraints`
  - `optimizer_config`
  - `response_profile`
  - `metadata`

Lợi ích:

- Thuật toán chỉ làm việc với một schema.
- Endpoint mới hay cũ đều dùng chung pipeline.
- Dễ log, debug, và version hóa.

## 5) Cơ chế cấu hình linh hoạt

### 5.1 Thứ tự ưu tiên cấu hình

Khuyến nghị áp dụng thứ tự ưu tiên sau:

1. Override từ request.
2. Cấu hình theo profile.
3. Cấu hình mặc định của server.

Ví dụ:

- Nếu request truyền `optimizer_generations`, dùng giá trị đó.
- Nếu không có, lấy từ profile.
- Nếu profile cũng không có, dùng `AppSettings`.

### 5.2 Profile theo use case

Mỗi profile nên mô tả:

- Ràng buộc nghiệp vụ mặc định.
- Bộ tham số thuật toán.
- Chỉ số ưu tiên objective.
- Định dạng output mong muốn.
- Version của rule.

Ví dụ profile:

- `hospital_general_day_shift`
- `clinic_low_staff`
- `department_custom_fairness`
- `night_shift_priority`

### 5.3 Version hóa profile

Nên có:

- `profile_id`
- `profile_version`
- `rule_version`
- `created_at`
- `updated_at`

Mục đích:

- Chạy lại được job cũ theo đúng rule cũ.
- Tránh việc thay đổi cấu hình hiện tại làm sai lịch đã sinh trước đó.

## 6) Cách map vào thuật toán hiện có

### 6.1 Không sửa lõi thuật toán theo từng endpoint

Không nên để mỗi endpoint tự gọi solver theo cách riêng. Thay vào đó:

- Endpoint → request adapter → internal request DTO → use case chung → scheduler service.

### 6.2 Mở rộng lớp use case

Use case nên nhận:

- request chuẩn hóa nội bộ
- profile resolved
- config resolved
- callback progress

Sau đó mới truyền xuống `NsgaDutySchedulerService`.

### 6.3 Giữ thuật toán độc lập với API

Phần trong `NSGA2IS-SLS/server/app/domain/nsga_scheduler.py` nên tiếp tục giữ vai trò:

- validate hard constraints
- khởi tạo problem
- chạy NSGA-II
- trích Pareto front
- dựng metrics và assignments

Không để logic endpoint lọt vào đây.

## 7) Cách trả kết quả theo format mong muốn

### 7.1 Adapter response

Nên thêm lớp chuyển đổi kết quả:

- Internal envelope → response format A
- Internal envelope → response format B
- Internal envelope → response format C

Ví dụ:

- một bên muốn trả schedule + metrics tách riêng
- một bên chỉ cần lịch cuối cùng
- một bên cần cả Pareto options
- một bên muốn format JSON khác theo hệ thống của họ

### 7.2 Response profile

Có thể gắn thêm `response_profile` để xác định:

- chỉ trả lịch đã chọn
- trả cả Pareto options
- trả metrics chi tiết
- trả format rút gọn cho client nhẹ

## 8) Luồng xử lý end-to-end đề xuất

### 8.1 Luồng đồng bộ

1. Client gọi endpoint mới.
2. API validate sơ bộ request.
3. API resolve profile và merge override.
4. API chuẩn hóa request thành internal DTO.
5. API gọi use case chung.
6. Scheduler chạy NSGA-II.
7. Response adapter build output theo profile.
8. API trả kết quả.

### 8.2 Luồng bất đồng bộ

1. Client gọi endpoint mới.
2. API validate sơ bộ.
3. API resolve profile và merge override.
4. API lưu snapshot config vào job payload.
5. API đẩy job vào queue.
6. Worker lấy job.
7. Worker dựng internal DTO từ snapshot.
8. Worker gọi use case chung.
9. Worker lưu kết quả.
10. API status/result endpoint trả theo response profile.

## 9) Các endpoint nên có

### 9.1 Endpoint hiện tại

- Giữ nguyên `POST /api/v1/schedules/run`
- Không đổi hành vi cũ.

### 9.2 Endpoint mới cho profile

- `POST /api/v1/schedule-profiles`
- `GET /api/v1/schedule-profiles/{profile_id}`
- `PATCH /api/v1/schedule-profiles/{profile_id}`
- `GET /api/v1/schedule-profiles`

### 9.3 Endpoint mới cho chạy lịch

- `POST /api/v1/schedules/run/{schedule_type}`
- `POST /api/v1/schedules/run/profile/{profile_id}`
- `POST /api/v1/schedules/run/custom`

### 9.4 Endpoint kết quả

- `GET /api/v1/jobs/{request_id}`
- `GET /api/v1/jobs/{request_id}/schedule`
- `GET /api/v1/jobs/{request_id}/metrics`

## 10) Gợi ý cấu trúc DTO

### 10.1 DTO request ngoài

- `ScheduleRequestBaseDTO`
- `ScheduleTypeRequestDTO`
- `ProfileBasedScheduleRequestDTO`
- `CustomScheduleRequestDTO`

### 10.2 DTO nội bộ

- `SchedulingJobRequestDTO`
- `SchedulingResolvedConfigDTO`
- `SchedulingResponseProfileDTO`
- `SchedulingExecutionContextDTO`

### 10.3 DTO response

- `AcceptedJobDTO`
- `JobStatusDTO`
- `ScheduleResultDTO`
- `ScheduleMetricsDTO`
- `ScheduleParetoDTO`

## 11) Các điểm cần lưu ý khi triển khai

### 11.1 Tương thích ngược

- Tuyệt đối không đổi schema bắt buộc của endpoint cũ nếu chưa có migration plan.
- Các field mới nên optional.
- Nếu endpoint mới bị lỗi, endpoint cũ vẫn phải hoạt động bình thường.

### 11.2 Snapshot cấu hình khi enqueue job

- Không chỉ lưu `profile_id`, nên lưu cả config đã merge cuối cùng.
- Điều này giúp job chạy lại không phụ thuộc vào config thay đổi sau đó.

### 11.3 Validation phân tầng

- Validate nhẹ ở API layer.
- Validate nghiệp vụ ở layer chuẩn hóa.
- Validate hard constraints ở domain layer.

### 11.4 Giới hạn độ phức tạp

- Không nên cho request tự do quá mức nếu chưa có kiểm soát.
- Nên giới hạn những tham số được override.
- Một số tham số nhạy cảm nên chỉ cho phép theo profile, không cho client ghi đè trực tiếp.

### 11.5 Logging và audit

- Log `schedule_type`, `profile_id`, `tenant_id`, `rule_version`.
- Log config snapshot đã dùng.
- Log reason nếu request bị reject.

## 12) Phân loại cái gì nên cho phép tùy biến

### 12.1 Nên cho tùy biến

- loại lịch
- số ngày
- số phòng
- số bác sĩ/ca
- giới hạn giờ làm
- số ngày nghỉ tối đa
- population size
- generations
- random seed
- randomization strength
- số phương án Pareto trả ra

### 12.2 Nên giới hạn hoặc khóa theo profile

- các hard constraints quan trọng
- các rule an toàn nghiệp vụ
- giới hạn tối đa/quá thấp ảnh hưởng chất lượng lịch
- logic xác thực nội bộ của từng cơ sở

## 13) Kế hoạch triển khai thực tế

### Phase 1: Chuẩn hóa nền tảng

- Giữ nguyên endpoint cũ.
- Tạo internal request DTO chung.
- Tách lớp resolve config từ request/profile/default.
- Tách lớp response adapter.

### Phase 2: Thêm endpoint mới

- Thêm endpoint theo `schedule_type` hoặc `profile_id`.
- Hỗ trợ payload tùy biến nhưng vẫn kiểm soát.
- Đảm bảo route mới gọi chung pipeline xử lý.

### Phase 3: Profile registry

- Lưu profile trong DB hoặc file versioned.
- Có API quản lý profile.
- Cho phép import/export profile.

### Phase 4: Async snapshot

- Job queue lưu snapshot cấu hình.
- Worker chỉ đọc snapshot, không phụ thuộc config runtime.
- Bổ sung metrics và audit.

### Phase 5: Mở rộng response format

- Thêm response profile.
- Cho phép trả nhiều định dạng theo từng khách hàng.

## 14) Ưu điểm của cách này

- Không phá hệ thống cũ.
- Dễ mở rộng cho nhiều loại lịch.
- Dễ bảo trì và version hóa.
- Tách rõ nghiệp vụ, cấu hình và thuật toán.
- Phù hợp mô hình serverless và asynchronous job processing.

## 15) Rủi ro cần tránh

- Endpoint mới quá nhiều nhưng không có internal core dùng chung.
- Cho client override quá nhiều tham số nhạy cảm.
- Không snapshot config khi chạy async.
- Trả response theo từng nơi mà không có adapter chuẩn.
- Không version hóa profile/rule.

## 16) Kết luận

Cách triển khai phù hợp nhất là:

- **Giữ nguyên luồng hiện tại** cho sự ổn định.
- **Tách thêm endpoint mới** cho các loại nhu cầu xếp lịch khác nhau.
- **Chuẩn hóa mọi request** về một schema nội bộ chung.
- **Dùng một thuật toán lõi duy nhất** để xử lý.
- **Dùng adapter response** để trả đúng format từng bên muốn.
- **Lưu snapshot cấu hình** để đảm bảo job async luôn tái hiện đúng kết quả.

Đây là hướng mở rộng an toàn, có tính lâu dài, và phù hợp nhất nếu mục tiêu của bạn là “một serverless thuật toán, nhiều loại bài toán xếp lịch, nhiều định dạng đầu ra khác nhau”.
