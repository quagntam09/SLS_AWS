# NSGA2IS-SLS

Hệ thống sinh lịch trực bác sĩ bằng NSGA-II cải tiến. API FastAPI nhận request, lưu trạng thái job vào DynamoDB, đẩy payload vào SQS, rồi trả `request_id` ngay. Worker EC2 long-poll SQS, chạy tối ưu, ghi kết quả lên S3 và cập nhật tiến độ job.

## Tóm Tắt Nhanh

- `POST /api/v1/schedules/run` tạo job bất đồng bộ và trả `202 Accepted`.
- `GET /api/v1/schedules/progress/{request_id}` xem trạng thái job.
- `GET /api/v1/schedules/jobs/{request_id}/schedule` lấy lịch đã hoàn tất.
- `GET /api/v1/schedules/jobs/{request_id}/metrics` lấy metrics của lịch.
- `GET /health` kiểm tra trạng thái ứng dụng.

## Kiến Trúc Ngắn Gọn

- FastAPI chạy trên AWS Lambda qua Mangum.
- SQS dùng làm hàng đợi giữa API và worker.
- EC2 worker long-poll SQS để chạy thuật toán nặng.
- DynamoDB lưu `status`, `progress_percent`, `message`, `error` và key kết quả.
- S3 lưu payload kết quả hoàn chỉnh của từng `request_id`.

## Lưu Ý Vận Hành

- API hiện chưa có authentication/authorization. Nếu mở ra ngoài mạng nội bộ, cần đặt lớp bảo vệ phía trước.
- Kết quả trong DynamoDB/S3 chưa có TTL hay lifecycle policy tự động, nên cần kế hoạch dọn dữ liệu nếu số job tăng.
- Worker chỉ ghi progress theo chu kỳ `APP_PROGRESS_UPDATE_INTERVAL`; thế hệ cuối luôn cập nhật `100%`.

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
```

Luồng async trên AWS cần các biến runtime sau:

```bash
QUEUE_URL=
TABLE_NAME=
BUCKET_NAME=
```

Trong `serverless.yml`, các biến này được inject cho Lambda; worker EC2 và EC2 API setup dùng cùng bộ tên canonical khi dựng env file.

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

## Deploy AWS

```bash
serverless deploy --stage dev
```

Xem thông tin stack:

```bash
serverless info --stage dev
```

Base path hiện tại trên AWS là `/dev`, nên URL thực tế sẽ bao gồm tiền tố này khi đi qua API Gateway.

## Deploy EC2 Worker/API

Bộ file trong `deploy/` và các script gốc ở thư mục root dùng để dựng EC2 chạy API public qua nginx hoặc dựng worker riêng:

- `ec2_api_setup.sh`: dựng máy, cài Python/nginx, clone source, tạo virtualenv, tạo systemd unit và cấu hình reverse proxy
- `ec2_worker_setup.sh`: dựng máy, cài Python, clone source, tạo virtualenv, tạo env file và systemd unit cho worker SQS
- `deploy/user-data/ec2-api-user-data.sh`: user-data để EC2 tự chạy setup khi launch
- `deploy/user-data/ec2-worker-user-data.sh`: user-data để EC2 tự chạy setup worker khi launch
- `deploy/user-data/launch-template-user-data.sh`: mẫu user-data cho Launch Template
- `deploy/systemd/nsga2is-sls-api.service`: mẫu systemd unit cho FastAPI
- `deploy/systemd/nsga2-worker.service`: mẫu systemd unit cho worker nền
- `deploy/nginx/nsga2is-sls-api.conf`: mẫu nginx reverse proxy về `127.0.0.1:8000`

Worker EC2 dùng entrypoint `python -m server.app.worker` và cùng layout package với API, nên `PYTHONPATH` phải trỏ vào `NSGA2IS-SLS/`.

Nếu chưa có domain, có thể đặt `SERVER_NAME=_` trong cấu hình nginx.

## Tài Liệu Liên Quan

- [API.md](API.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [serverless.yml](serverless.yml)
