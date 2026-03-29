# Báo cáo triển khai hệ thống xếp lịch linh hoạt

## 1. Mục tiêu đã thực hiện

Đã triển khai một lớp mở rộng cho hệ thống xếp lịch theo hướng:

- Giữ nguyên đầy đủ luồng legacy hiện có để không ảnh hưởng client đang dùng.
- Thêm các endpoint mới theo schedule type và profile.
- Chuẩn hóa request ngoài API về một schema nội bộ chung.
- Dùng chung một pipeline xử lý cho legacy, general, department và custom.
- Thêm lớp profile registry và response detail để hỗ trợ mở rộng về sau.
- Cho worker xử lý được cả legacy payload lẫn normalized job snapshot.

---

## 2. Phần đã hoàn thiện

### 2.1 DTO và schema nội bộ

Đã mở rộng [server/app/domain/schemas.py](server/app/domain/schemas.py) với các nhóm model sau:

- Request legacy được mở rộng trường tùy chọn:
  - `schedule_type`
  - `profile_id`
  - `tenant_id`
  - `department_id`
  - `response_profile`
  - `optimizer_population_size`
  - `optimizer_generations`
  - `random_seed`
  - `randomization_strength`
  - `pareto_options_limit`
  - `business_constraints`
  - `metadata`

- DTO nội bộ mới:
  - `SchedulingOptimizerConfigDTO`
  - `SchedulingProfileDTO`
  - `ScheduleProfileUpdateDTO`
  - `SchedulingResolvedConfigDTO`
  - `SchedulingJobRequestDTO`
  - `SchedulingExecutionContextDTO`
  - `ScheduleJobDetailDTO`

- Response accepted đã được mở rộng thêm metadata điều hướng:
  - `schedule_type`
  - `profile_id`
  - `response_profile`

Kết quả: hệ thống đã có một hợp đồng dữ liệu đủ để hỗ trợ nhiều kiểu input khác nhau nhưng vẫn giữ tương thích ngược.

### 2.2 Profile registry

Đã thêm file [server/app/application/services/scheduling_profile_registry.py](server/app/application/services/scheduling_profile_registry.py) để quản lý profile theo kiểu file-backed, bao gồm:

- Profile mặc định:
  - `legacy`
  - `hospital_general_day_shift`
  - `department_custom_fairness`
  - `night_shift_priority`

- Chức năng:
  - `list_profiles()`
  - `get_profile(profile_id)`
  - `resolve_profile(profile_id, schedule_type)`
  - `upsert_profile(profile)`
  - `update_profile(profile_id, patch)`

- Có hỗ trợ:
  - `allowed_override_fields`
  - `locked_fields`
  - `profile_version`
  - `rule_version`
  - `metadata`

Kết quả: profile có thể được quản lý mở rộng theo từng use case mà không phải sửa lõi thuật toán.

### 2.3 Request normalization / adapter layer

Đã thêm file [server/app/application/services/scheduling_request_adapter.py](server/app/application/services/scheduling_request_adapter.py) để thực hiện chuẩn hóa request:

- `resolve_scheduling_job_request()`
  - merge request override
  - merge profile default
  - merge server default
  - sinh `SchedulingJobRequestDTO`

- `resolve_generation_request()`
  - chuyển legacy request hoặc normalized snapshot về `ScheduleGenerationRequestDTO`
  - dùng trực tiếp cho use case và worker

- Cơ chế ưu tiên:
  1. override từ request
  2. profile
  3. config mặc định của server

- Có chặn override theo profile:
  - field bị khóa sẽ không bị ghi đè
  - field không nằm trong allow-list cũng không bị ghi đè

Kết quả: toàn bộ request đi vào hệ thống đều được chuẩn hóa trước khi chạy thuật toán.

### 2.4 Use case chung

Đã cập nhật [server/app/application/use_cases/generate_schedule.py](server/app/application/use_cases/generate_schedule.py):

- Use case `GenerateScheduleUseCase` giờ nhận được:
  - `ScheduleRunRequestDTO`
  - hoặc `SchedulingJobRequestDTO`

- Tầng use case không còn tự ghép config cứng nữa, mà đi qua adapter chuẩn hóa.

Kết quả: use case trở thành một điểm vào chung cho cả legacy và luồng mới.

### 2.5 API routes mới

Đã mở rộng [server/app/api/v1/scheduling.py](server/app/api/v1/scheduling.py) và [server/app/api/router.py](server/app/api/router.py) với các route:

- Legacy giữ nguyên:
  - `POST /api/v1/schedules/run`

- Run theo type/profile/custom:
  - `POST /api/v1/schedules/run/{schedule_type}`
  - `POST /api/v1/schedules/run/profile/{profile_id}`
  - `POST /api/v1/schedules/run/custom`

- Job result mới:
  - `GET /api/v1/jobs/{request_id}`
  - `GET /api/v1/jobs/{request_id}/schedule`
  - `GET /api/v1/jobs/{request_id}/metrics`

