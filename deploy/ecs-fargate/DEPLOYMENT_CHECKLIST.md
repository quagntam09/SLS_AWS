# Checklist Triển Khai ECS Fargate Worker + EventBridge Pipes

Tài liệu này là checklist triển khai end-to-end cho mục tiêu ban đầu: tách worker NSGA-II sang container trên ECS Fargate, nhận job từ SQS qua EventBridge Pipes, cập nhật DynamoDB, lưu kết quả lên S3, và có DLQ để không mất job lỗi.

## Mục tiêu kiến trúc

- API vẫn nhận request và đẩy job vào SQS.
- Fargate task chạy 1 job rồi tự thoát.
- Nếu task lỗi nhiều lần, message được đẩy sang DLQ.
- Worker cập nhật trạng thái vào DynamoDB và lưu kết quả vào S3.
- Mạng private nên ưu tiên VPC Endpoints thay vì NAT Gateway nếu có thể.
- Worker có một giới hạn runtime cứng để tránh zombie task; DLQ không thay thế cơ chế timeout này.

## Bước 0: Chuẩn bị thông tin bắt buộc

Chuẩn bị sẵn các giá trị sau trước khi triển khai:

- AWS Region, ví dụ `ap-southeast-1`
- VPC ID
- Danh sách private subnet cho Fargate task
- Security group cho task Fargate
- SQS queue chính của job
- SQS DLQ
- DynamoDB table name
- S3 bucket name lưu kết quả
- ECR repository URI của image worker
- ECS cluster name nếu muốn đặt cố định

## Bước 1: Thiết kế hàng đợi và DLQ

### 1.1. Tạo hoặc xác nhận queue chính

- Queue chính là nơi API đẩy job vào.
- Job body phải có format:

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

### 1.2. Tạo DLQ

- Tạo một SQS queue riêng cho message thất bại, ví dụ `nsga2is-sls-worker-dlq`.
- Thiết lập retention đủ dài để điều tra sự cố, ví dụ 14 ngày.
- DLQ dùng để giữ job lỗi thay vì mất message hoặc gây tắc queue chính.

### 1.3. Hiểu đúng retry của EventBridge Pipes

- EventBridge Pipes với target ECS chỉ coi việc `RunTask` thành công là hoàn tất delivery.
- Pipes không chờ NSGA-II chạy xong.
- DLQ của Pipes hữu ích cho lỗi delivery / tạo task, không phải cho lỗi runtime sau khi task đã bắt đầu.
- Vì vậy cần kết hợp DLQ với timeout nội bộ trong worker và/hoặc giám sát ECS state change.

### 1.4. Quyền IAM liên quan DLQ

- Role của Pipe phải có quyền `sqs:SendMessage` vào DLQ.
- Role của Pipe vẫn cần quyền đọc queue chính.

### 1.5. Nếu dùng CloudFormation mẫu

- File mẫu đã có trong [worker-fargate-stack.yaml](worker-fargate-stack.yaml).
- Stack hiện có tham số `DlqName`, `WorkerMaxRuntimeSeconds` và tạo luôn SQS DLQ để dùng cho EventBridge Pipes.

## Bước 2: Build và push image worker lên ECR

### 2.1. Build image

Từ thư mục gốc project:

```bash
docker build -t nsga2is-sls-worker:latest .
```

### 2.2. Tạo ECR repository

```bash
aws ecr create-repository --repository-name nsga2is-sls-worker --region ap-southeast-1
```

### 2.3. Login Docker vào ECR

```bash
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com
```

### 2.4. Tag và push image

```bash
docker tag nsga2is-sls-worker:latest <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/nsga2is-sls-worker:latest
docker push <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/nsga2is-sls-worker:latest
```

### 2.5. Ghi lại image URI

- URI này sẽ đi vào tham số `ImageUri` của stack.

## Bước 3: Chọn cấu hình CPU/RAM cho Fargate

### 3.1. Hiểu rủi ro tài nguyên

- NSGA-II có thể tiêu thụ RAM lớn khi population/generations tăng.
- Nếu cấp thiếu, task có thể bị OOM và dừng đột ngột.
- Khi đó job có thể không kịp cập nhật lỗi đẹp vào DynamoDB.

