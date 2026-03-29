# NSGA2IS-SLS

Hệ thống sinh lịch trực bác sĩ bằng NSGA-II cải tiến. API FastAPI nhận request, ghi trạng thái job vào DynamoDB, đẩy payload vào SQS, rồi trả `request_id` ngay. Worker là một process event-driven chạy cùng entrypoint `server.app.worker`, nhận payload từ orchestration bên ngoài, chạy tối ưu, ghi kết quả lên S3 và cập nhật tiến độ job.

## Tóm Tắt Nhanh

- `POST /api/v1/schedules/run` tạo job bất đồng bộ và trả `202 Accepted`.
- `GET /api/v1/schedules/progress/{request_id}` xem trạng thái job.
- `GET /api/v1/schedules/jobs/{request_id}/schedule` lấy lịch đã hoàn tất.
- `GET /api/v1/schedules/jobs/{request_id}/metrics` lấy metrics của lịch.
- `GET /health` kiểm tra trạng thái ứng dụng.

## Kiến Trúc Hiện Tại

- FastAPI chạy trên AWS Lambda qua Mangum.
- API không chạy thuật toán trực tiếp; nó chỉ validate request, ghi DynamoDB và publish message vào SQS.
- Worker nhận 1 job payload mỗi lần chạy, update `running/completed/failed`, rồi lưu kết quả JSON vào S3.
- DynamoDB lưu trạng thái job, tiến độ, message lỗi, và key trỏ tới kết quả.
- Fargate + EventBridge Pipes là đường chạy worker chuẩn trong repo.

- API mặc định chưa bật authentication/authorization; nếu mở ra ngoài mạng nội bộ thì nên đặt `APP_API_KEY` hoặc lớp bảo vệ phía trước.
- Kết quả trong DynamoDB/S3 chưa có TTL hay lifecycle policy tự động, nên cần kế hoạch dọn dữ liệu nếu số job tăng.
- Worker chỉ ghi progress theo chu kỳ `APP_PROGRESS_UPDATE_INTERVAL`; thế hệ cuối luôn cập nhật `100%`.
- Payload sinh lịch phải hợp lệ theo schema: tối thiểu 12 bác sĩ và `shifts_per_day` hiện được cố định ở `2`.

## Cấu Trúc Chính

```text
NSGA2IS-SLS/
├── server/
│   ├── app/
│   │   ├── main.py
│   │   ├── worker.py
│   │   ├── api/
│   │   ├── application/
│   │   └── domain/
│   └── nsga2_improved/
├── deploy/
├── API.md
├── ARCHITECTURE.md
├── serverless.yml
├── requirements.txt
└── package.json
```

## Yêu Cầu

- Python 3.12
- Node.js và npm nếu deploy bằng Serverless Framework
- AWS CLI đã cấu hình nếu triển khai lên AWS

## Cài Đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Nếu deploy bằng Serverless Framework:

```bash
npm install
```

## Cấu Hình Môi Trường

Tạo file `.env` ở thư mục gốc khi chạy local. Các biến `APP_*` được đọc bởi `server/app/config.py`:

```bash
APP_ENV=development
APP_OPTIMIZER_POPULATION_SIZE=250
APP_OPTIMIZER_GENERATIONS=400
APP_PARETO_OPTIONS_LIMIT=6
APP_PROGRESS_UPDATE_INTERVAL=50
APP_RANDOMIZATION_STRENGTH=0.08
APP_RANDOM_SEED=
APP_CORS_ALLOW_ORIGINS=http://localhost:3000
APP_API_KEY=
```

Nếu `APP_API_KEY` được đặt, toàn bộ endpoint nghiệp vụ dưới `/api/v1/schedules` sẽ yêu cầu header `X-API-Key` khớp giá trị này. Nếu để trống, cơ chế xác thực sẽ tắt để không ảnh hưởng môi trường local.

Luồng async trên AWS cần các biến runtime sau:

```bash
QUEUE_URL=
TABLE_NAME=
BUCKET_NAME=
AWS_REGION=
```

Worker entrypoint còn hỗ trợ các biến/đầu vào riêng nếu chạy trực tiếp hoặc qua orchestrator:

```bash
WORKER_EVENT_JSON=
REQUEST_ID=
WORKER_MAX_RUNTIME_SECONDS=
LOG_LEVEL=
```

Trong `serverless.yml`, các biến AWS này được inject cho Lambda; worker Fargate và các script bootstrap cũng dùng cùng bộ tên canonical khi dựng env file.

`APP_PROGRESS_UPDATE_INTERVAL` điều khiển tần suất worker ghi tiến độ xuống DynamoDB. Ví dụ `50` nghĩa là chỉ cập nhật theo chu kỳ thế hệ, thay vì ghi ở mọi vòng lặp.

`ROOT_PATH=/dev` được dùng cho Lambda/API Gateway hiện tại; nếu đổi stage hay prefix, cần đồng bộ trong `serverless.yml` và `server/app/main.py`.

Khi chạy local, nhớ thực hiện từ bên trong thư mục `NSGA2IS-SLS/` vì code application nằm dưới package đó.

## Chạy Local

```bash
cd NSGA2IS-SLS
uvicorn server.app.main:app --reload
```

Sau khi chạy, API sẵn sàng tại:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

Nếu cần chạy worker thủ công, dùng payload JSON hợp lệ qua `--event`, `--payload`, hoặc `WORKER_EVENT_JSON`.

## Deploy AWS

```bash
serverless deploy --stage dev
```

Xem thông tin stack:

```bash
serverless info --stage dev
```

Base path hiện tại trên AWS là `/dev`, nên URL thực tế sẽ bao gồm tiền tố này khi đi qua API Gateway.

## Deploy Worker

- Khuyến nghị dùng `deploy/ecs-fargate/README.md` cho mô hình SQS -> EventBridge Pipes -> Fargate worker.
- Worker entrypoint chạy bằng `python -m server.app.worker` và nhận payload qua `--event`, `--payload`, hoặc `WORKER_EVENT_JSON`.
- Nếu dùng `deploy-worker.sh`, hãy set trước `AWS_ACCOUNT_ID`, `VPC_ID`, `SUBNET_IDS`, `QUEUE_ARN`, `TABLE_NAME`, và `BUCKET_NAME` trong môi trường shell để tránh hardcode hạ tầng trong script.
- Cách tiện nhất là tạo file `.deploy-worker.env` ở thư mục gốc repo; script sẽ tự đọc file này nếu tồn tại.
- Có sẵn file mẫu [`.deploy-worker.env.example`](.deploy-worker.env.example) để copy sang `.deploy-worker.env` rồi điền giá trị thật.

## Tài Liệu Liên Quan

- [API.md](API.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md)
- [serverless.yml](serverless.yml)