- Profile management:
  - `GET /api/v1/schedule-profiles`
  - `GET /api/v1/schedule-profiles/{profile_id}`
  - `POST /api/v1/schedule-profiles`
  - `PATCH /api/v1/schedule-profiles/{profile_id}`

- Đã giữ cơ chế API key như cũ.

Kết quả: endpoint cũ vẫn chạy, endpoint mới đã sẵn sàng để mở rộng từng use case.

### 2.6 Response adapter

Đã cập nhật [server/app/application/services/schedule_view_builder.py](server/app/application/services/schedule_view_builder.py):

- Giữ nguyên builder cũ:
  - `build_schedule_response()`
  - `build_metrics_response()`

- Thêm builder mới:
  - `build_job_detail_response()`

Kết quả: job detail có thể trả cả progress lẫn envelope nếu job đã hoàn tất.

### 2.7 Worker

Đã cập nhật [server/app/worker.py](server/app/worker.py) để:

- Nhận job legacy như cũ.
- Nhận normalized snapshot mới có các trường:
  - `business_request`
  - `resolved_profile`
  - `resolved_config`

- Parse được:
  - `ScheduleRunRequestDTO`
  - hoặc `SchedulingJobRequestDTO`

Kết quả: worker tương thích với luồng cũ và luồng enqueue snapshot mới.

---

## 3. Kiểm tra đã thực hiện

### 3.1 Kiểm tra lỗi cú pháp

Đã chạy kiểm tra lỗi trên toàn bộ `server/app` và không còn lỗi.

### 3.2 Kiểm tra import / resolve thực tế

Đã chạy code snippet Python trong môi trường workspace để xác thực:

- `resolve_scheduling_job_request()` hoạt động đúng.
- Profile mặc định được resolve chuẩn.
- Override hợp lệ được merge đúng.
- Các giá trị bị khóa / giới hạn được áp dụng theo profile và DTO.

### 3.3 Kết quả xác thực

- Input legacy bình thường: resolve về profile `legacy`.
- Input theo `schedule_type='department'`: resolve về profile `department_custom_fairness`.
- Override hợp lệ được giữ.
- Override vượt giới hạn DTO bị chặn từ sớm.

---

## 4. Tương thích ngược

Đã giữ nguyên các điểm sau:

- Endpoint legacy `POST /api/v1/schedules/run`.
- Cơ chế queue và worker hiện tại.
- Output lịch/chỉ số hiện hành qua các endpoint cũ.
- API key guard.
- Luồng xử lý NSGA-II lõi trong domain.

Điều này giúp client cũ không phải thay đổi ngay.

---

## 5. Phạm vi mới đã mở rộng

Hệ thống hiện tại đã hỗ trợ:

- Nhiều loại schedule request.
- Profile-based configuration.
- Snapshot cấu hình khi enqueue.
- Job detail endpoint.
- Profile registry CRUD cơ bản.
- Response detail ở mức job.

---

## 6. Phần còn mở / có thể làm tiếp

Các phần dưới đây chưa triển khai hoàn toàn ở mức production-grade, nhưng nền tảng đã có sẵn:

### 6.1 Profile registry production backend

Hiện registry đang dùng file local `.scheduling_profiles.json`.
Có thể nâng cấp sang:

- DynamoDB
- S3
- PostgreSQL
- Parameter Store / AppConfig

### 6.2 Version hóa profile đầy đủ

Hiện đã có các field:

- `profile_version`
- `rule_version`

Nhưng chưa có migration hoặc audit trail hoàn chỉnh.

### 6.3 Response profile nâng cao

Đã có khung `response_profile`, nhưng chưa tách adapter output thành nhiều format khác nhau theo từng khách hàng.

### 6.4 Validation nghiệp vụ theo profile

Hiện mới dừng ở:

- validate DTO
- validate feasibility cơ bản
- hard constraints ở domain

Có thể bổ sung validation sâu hơn theo từng profile/tenant/department.

### 6.5 Lưu snapshot job vào storage riêng

Hiện job snapshot chủ yếu đi qua queue payload và worker xử lý trực tiếp.
Có thể tăng độ bền bằng cách lưu snapshot vào DynamoDB hoặc S3 trước khi chạy.

---

## 7. Kết luận

Phần đã triển khai đáp ứng đúng mục tiêu chính:

- không phá legacy,
- thêm endpoint mới,
- chuẩn hóa request chung,
- dùng chung một pipeline lõi,
- hỗ trợ profile,
- hỗ trợ worker snapshot,
- và kiểm tra lỗi đã ổn định.

Nói ngắn gọn, nền tảng mở rộng cho hệ thống xếp lịch linh hoạt đã được dựng xong, và hiện có thể tiếp tục nâng cấp theo hướng production hóa profile storage và response adapter.
