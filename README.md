# NSGA2IS-SLS

Hệ thống tối ưu lịch trực bác sĩ bằng NSGA-II cải tiến. Ứng dụng cung cấp FastAPI để nhận yêu cầu sinh lịch, theo dõi tiến độ và lấy kết quả sau khi worker Lambda hoàn tất xử lý trên AWS.

## Tổng Quan

- `POST /api/v1/schedules/run` tạo request, lưu vào DynamoDB và đẩy message vào SQS, sau đó trả `request_id` ngay.
- Worker Lambda đọc message, chạy NSGA-II, lưu kết quả vào S3 và cập nhật trạng thái job.
- `GET /api/v1/schedules/progress/{request_id}` trả trạng thái hiện tại của job.
- `GET /api/v1/schedules/jobs/{request_id}/schedule` và `/metrics` chỉ trả khi job đã `completed`.
- `GET /health` trả trạng thái ứng dụng.

## Cấu Trúc Dự Án

```text
NSGA2IS-SLS/
├── server/
│   ├── app/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   ├── config.py
│   │   ├── main.py
│   │   └── worker.py
│   └── nsga2_improved/
├── tools/
├── artifacts/
├── API.md
├── README.md
├── serverless.yml
├── package.json
└── requirements.txt
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

Tạo file `.env` ở thư mục gốc khi chạy local. Các biến `APP_*` được đọc từ `.env`:

```bash
APP_ENV=development
APP_OPTIMIZER_POPULATION_SIZE=250
APP_OPTIMIZER_GENERATIONS=400
APP_PARETO_OPTIONS_LIMIT=6
APP_PROGRESS_UPDATE_INTERVAL=50
APP_RANDOMIZATION_STRENGTH=0.08
APP_RANDOM_SEED=
APP_CORS_ALLOW_ORIGINS=http://localhost:3000
```

Các biến runtime AWS cần cho luồng submit job:

```bash
SCHEDULE_QUEUE_URL=
SCHEDULE_TABLE_NAME=
SCHEDULE_RESULTS_BUCKET=
```

`POST /api/v1/schedules/run` phụ thuộc vào ba biến này. Nếu thiếu một trong số đó hoặc AWS không truy cập được, API sẽ trả `503 Service Unavailable` thay vì `500 Internal Server Error`.

`APP_PROGRESS_UPDATE_INTERVAL` kiểm soát tần suất worker ghi tiến độ xuống DynamoDB. Ví dụ `50` nghĩa là chỉ cập nhật ở mỗi 50 thế hệ, thay vì ghi ở mọi thế hệ, để giảm WCU và tránh throttling.

## Chạy Local

```bash
uvicorn server.app.main:app --reload
```

Sau khi chạy, API sẵn sàng tại:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

## Deploy AWS

```bash
serverless deploy --stage dev
```

Xem thông tin stack:

```bash
serverless info --stage dev
```

## Endpoint Reference

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/api/v1/schedules/run` | Tạo job sinh lịch |
| `GET` | `/api/v1/schedules/progress/{request_id}` | Xem trạng thái job |
| `GET` | `/api/v1/schedules/jobs/{request_id}/schedule` | Lấy lịch hoàn tất |
| `GET` | `/api/v1/schedules/jobs/{request_id}/metrics` | Lấy metrics thuật toán |
| `GET` | `/health` | Health check |

## Tài Liệu Liên Quan

- [API.md](API.md)
- [serverless.yml](serverless.yml)
