# OADE-NSGA2-SLS

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
OADE-NSGA2-SLS/
├── server/
│   ├── app/
│   │   ├── core/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   ├── infrastructure/
│   │   ├── main.py
│   │   └── worker.py
│   └── OADE-NSGA-II/
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

Tạo file `.env` ở thư mục gốc khi chạy local. Có thể copy từ `.env.example` rồi điền giá trị thực.

Hai biến bắt buộc khi deploy lên AWS account mới:

- `SERVERLESS_ACCESS_KEY`: license key/token của Serverless Framework.
- `AWS_ACCOUNT_ID`: account đích để build/push image và deploy stack.

Các biến cấu hình runtime được đọc trong [OADE-NSGA-II-SLS/server/app/core/settings.py](OADE-NSGA-II-SLS/server/app/core/settings.py) và được dùng lại bởi Lambda, worker và script deploy. Nếu cần danh sách biến runtime đầy đủ, tham chiếu trực tiếp file settings và [serverless.yml](serverless.yml).

## Chạy Local

```bash
cd OADE-NSGA-II-SLS
uvicorn server.app.main:app --reload
```

Sau khi chạy, API sẵn sàng tại:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

Nếu cần chạy worker thủ công, dùng payload JSON hợp lệ qua `--event`, `--payload`, hoặc `WORKER_EVENT_JSON`.

## Deploy AWS

1) Deploy API/Lambda bằng Serverless Framework:

```bash
npm install
cp .env.example .env
# cập nhật .env: SERVERLESS_ACCESS_KEY, AWS_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
npx serverless deploy --stage dev --region ${AWS_REGION:-ap-southeast-2}
```

2) Deploy worker Fargate:

```bash
cp .deploy-worker.env.example .deploy-worker.env
# cập nhật .deploy-worker.env theo resource thực tế của account mới
bash ./deploy-worker.sh latest
```

Xem thêm runbook trong [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md).

## Deploy Worker

Mô hình worker chuẩn là SQS -> EventBridge Pipes -> Fargate. Hướng dẫn triển khai và runbook go-live nằm trong [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md).

## Tài Liệu Liên Quan

- [API.md](API.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md)
- [serverless.yml](serverless.yml)
