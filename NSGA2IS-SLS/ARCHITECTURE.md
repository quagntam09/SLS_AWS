# Kiến Trúc Hệ Thống NSGA2IS-SLS

Tài liệu này mô tả kiến trúc hiện tại của dự án, cách các thành phần phối hợp với nhau, và cách hệ thống được triển khai trên AWS theo cấu hình đang có trong repository.

## 1. Mục tiêu hệ thống

NSGA2IS-SLS là hệ thống sinh lịch trực bác sĩ bằng thuật toán NSGA-II cải tiến. Hệ thống nhận một yêu cầu lập lịch, đưa vào hàng đợi xử lý, chạy tối ưu trong worker riêng, lưu kết quả, và cung cấp API để theo dõi tiến độ cũng như lấy lịch hoàn chỉnh sau khi job kết thúc.

Thiết kế hiện tại đi theo mô hình bất đồng bộ để tách:

- tầng nhận request HTTP
- tầng xử lý nặng bằng thuật toán tối ưu
- tầng lưu trữ trạng thái và kết quả

Mục tiêu chính của mô hình này là tránh giữ request HTTP quá lâu và phù hợp với giới hạn thời gian của API Gateway / Lambda.

## 2. Tổng quan kiến trúc

Hệ thống hiện tại gồm 4 khối chính:

- API FastAPI chạy trong AWS Lambda qua Mangum
- Worker Lambda xử lý message từ SQS
- DynamoDB lưu trạng thái job và tiến độ
- S3 lưu payload kết quả hoàn chỉnh

Ngoài ra, Serverless Framework dùng để khai báo hạ tầng, IAM permissions, biến môi trường và các resource AWS.

```mermaid
flowchart LR
    Client[Frontend / Client] -->|POST /api/v1/schedules/run| API[FastAPI on Lambda]
    API -->|put_item| DDB[(DynamoDB)]
    API -->|send_message| SQS[(SQS Queue)]
    SQS -->|trigger| Worker[Worker Lambda]
    Worker -->|update progress| DDB
    Worker -->|put_object result| S3[(S3 Bucket)]
    Worker -->|mark completed| DDB
    Client -->|GET /progress/{request_id}| API
    Client -->|GET /jobs/{request_id}/schedule| API
    Client -->|GET /jobs/{request_id}/metrics| API
    API -->|get_item / get_object| DDB
    API -->|get_object| S3
```

## 3. Cấu trúc thư mục liên quan đến kiến trúc

Các thư mục chính đang tham gia vào hệ thống:

- `server/app/main.py`: khởi tạo FastAPI app, CORS, health check, Mangum handler
- `server/app/api/`: router HTTP
- `server/app/application/`: use case và service layer
- `server/app/domain/`: schema DTO và service tối ưu
- `server/app/worker.py`: Lambda worker xử lý SQS event
- `server/nsga2_improved/`: engine NSGA-II cải tiến
- `serverless.yml`: khai báo hạ tầng AWS và runtime

Hệ thống có cơ chế batching cho progress update. Worker chỉ ghi tiến độ xuống DynamoDB theo chu kỳ được cấu hình bởi `APP_PROGRESS_UPDATE_INTERVAL` và luôn ghi ở thế hệ cuối cùng để đảm bảo job kết thúc có trạng thái `100%`.

## 4. Các thành phần chính

### 4.1 API service

Điểm vào HTTP của hệ thống là `server/app/main.py`.

Chức năng của module này:

- tạo FastAPI application
- cấu hình CORS
- đăng ký router `/api/v1`
- expose health check `/health`
- tạo `handler = Mangum(app)` để chạy trên AWS Lambda

API hiện có các endpoint chính:

- `POST /api/v1/schedules/run`
- `GET /api/v1/schedules/progress/{request_id}`
- `GET /api/v1/schedules/jobs/{request_id}/schedule`
- `GET /api/v1/schedules/jobs/{request_id}/metrics`
- `GET /health`

### 4.2 Application layer

Tầng ứng dụng gồm hai nhóm logic:

- use case: `GenerateScheduleUseCase`
- service hạ tầng: `async_schedule_service.py`, `schedule_view_builder.py`

`GenerateScheduleUseCase` chuyển request API thành request tối ưu nội bộ, lấy cấu hình từ environment, rồi gọi domain service để sinh lịch.

