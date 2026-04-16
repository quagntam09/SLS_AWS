# ECS/Fargate Worker Mẫu

Bộ file này là đường chạy worker được khuyến nghị cho kiến trúc hiện tại: SQS -> EventBridge Pipes -> Fargate task -> `server.app.worker`.

## 1. Task Definition

File: [worker-task-definition.json](worker-task-definition.json)

- Dùng image build từ [Dockerfile](../../Dockerfile).
- Chạy entrypoint `python -m server.app.worker`.
- Nhận payload job qua biến môi trường `WORKER_EVENT_JSON`.
- Giữ các biến cấu hình runtime của worker: `APP_*`, `TABLE_NAME`, `BUCKET_NAME`, `AWS_REGION`, `LOG_LEVEL`.
- **Biến mới có thể điều chỉnh**: `APP_SHIFT_HOURS` (default `4.5`), `APP_MAX_CONSECUTIVE_DAYS` (default `5`), `S3_RESULT_PREFIX` (default `results`).
  Thay đổi các biến này trong task definition hoặc CloudFormation stack khi bệnh viện cần cấu hình riêng.

## 2. EventBridge Pipes

File: [eventbridge-pipe-sqs-to-fargate.yaml](eventbridge-pipe-sqs-to-fargate.yaml)

- Source: SQS queue chứa message JSON.
- Target: ECS cluster.
- Mỗi message sẽ khởi chạy 1 Fargate task.
- `WORKER_EVENT_JSON` nhận trực tiếp `$.body` của message SQS.
- `REQUEST_ID` được map từ `$.body.request_id` để worker cập nhật DynamoDB khi lỗi.

## 2b. CloudFormation Stack

File: [worker-fargate-stack.yaml](worker-fargate-stack.yaml)

- Dựng luôn ECS cluster, security group, execution role, task role, task definition và Pipe trong một stack.
- Nhận đầu vào `VpcId`, `SubnetIds`, `QueueArn`, `ImageUri`, `TableName`, `BucketName`.
- Phù hợp khi muốn deploy nhanh mà không cần ghép từng tài nguyên bằng tay.

## 3. Payload Contract

Worker hiện tại hỗ trợ message body có dạng:

```json
{
  "request_id": "req_xxxxxxxxxxxx",
  "payload": {
    "start_date": "2026-03-28",
    "num_days": 7,
    "max_weekly_hours_per_doctor": 48,
    "max_days_off_per_doctor": 5,
    "rooms_per_shift": 1,
    "doctors_per_room": 5,
    "shifts_per_day": 2,
    "doctors": []
  }
}
```

Đây cũng là format mà API hiện tại ghi vào SQS, nên có thể dùng lại trực tiếp cho Pipes. Nếu chạy manual, bạn có thể truyền chính payload này qua `--event`/`--payload` hoặc set `WORKER_EVENT_JSON`.

## 4. IAM tối thiểu

Cần 2 nhóm quyền chính:

- **Pipes role**: `ecs:RunTask`, `iam:PassRole`, quyền đọc SQS.
- **Task role**: quyền truy cập DynamoDB và S3.

## 5. Ghi chú triển khai

- Nếu cluster/subnet nằm private, nên bật `AssignPublicIp: DISABLED` và bảo đảm có NAT Gateway để task ra được AWS API.
- Nếu muốn tối ưu chi phí, có thể giảm `cpu`/`memory` trong task definition theo profile thực tế của NSGA-II.
- Stack CloudFormation hoàn chỉnh đã có trong [worker-fargate-stack.yaml](worker-fargate-stack.yaml).

## 6. Deploy script an toàn hơn

File: [../../deploy-worker.sh](../../deploy-worker.sh)

- Script deploy không còn chứa hardcoded VPC/Subnet/Queue/Table/Bucket nữa.
- Script có thể tự nạp file `.deploy-worker.env` ở thư mục gốc repo nếu file này tồn tại.
- Cần truyền các biến môi trường bắt buộc trước khi chạy: `AWS_ACCOUNT_ID`, `VPC_ID`, `SUBNET_IDS`, `QUEUE_ARN`, `TABLE_NAME`, `BUCKET_NAME`.
- Các biến tùy chọn: `AWS_REGION`, `ECR_REPOSITORY`, `STACK_NAME`, `TEMPLATE_FILE`, `CPU`, `MEMORY`, `ASSIGN_PUBLIC_IP`.
- `ASSIGN_PUBLIC_IP` nên giữ `DISABLED` nếu môi trường VPC có NAT Gateway hoặc VPC Endpoints.
- Có thể dùng [`.deploy-worker.env.example`](../../.deploy-worker.env.example) làm template rồi copy sang `.deploy-worker.env`.
- Nếu đang dùng Windows PowerShell, chạy script qua `bash .\deploy-worker.sh` hoặc `wsl bash ./deploy-worker.sh`. Không nên nhập trực tiếp `./deploy-worker.sh` trong PowerShell vì đó là bash script.

## 7. Runbook triển khai end-to-end

### 7.1. Mục tiêu vận hành

- API vẫn nhận request và đẩy job vào SQS.
- Fargate task chạy một job rồi tự thoát.
- Nếu task lỗi ở lớp delivery hoặc khởi tạo, message được đẩy sang DLQ.
- Worker cập nhật trạng thái vào DynamoDB và lưu kết quả vào S3.
- Mạng private nên ưu tiên VPC Endpoints thay vì NAT Gateway nếu có thể.
- Worker có giới hạn runtime cứng để tránh zombie task; DLQ không thay thế cơ chế timeout này.

### 7.2. Chuẩn bị trước khi triển khai

Chuẩn bị sẵn:

- AWS Region, ví dụ `ap-southeast-1`
- VPC ID
- danh sách private subnet cho Fargate task
- security group cho task Fargate
- SQS queue chính của job
- SQS DLQ
- DynamoDB table name
- S3 bucket name lưu kết quả
- ECR repository URI của image worker
- ECS cluster name nếu muốn đặt cố định

### 7.3. Queue và DLQ

- Queue chính là nơi API đẩy job vào.
- Job body phải có format như ở mục Payload Contract.
- Tạo DLQ riêng, ví dụ `nsga2is-sls-worker-dlq`.
- Thiết lập retention đủ dài để điều tra sự cố, ví dụ 14 ngày.
- Role của Pipe phải có quyền `sqs:SendMessage` vào DLQ và vẫn có quyền đọc queue chính.
- EventBridge Pipes với target ECS chỉ coi `RunTask` thành công là hoàn tất delivery; DLQ chủ yếu bảo vệ lỗi delivery, không phải lỗi runtime sau khi task đã start.

### 7.4. Build và push image worker

Từ thư mục gốc project:

```bash
docker build -t nsga2is-sls-worker:latest .
```

Tạo ECR repository:

```bash
aws ecr create-repository --repository-name nsga2is-sls-worker --region ap-southeast-1
```

Login Docker vào ECR:

```bash
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com
```

Tag và push image:

```bash
docker tag nsga2is-sls-worker:latest <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/nsga2is-sls-worker:latest
docker push <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/nsga2is-sls-worker:latest
```

### 7.5. CPU/RAM và runtime

- NSGA-II có thể tiêu thụ RAM lớn khi population/generations tăng.
- Nếu cấp thiếu, task có thể bị OOM và dừng đột ngột.
- Gợi ý khởi điểm: `Cpu = 1024`, `Memory = 2048` cho test nhỏ.
- Gợi ý thực tế hơn: `Cpu = 2048`, `Memory = 4096` nếu workload lớn hơn.
- `WorkerMaxRuntimeSeconds` là giới hạn cứng do worker áp dụng, mặc định 7200 giây.

### 7.6. VPC Endpoints và mạng private

- Nếu task chạy trong private subnet, nó không có internet mặc định.
- Nếu không có NAT Gateway hoặc endpoints, task có thể không kéo được image từ ECR hoặc không gọi được AWS API.
- Gateway endpoints cần có: S3, DynamoDB.
- Interface endpoints cần có: ECR API, ECR DKR, CloudWatch Logs, STS nếu runtime cần gọi STS trực tiếp.
- Bảo đảm VPC bật DNS resolution và DNS hostnames.

### 7.7. Triển khai stack worker Fargate

File mẫu:

- [worker-fargate-stack.yaml](worker-fargate-stack.yaml)

Tham số chính:

- `VpcId`
- `SubnetIds`
- `QueueArn`
- `ImageUri`
- `TableName`
- `BucketName`
- `Cpu`
- `Memory`
- `AssignPublicIp`
- `DlqName`

Ví dụ deploy:

```bash
aws cloudformation deploy \
  --stack-name nsga2is-sls-worker-fargate \
  --template-file deploy/ecs-fargate/worker-fargate-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcId=vpc-xxxxxxxx \
    SubnetIds=subnet-aaaaaaa,subnet-bbbbbbb \
    QueueArn=arn:aws:sqs:ap-southeast-1:<ACCOUNT_ID>:nsga2is-sls-job-queue \
    ImageUri=<ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/nsga2is-sls-worker:latest \
    TableName=nsga2is-sls-dev-requests \
    BucketName=nsga2is-sls-dev-results \
    Cpu=2048 \
    Memory=4096 \
    AssignPublicIp=DISABLED \
    DlqName=nsga2is-sls-worker-dlq
```

### 7.8. IAM tối thiểu

- Task execution role: ECS pull image và ghi log.
- Task role: `dynamodb:GetItem`, `dynamodb:UpdateItem`, `s3:PutObject`, `s3:GetObject`.
- Pipe role: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, `sqs:ChangeMessageVisibility`, `ecs:RunTask`, `iam:PassRole`, `sqs:SendMessage` vào DLQ.

### 7.9. Kiểm tra sau deploy

- SQS queue chính có message.
- Pipe khởi tạo Fargate task.
- Task chạy `python -m server.app.worker`.
- Logs xuất hiện trên CloudWatch.
- DynamoDB chuyển sang `running` rồi `completed`.
- S3 có file kết quả cuối.
- Nếu task lỗi ở lớp delivery hoặc khởi tạo, message đi sang DLQ.

### 7.10. Vận hành sau triển khai

- Xem CloudWatch Logs của task Fargate để theo dõi progress và lỗi runtime.
- Nếu DLQ tăng message, ưu tiên kiểm tra IAM, network hoặc ECS RunTask.
- Nếu task chạy rồi mới chết, xem CloudWatch Logs, trạng thái stale-running trong DynamoDB và rule ECS Task State Change nếu có.
- Tăng `Cpu`/`Memory` khi job lớn hơn.
- Giảm `AppProgressUpdateInterval` nếu cần cập nhật tiến độ dày hơn.
- Giảm `WorkerMaxRuntimeSeconds` trong môi trường test để kiểm tra timeout.

### 7.11. Quick checklist trước go-live

- [ ] ECR image đã push
- [ ] Stack Fargate đã deploy
- [ ] DLQ đã tạo
- [ ] Pipe role có quyền gửi DLQ
- [ ] CPU/RAM đủ cho workload
- [ ] VPC endpoints đã có hoặc NAT Gateway sẵn sàng
- [ ] API gửi job đúng format
- [ ] DynamoDB và S3 nhận được cập nhật
- [ ] CloudWatch Logs hoạt động
- [ ] Test lỗi có thể đi sang DLQ