### 3.2. Chỉnh tham số CPU/RAM

Trong [worker-fargate-stack.yaml](worker-fargate-stack.yaml):

- `Cpu`
- `Memory`

Gợi ý khởi điểm:

- `Cpu = 1024`, `Memory = 2048` cho test nhỏ
- `Cpu = 2048`, `Memory = 4096` nếu population/generations lớn hơn

### 3.3. Chỉnh giới hạn runtime

- `WorkerMaxRuntimeSeconds` đang có giá trị mặc định 7200 giây (2 giờ).
- Đây là giới hạn cứng do chính worker áp dụng, giúp task tự thoát nếu thuật toán chạy quá lâu hoặc treo.
- Nếu muốn an toàn hơn, có thể giảm xuống trong môi trường test.

### 3.4. Khi nào tăng lên nữa

- Khi job nhiều bác sĩ, nhiều ngày, hoặc lịch quá lớn.
- Khi CloudWatch Logs cho thấy task bị dừng do thiếu bộ nhớ.

## Bước 4: Thiết kế mạng private với VPC Endpoints

### 4.1. Vì sao cần endpoints

- Nếu task chạy trong private subnet, nó không có internet mặc định.
- Nếu không có NAT Gateway hoặc endpoints, task có thể không kéo được image từ ECR hoặc không gọi được AWS API.
- VPC Endpoints giúp traffic đi nội bộ AWS, an toàn hơn và thường tiết kiệm hơn NAT Gateway.

### 4.2. Gateway Endpoints cần có

- S3 Gateway Endpoint
- DynamoDB Gateway Endpoint

### 4.3. Interface Endpoints cần có

- ECR API
- ECR DKR
- CloudWatch Logs
- STS nếu task hoặc quyền runtime cần gọi STS trực tiếp

### 4.4. Cách gắn endpoints

- Tạo endpoints trong cùng VPC với Fargate tasks.
- Gắn route table của subnet private vào S3/DynamoDB gateway endpoint.
- Gắn security group cho interface endpoints để cho phép truy cập từ security group của worker.

### 4.5. Kiểm tra DNS

- Bảo đảm VPC bật `DNS resolution` và `DNS hostnames`.
- Đây là điều kiện gần như bắt buộc để interface endpoints hoạt động ổn định.

### 4.6. Nếu chưa có endpoints

- Bạn vẫn có thể chạy bằng NAT Gateway để thử nghiệm nhanh.
- Nhưng cho môi trường lâu dài nên ưu tiên endpoints.

## Bước 5: Triển khai stack worker Fargate

### 5.1. Dùng CloudFormation mẫu

File:

- [worker-fargate-stack.yaml](worker-fargate-stack.yaml)

### 5.2. Các tham số chính cần điền

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

### 5.3. Ví dụ triển khai bằng AWS CLI

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

### 5.4. Sau khi deploy xong

Kiểm tra output:

- Cluster ARN
- Task definition ARN
- Task role ARN
- Execution role ARN
- Security group ID
- DLQ ARN
- Pipe name

## Bước 6: Cấu hình EventBridge Pipes và DLQ

### 6.1. Cách Pipe hoạt động

- SQS nhận job từ API.
- Pipe lắng nghe queue chính.
- Mỗi message khởi chạy một Fargate task.
- Nếu task thất bại nhiều lần, message được đẩy sang DLQ.

### 6.2. Điều quan trọng cần đúng

- `WORKER_EVENT_JSON` phải nhận payload gốc từ SQS body.
- `REQUEST_ID` phải map từ `$.body.request_id`.
- Pipe role phải có quyền gửi message tới DLQ.

### 6.3. Kiểm tra DLQ sau khi deploy

- Vào SQS console.
- Xác nhận queue DLQ tồn tại.
- Đảm bảo message failed được chuyển vào đó khi Pipe không khởi tạo được task hoặc lỗi delivery xảy ra trước khi task được chạy.

### 6.4. Cách quan sát thất bại runtime