`async_schedule_service.py` chịu trách nhiệm làm việc với AWS:

- tạo request id
- ghi trạng thái job vào DynamoDB
- đẩy message vào SQS
- cập nhật tiến độ job
- lưu kết quả vào S3
- đọc lại tiến độ và kết quả đã lưu

`schedule_view_builder.py` chuyển dữ liệu envelope nội bộ thành DTO phục vụ response API.

### 4.3 Domain layer

Tầng domain hiện có hai phần quan trọng:

- `schemas.py`: tất cả DTO dùng cho API và kết quả tối ưu
- `nsga_scheduler.py`: service tối ưu lịch

`schemas.py` định nghĩa:

- hồ sơ bác sĩ
- payload request
- kết quả lịch
- metrics thuật toán
- DTO cho progress / schedule / metrics response

`nsga_scheduler.py` là lõi nghiệp vụ:

- kiểm tra hard constraints
- tạo bài toán tối ưu
- decode vector ứng viên thành lịch
- sửa vi phạm hard constraints phát sinh trong quá trình tiến hóa
- tính soft penalties và fairness metrics
- chạy NSGA-II cải tiến
- dựng envelope kết quả gồm lịch được chọn và các phương án Pareto

### 4.4 Worker Lambda

`server/app/worker.py` là entrypoint của Lambda được kích hoạt bởi SQS.

Luồng xử lý của worker:

- nhận message từ queue
- parse `request_id` và payload
- validate lại `ScheduleRunRequestDTO`
- gọi `mark_running(...)`
- chạy `GenerateScheduleUseCase().execute(...)`
- cập nhật progress theo chu kỳ modulo `APP_PROGRESS_UPDATE_INTERVAL` trong quá trình tiến hóa
- luôn ghi progress `100%` ở thế hệ cuối cùng
- lưu kết quả bằng `mark_completed(...)`
- nếu lỗi, gọi `mark_failed(...)`

Worker được thiết kế tách biệt khỏi API để không chặn request HTTP khi tối ưu chạy lâu.

### 4.5 NSGA-II engine

Thư mục `server/nsga2_improved/` chứa implementation thuật toán:

- `core.py`: wrapper và model cá thể
- `operators.py`: initialization, mutation, crossover, OBL
- `selection.py`: non-dominated sorting và crowding distance
- `algorithm.py`: vòng lặp tiến hóa chính

Engine này được đóng gói như một module nội bộ, và domain service dùng nó để chạy tối ưu.

## 5. Luồng xử lý request

### 5.1 Submit job

Khi client gọi `POST /api/v1/schedules/run`:

1. FastAPI validate `ScheduleRunRequestDTO`
2. `run_schedule()` dựng request tối ưu nội bộ từ payload
3. `_validate_hard_constraints()` kiểm tra tính khả thi ở mức nghiệp vụ
4. `create_schedule_request()` tạo `request_id`
5. request được ghi vào DynamoDB với trạng thái `queued`
6. payload được gửi vào SQS
7. API trả ngay `request_id`, `status=queued`

Điểm quan trọng: API không chạy thuật toán trực tiếp. Tất cả phần nặng được đẩy sang worker.

### 5.2 Worker xử lý job

Khi SQS trigger Lambda worker:

1. worker đọc message
2. worker validate lại payload
3. worker gọi `mark_running()` để cập nhật trạng thái `running`
4. worker chạy NSGA-II qua `GenerateScheduleUseCase`
5. trong quá trình chạy, worker cập nhật progress theo thế hệ
6. khi xong, worker serializes result sang JSON
7. `mark_completed()` lưu result vào S3 và cập nhật DynamoDB sang `completed`

### 5.3 Theo dõi tiến độ

Khi client gọi `GET /api/v1/schedules/progress/{request_id}`:

1. API đọc item từ DynamoDB
2. nếu job `completed`, API trả thông tin trạng thái và progress
3. nếu không tồn tại, trả `404`
4. nếu job failed, progress vẫn có thể trả trạng thái `failed` và message lỗi

### 5.4 Lấy lịch hoàn chỉnh

Khi client gọi `GET /api/v1/schedules/jobs/{request_id}/schedule`:

1. API kiểm tra job có tồn tại
2. API chỉ chấp nhận job đã `completed`
3. API đọc result từ S3 qua key đã lưu trong DynamoDB
4. result được map thành `ScheduleJobScheduleResponseDTO`

Tương tự, `GET /api/v1/schedules/jobs/{request_id}/metrics` chỉ trả metrics khi job đã hoàn tất.

## 6. Deployment hiện tại trên AWS

File triển khai chính là `serverless.yml`.

### 6.1 Runtime

- AWS Lambda runtime: `python3.12`
- API timeout: `30s`
- Worker timeout: `900s`
- Worker memory: `1024MB`

### 6.2 Functions

Có hai Lambda function:

- `api`: phục vụ HTTP API
- `worker`: xử lý SQS events

### 6.3 AWS resources

Serverless tạo các resource sau:

- `ScheduleJobsQueue`: SQS queue để queue job sinh lịch
- `ScheduleRequestsTable`: DynamoDB table lưu trạng thái job
- `ScheduleResultsBucket`: S3 bucket lưu JSON kết quả

### 6.4 IAM permissions

Lambda role được cấp quyền:

- `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes`
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`
- `s3:PutObject`, `GetObject`

Đây là quyền tối thiểu để triển khai luồng submit -> queue -> worker -> lưu kết quả.

### 6.5 Biến môi trường runtime

Các biến quan trọng đang được inject qua `serverless.yml`:

- `PYTHONPATH=/var/task:/var/task/server`
- `APP_ENV`
- `APP_OPTIMIZER_POPULATION_SIZE`
- `APP_OPTIMIZER_GENERATIONS`
- `APP_PARETO_OPTIONS_LIMIT`
- `APP_RANDOMIZATION_STRENGTH`
- `APP_RANDOM_SEED`
- `APP_CORS_ALLOW_ORIGINS`
- `APP_PROGRESS_UPDATE_INTERVAL`
- `SCHEDULE_QUEUE_URL`
- `SCHEDULE_TABLE_NAME`
- `SCHEDULE_RESULTS_BUCKET`

`APP_*` được đọc bởi `server/app/config.py`.
`SCHEDULE_*` được dùng trong `async_schedule_service.py`.
`APP_PROGRESS_UPDATE_INTERVAL` quyết định tần suất worker ghi progress xuống DynamoDB để giảm số lần `UpdateItem`.

## 7. Cấu hình ứng dụng

Cấu hình tập trung ở `server/app/config.py`.

Các giá trị chính:

- `optimizer_population_size`
- `optimizer_generations`
- `pareto_options_limit`
- `randomization_strength`
- `random_seed`
- `cors_allow_origins`
- `env`

`get_settings()` dùng cache 1 lần để tránh khởi tạo lại settings nhiều lần.

### 7.1 CORS

CORS được cấu hình từ `APP_CORS_ALLOW_ORIGINS`, tách bằng dấu phẩy.

Hiện tại default đang là localhost, nên khi deploy production cần set rõ origin thật của frontend.

### 7.2 .env local

README hiện cho phép chạy local bằng `.env`. Các biến `APP_*` có thể khai báo tại đó. Nếu muốn test API async local đúng nghĩa, cần thêm cả `SCHEDULE_*` hoặc mock lớp hạ tầng AWS.

## 8. Mô hình dữ liệu và lưu trữ

### 8.1 DynamoDB

Mỗi job có một item keyed theo `request_id`.

Trạng thái job thường đi qua các pha:

- `queued`
- `running`
- `completed`
- `failed`

Các thuộc tính thường có:

- `progress_percent`
- `message`
- `error`
- `result_s3_key`
- `created_at`
- `updated_at`

### 8.2 S3

Kết quả hoàn chỉnh được lưu dưới key:

- `results/{request_id}.json`

Dữ liệu trong file JSON là payload DTO hóa từ envelope kết quả của scheduler.

### 8.3 SQS

SQS dùng để decouple API submit và worker chạy tối ưu.

Message body chứa:

- `request_id`
- `payload`

## 9. DTO và response model

`server/app/domain/schemas.py` là nguồn chuẩn cho response shape.

Các nhóm chính:

- `ScheduleRunRequestDTO`: payload submit job
- `ScheduleRequestAcceptedDTO`: response khi queue job thành công
- `ScheduleJobStatusDTO`: progress status
- `ScheduleJobScheduleResponseDTO`: lịch hoàn chỉnh
- `ScheduleJobMetricsResponseDTO`: metrics hoàn chỉnh
- `ScheduleGenerationEnvelopeDTO`: kết quả nội bộ đầy đủ của thuật toán

Điểm đáng chú ý:

- `experiences` là `float`, không ép về `int`
- `doctors` phải unique theo `id`
- `days_off` không được trùng `preferred_extra_days`
- `shifts_per_day` hiện chỉ nhận `1` hoặc `2`

## 10. Luồng tối ưu trong domain

Lõi tối ưu ở `nsga_scheduler.py` đi theo các bước:

1. validate hard constraints
2. build metadata của kỳ trực
3. tạo problem wrapper cho NSGA-II
4. run solver
5. lấy Pareto front
6. decode từng nghiệm thành lịch trực
7. tính metrics chất lượng và fairness
8. chọn nghiệm đầu tiên trong Pareto candidates làm lịch mặc định trả về

### 10.1 Hard constraints

Các ràng buộc cứng hiện tại gồm:

- đủ số bác sĩ cho mỗi ca
- giới hạn giờ làm/tuần
- số ngày nghỉ tối đa trong kỳ
- intern phải có supervisor
- license hợp lệ
- preferred days không được trùng day off
- số ca/ngày hợp lý
- số ngày lập lịch hợp lý

### 10.2 Soft constraints

Soft constraints được tối ưu bằng penalty:

- không làm quá nhiều ngày liên tiếp
- cân bằng giờ làm
- ưu tiên ngày đăng ký
- công bằng weekend
- tránh bác sĩ bị 0 ca nếu có thể
- cân bằng workload tổng thể
- cân bằng theo chuyên khoa
- cân bằng theo tháng

## 11. Local development và thực thi

### 11.1 Chạy API local

README hiện đề xuất:

```bash
uvicorn server.app.main:app --reload
```

Vì import trong code đang theo kiểu package dưới `server/`, môi trường local cần đảm bảo đường dẫn module tương ứng đã có trên `PYTHONPATH`.

### 11.2 Chạy worker local

Worker là Lambda entrypoint, nên local test thường cần mô phỏng event SQS hoặc gọi handler trực tiếp trong test harness.

### 11.3 Cài đặt phụ thuộc

`requirements.txt` gồm:

- FastAPI
- Mangum
- Pydantic v2
- Uvicorn
- NumPy
- SciPy
- boto3

`serverless-python-requirements` được dùng để đóng gói dependency cho Lambda.

## 12. Đặc tính vận hành hiện tại

### Ưu điểm

- API không bị chặn bởi bài toán tối ưu nặng
- trạng thái job lưu bền vững trên DynamoDB/S3
- worker tách riêng cho scale độc lập
- có thể theo dõi progress chi tiết theo generation

### Giới hạn hiện tại

- API và worker phụ thuộc chặt vào các biến môi trường AWS
- local dev cần cấu hình path/module cẩn thận
- `ScheduleJobManager` vẫn tồn tại nhưng không phải luồng deploy chính
- `shifts_per_day` hiện bị giới hạn ở `1` hoặc `2`
- thời gian chạy thực tế vẫn bị giới hạn bởi timeout Lambda / API Gateway

## 13. Kết luận

Kiến trúc hiện tại là một kiến trúc async serverless khá điển hình:

- HTTP API chỉ nhận request và trả `request_id`
- SQS làm hàng đợi
- worker Lambda xử lý tối ưu
- DynamoDB giữ trạng thái job
- S3 lưu kết quả cuối

Thiết kế này phù hợp với workload tối ưu lịch dài, nhưng đòi hỏi cấu hình môi trường và packaging nhất quán để chạy local và deploy AWS không bị lệch.

## 14. Tài liệu liên quan

- [README.md](README.md)
- [API.md](API.md)
- [serverless.yml](serverless.yml)
- [server/app/main.py](server/app/main.py)
- [server/app/worker.py](server/app/worker.py)
- [server/app/application/services/async_schedule_service.py](server/app/application/services/async_schedule_service.py)
- [server/app/domain/nsga_scheduler.py](server/app/domain/nsga_scheduler.py)
