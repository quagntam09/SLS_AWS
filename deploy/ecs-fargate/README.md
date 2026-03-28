# ECS/Fargate Worker Mẫu

Bộ file này là đường chạy worker được khuyến nghị cho kiến trúc hiện tại: SQS -> EventBridge Pipes -> Fargate task -> `server.app.worker`.

## 1. Task Definition

File: [worker-task-definition.json](worker-task-definition.json)

- Dùng image build từ [Dockerfile](../../Dockerfile).
- Chạy entrypoint `python -m server.app.worker`.
- Nhận payload job qua biến môi trường `WORKER_EVENT_JSON`.
- Giữ các biến cấu hình runtime của worker: `APP_*`, `TABLE_NAME`, `BUCKET_NAME`, `AWS_REGION`, `LOG_LEVEL`.

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
- Nếu bạn muốn, mình có thể convert bộ mẫu này sang CloudFormation hoàn chỉnh hoặc CDK stack tiếp theo.
- Stack CloudFormation hoàn chỉnh đã có trong [worker-fargate-stack.yaml](worker-fargate-stack.yaml).

## 6. Checklist triển khai đầy đủ

- Xem [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) để đi theo từng bước: DLQ, CPU/RAM, VPC Endpoints, ECR, CloudFormation, Pipe, test end-to-end.