- Xem CloudWatch Logs của task.
- Xem bản ghi lỗi trong DynamoDB nếu worker kịp gọi `mark_failed`.
- Nếu task chết do timeout nội bộ, worker sẽ tự cập nhật `failed` trước khi thoát.

### 6.5. Cách xử lý OOM chính xác hơn

- OOM có thể khiến container bị kernel kill ngay, nên worker không kịp gọi `mark_failed`.
- Cách đơn giản: khi API query progress mà thấy `running` quá lâu, coi như timeout/failed và trả về cho client.
- Cách triệt để hơn: tạo EventBridge Rule lắng nghe ECS Task State Change.
  - Nếu task chuyển `STOPPED` với reason chứa `OutOfMemory` hoặc `OutOfMemoryError`.
  - Kích hoạt Lambda nhỏ để cập nhật DynamoDB sang `failed` theo `request_id`.

## Bước 7: Kiểm tra IAM

### 7.1. Task execution role

- Dùng để ECS kéo image và ghi log.
- Policy managed của ECS execution role là đủ cho phần image pull và log cơ bản.

### 7.2. Task role

- `dynamodb:GetItem`
- `dynamodb:UpdateItem`
- `s3:PutObject`
- `s3:GetObject`

### 7.3. Pipe role

- `sqs:ReceiveMessage`
- `sqs:DeleteMessage`
- `sqs:GetQueueAttributes`
- `sqs:ChangeMessageVisibility`
- `ecs:RunTask`
- `iam:PassRole`
- `sqs:SendMessage` vào DLQ

## Bước 8: Chạy thử end-to-end

### 8.1. Gửi job từ API

- Gọi endpoint tạo lịch hiện có.
- Lấy `request_id` trả về.

### 8.2. Kiểm tra trên AWS

- SQS queue chính có message.
- Pipe khởi tạo Fargate task.
- Task chạy `python -m server.app.worker`.
- Logs xuất hiện trên CloudWatch.
- DynamoDB chuyển trạng thái sang `running` rồi `completed`.
- S3 có file kết quả cuối.

### 8.3. Test lỗi giả lập

- Chạy với cấu hình thiếu RAM hoặc payload lỗi.
- Xác nhận task fail.
- Xác nhận message sang DLQ nếu lỗi xảy ra ở lớp delivery / khởi tạo task.
- Xác nhận job chuyển `failed` trong DynamoDB nếu worker bắt được exception hoặc timeout nội bộ.

### 8.4. Test zombie task

- Tạm giảm `WorkerMaxRuntimeSeconds` xuống giá trị nhỏ, ví dụ 120 giây.
- Chạy job lớn hơn thời gian này.
- Xác nhận worker tự log timeout, cập nhật `failed`, rồi thoát.

## Bước 9: Vận hành sau triển khai

### 9.1. Theo dõi CloudWatch Logs

- Xem log task Fargate.
- Dùng log để theo dõi progress và lỗi runtime.

### 9.2. Theo dõi DLQ

- Nếu DLQ tăng message, ưu tiên xử lý lỗi delivery, quyền IAM, network, hoặc ECS RunTask.
- Nếu task đã chạy rồi mới chết, hãy xem CloudWatch Logs, DynamoDB stale-running và rule ECS task state change.

### 9.3. Điều chỉnh tài nguyên

- Tăng `Cpu`/`Memory` trong stack nếu job lớn hơn.
- Giảm `AppProgressUpdateInterval` nếu cần cập nhật tiến độ dày hơn.
- Điều chỉnh `WorkerMaxRuntimeSeconds` nếu thực tế job hợp lệ cần chạy lâu hơn 2 giờ.

### 9.4. Điều chỉnh mạng

- Nếu đã có VPC Endpoints đầy đủ, đặt `AssignPublicIp=DISABLED`.
- Nếu chưa có endpoints, tạm thời dùng NAT Gateway để kiểm thử.

## Bước 10: Checklist nhanh trước go-live

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

## Tài liệu liên quan

- [worker-fargate-stack.yaml](worker-fargate-stack.yaml)
- [README.md](README.md)
- [worker-task-definition.json](worker-task-definition.json)
- [eventbridge-pipe-sqs-to-fargate.yaml](eventbridge-pipe-sqs-to-fargate.yaml)
