# NSGA2IS-SLS

Hệ thống sinh lịch trực bác sĩ bằng NSGA-II cải tiến. API FastAPI nhận request, ghi trạng thái job vào DynamoDB, đẩy payload vào SQS và trả `request_id` ngay. Worker chạy tách biệt theo kiểu event-driven, xử lý tối ưu, ghi kết quả lên S3 và cập nhật tiến độ job.

## Tóm Tắt Nhanh

- `POST /api/v1/schedules/run` tạo job bất đồng bộ và trả `202 Accepted`.
- `GET /api/v1/schedules/progress/{request_id}` xem trạng thái job.
- `GET /api/v1/schedules/jobs/{request_id}/schedule` lấy lịch đã hoàn tất.
- `GET /api/v1/schedules/jobs/{request_id}/metrics` lấy metrics của lịch.
- `GET /health` kiểm tra trạng thái ứng dụng.

## Kiến Trúc Tóm Tắt

- FastAPI chạy trên AWS Lambda qua Mangum.
- API chỉ validate request, ghi job vào DynamoDB và publish message vào SQS.
- Worker nhận payload riêng, chạy NSGA-II, ghi kết quả JSON lên S3 và cập nhật trạng thái `running/completed/failed`.
- Fargate + EventBridge Pipes là đường chạy worker chuẩn trong repo.
- Chi tiết kiến trúc, luồng dữ liệu và các ràng buộc runtime được mô tả trong [ARCHITECTURE.md](ARCHITECTURE.md) và [API.md](API.md).

## Cấu Trúc Chính

```text
NSGA2IS-SLS/
├── server/
│   ├── app/
│   │   ├── core/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   ├── infrastructure/
│   │   ├── main.py
│   │   └── worker.py
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

Tạo file `.env` ở thư mục gốc khi chạy local. Các biến cấu hình được đọc trong [NSGA2IS-SLS/server/app/core/settings.py](NSGA2IS-SLS/server/app/core/settings.py) và được dùng lại bởi Lambda, worker và script deploy. Nếu cần danh sách biến runtime đầy đủ, tham chiếu trực tiếp file settings và [serverless.yml](serverless.yml).

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

Xem cấu hình và lệnh triển khai trong [serverless.yml](serverless.yml). Nếu cần kiểm tra mô hình worker trên ECS Fargate, dùng [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md).

## Deploy Worker

Mô hình worker chuẩn là SQS -> EventBridge Pipes -> Fargate. Hướng dẫn triển khai và runbook go-live nằm trong [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md).

## Tài Liệu Liên Quan

- [API.md](API.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md)
- [serverless.yml](serverless.yml)
