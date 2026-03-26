# NSGA2IS-SLS

Hệ thống tối ưu lịch trực bác sĩ bằng NSGA-II cải tiến. Dự án có 2 chế độ chạy chính:

- Chạy local để phát triển, debug, và kiểm tra thuật toán.
- Chạy async trên AWS với FastAPI, SQS, DynamoDB, và S3.

## Tổng Quan

- `POST /api/v1/schedules/run` tạo request và trả `request_id` ngay.
- Worker Lambda xử lý job, chạy NSGA-II, rồi lưu kết quả vào S3.
- `GET /api/v1/schedules/progress/{request_id}` dùng để poll trạng thái.
- `GET /api/v1/schedules/jobs/{request_id}/schedule` và `/metrics` chỉ trả khi job đã hoàn tất.

## Cấu Trúc Dự Án

```text
NSGA2IS-SLS/
├── server/
│   ├── app/
│   │   ├── main.py
│   │   ├── worker.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── application/
│   │   └── domain/
│   └── nsga2_improved/
├── artifacts/
├── README.md
├── API.md
├── TOOLS_GUIDE.md
├── PAYLOAD_SAMPLES.md
├── TEST_CASES.md
├── serverless.yml
└── requirements.txt
```

## Yêu Cầu

- Python 3.12
- Node.js 18+ nếu deploy bằng Serverless Framework
- AWS CLI đã cấu hình nếu chạy trên AWS

## Cài Đặt Local

```bash
cd /path/to/NSGA2IS-SLS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Nếu bạn cần deploy AWS bằng Serverless Framework, cài thêm:

```bash
npm install
```

## Cấu Hình Môi Trường

Tạo file `.env` ở thư mục gốc nếu chạy local. Các giá trị dưới đây là khuyến nghị để dev:

```bash
APP_ENV=development
APP_OPTIMIZER_POPULATION_SIZE=250
APP_OPTIMIZER_GENERATIONS=400
APP_PARETO_OPTIONS_LIMIT=6
APP_RANDOMIZATION_STRENGTH=0.08
APP_RANDOM_SEED=
APP_CORS_ALLOW_ORIGINS=http://localhost:3000,https://your-frontend-domain.example
```

Lưu ý:

- `APP_CORS_ALLOW_ORIGINS` nhận danh sách phân tách bằng dấu phẩy.
- Submit job qua API cần thêm các biến AWS runtime: `SCHEDULE_QUEUE_URL`, `SCHEDULE_TABLE_NAME`, `SCHEDULE_RESULTS_BUCKET`.
- Trong `serverless.yml`, các biến này được inject tự động khi deploy lên AWS.

## Chạy API Local

```bash
uvicorn server.app.main:app --reload
```

Sau khi chạy:

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Deploy AWS

### 1) Cài plugin Serverless

```bash
npm install
```

### 2) Deploy

```bash
serverless deploy --stage dev
```

Nếu bạn dùng `npx`, có thể chạy:

```bash
npx serverless deploy --stage dev
```

### 3) Xem URL API

```bash
serverless info --stage dev
```

### Tài Nguyên AWS Tạo Ra

- `ScheduleJobsQueue`: SQS queue nhận job.
- `ScheduleRequestsTable`: DynamoDB lưu trạng thái job.
- `ScheduleResultsBucket`: S3 lưu kết quả JSON.

## Cách Gọi API Trên AWS

### 1) Gửi request

```bash
AWS_BASE_URL="https://your-api-id.execute-api.region.amazonaws.com"

curl -X POST "${AWS_BASE_URL}/api/v1/schedules/run" \
  -H "Content-Type: application/json" \
  -d @payload.json
```

Response mẫu:

```json
{
  "request_id": "req_123456789abc",
  "status": "queued",
  "progress_percent": 0,
  "message": "Schedule generation request submitted"
}
```

### 2) Poll tiến độ

```bash
REQUEST_ID="paste-request-id-here"
curl "${AWS_BASE_URL}/api/v1/schedules/progress/${REQUEST_ID}"
```

Trạng thái hợp lệ:

- `queued`
- `running`
- `completed`
- `failed`

### 3) Lấy lịch và metrics

```bash
curl "${AWS_BASE_URL}/api/v1/schedules/jobs/${REQUEST_ID}/schedule"
curl "${AWS_BASE_URL}/api/v1/schedules/jobs/${REQUEST_ID}/metrics"
```

## Endpoint Reference

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/api/v1/schedules/run` | Tạo job sinh lịch |
| `GET` | `/api/v1/schedules/progress/{request_id}` | Xem trạng thái job |
| `GET` | `/api/v1/schedules/jobs/{request_id}/schedule` | Lấy lịch hoàn tất |
| `GET` | `/api/v1/schedules/jobs/{request_id}/metrics` | Lấy metrics thuật toán |
| `GET` | `/health` | Health check |

## Quy Trình Khuyến Nghị Khi Phát Triển

1. Tạo và kích hoạt virtual environment.
2. Cài dependencies bằng `pip install -r requirements.txt`.
3. Chuẩn bị payload JSON thủ công hoặc từ công cụ cá nhân bên ngoài repo.
4. Chạy `uvicorn server.app.main:app --reload` để kiểm tra API local.
5. Khi cần test end-to-end, deploy AWS rồi gọi API bằng `curl` hoặc công cụ HTTP client cá nhân.

## Lưu Ý Quan Trọng

- `doctors` phải có ít nhất 12 phần tử.
- `doctor.experiences` là số thực, không ép về int.
- `days_off` không được giao với `preferred_extra_days`.
- `POST /api/v1/schedules/run` dùng luồng async trên AWS nên cần các resource SQS/DynamoDB/S3.
- `worker.py` là entrypoint cho Lambda xử lý queue, không phải để gọi trực tiếp từ API local.

## Troubleshooting

- Job kẹt ở `queued` hoặc `running`: kiểm tra worker Lambda, SQS, và quyền IAM.
- `failed` do validate: kiểm tra payload, số lượng bác sĩ, và ràng buộc ngày nghỉ.
- `schedule` hoặc `metrics` không trả về: kiểm tra `result_s3_key` trong DynamoDB và object trong S3.
- API local trả lỗi thiếu env: kiểm tra `.env` và các biến AWS runtime cần cho submit job.

## Tài Liệu Liên Quan

- [API.md](API.md)
- [TOOLS_GUIDE.md](TOOLS_GUIDE.md)
- [PAYLOAD_SAMPLES.md](PAYLOAD_SAMPLES.md)
- [TEST_CASES.md](TEST_CASES.md)
- [serverless.yml](serverless.yml)
