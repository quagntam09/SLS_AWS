# API Reference

Tài liệu tham chiếu cho luồng async trên AWS.

## 1. Base URL

- Local: `http://127.0.0.1:8000`
- AWS: URL từ `serverless deploy` hoặc `serverless info`

Luồng production trên AWS:

1. `POST /api/v1/schedules/run` ghi request vào DynamoDB và đẩy message vào SQS.
2. Worker Lambda đọc message, chạy NSGA-II, rồi lưu kết quả vào S3.
3. API `progress`, `schedule`, `metrics` đọc lại dữ liệu từ DynamoDB/S3.

## 2. POST /api/v1/schedules/run

Tạo job sinh lịch mới.

### Request body

```json
{
  "start_date": "2026-03-25",
  "num_days": 7,
  "max_weekly_hours_per_doctor": 48,
  "max_days_off_per_doctor": 5,
  "rooms_per_shift": 2,
  "doctors_per_room": 2,
  "shifts_per_day": 2,
  "doctors": [
    {
      "id": "DOC001",
      "name": "Trần Văn A",
      "experiences": 5,
      "department_id": "DEPT001",
      "specialization": "General",
      "days_off": ["2026-03-26"],
      "preferred_extra_days": ["2026-03-27"],
      "has_valid_license": true,
      "is_intern": false
    }
  ]
}
```

### Validation

- `doctors` phải có ít nhất 12 phần tử.
- `doctor.id` phải unique.
- `doctor.experiences` là số thực, không ép về int.
- `days_off` không được giao với `preferred_extra_days`.
- `max_days_off_per_doctor` áp dụng cho ngày nghỉ trong kỳ.

### Response

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "progress_percent": 0,
  "message": "Schedule generation request submitted"
}
```

### Status codes

- `200`: request hợp lệ và đã được xếp hàng.
- `400`: lỗi validate nghiệp vụ.
- `422`: lỗi validate schema.
- `503`: thiếu cấu hình AWS hoặc không truy cập được DynamoDB/SQS/S3.

## 3. GET /api/v1/schedules/progress/{request_id}

Lấy trạng thái job hiện tại.

### Response

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress_percent": 65,
  "message": "Đang tối ưu bằng NSGA-II cải tiến (thế hệ 260/400)",
  "error": null
}
```

### Status codes

- `200`: tìm thấy request_id.
- `404`: không có request_id.

### Ý nghĩa status

- `queued`: đã vào DynamoDB/SQS.
- `running`: worker Lambda đang xử lý.
- `completed`: đã có kết quả.
- `failed`: job lỗi, xem `error`.

### Progress update batching

Worker không ghi progress xuống DynamoDB ở mọi thế hệ. Tần suất ghi được điều khiển bởi `APP_PROGRESS_UPDATE_INTERVAL` (mặc định `50`), nghĩa là chỉ cập nhật khi `generation % APP_PROGRESS_UPDATE_INTERVAL == 0` và luôn ghi ở thế hệ cuối cùng để đạt `100%`.

## 4. GET /api/v1/schedules/jobs/{request_id}/schedule

Lấy lịch đã hoàn tất và các phương án Pareto.

### Response shape

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "selected_option_id": "OPT-01",
  "selected": {
    "start_date": "2026-03-25",
    "num_days": 7,
    "rooms_per_shift": 2,
    "doctors_per_room": 2,
    "shifts_per_day": 2,
    "assignments": []
  },
  "pareto_options": []
}
```

### Status codes

- `200`: job completed.
- `409`: job đang chạy, queued, hoặc failed.
- `404`: không có request_id.

## 5. GET /api/v1/schedules/jobs/{request_id}/metrics

Lấy metrics thuật toán và metrics của từng phương án Pareto.

### Response shape

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "algorithm_run_metrics": {
    "elapsed_seconds": 12.45,
    "n_generations": 260,
    "population_size": 250,
    "pareto_front_size": 8,
    "best_hard_objective": 0.0,
    "best_soft_objective": 0.15,
    "best_workload_std_objective": 0.12,
    "best_fairness_objective": 0.11,
    "convergence_hard_ratio": null,
    "convergence_soft_ratio": 0.88,
    "convergence_workload_ratio": 0.81,
    "convergence_fairness_ratio": 0.81
  },
  "pareto_options": [
    {
      "option_id": "OPT-01",
      "metrics": {}
    }
  ]
}
```

### Status codes

- `200`: job completed.
- `409`: job đang chạy, queued, hoặc failed.
- `404`: không có request_id.

## 6. Health Check

### GET /health

Response:

```json
{
  "status": "ok"
}
```

## 7. AWS Verification Checklist

Để xác nhận thuật toán đã chạy trên AWS, kiểm tra theo thứ tự sau:

1. `POST /api/v1/schedules/run` trả `request_id`.
2. `GET /api/v1/schedules/progress/{request_id}` chuyển sang `completed`.
3. `GET /api/v1/schedules/jobs/{request_id}/schedule` trả 200.
4. `GET /api/v1/schedules/jobs/{request_id}/metrics` trả 200.
5. DynamoDB item có `status=completed` và `result_s3_key`.
6. S3 có object `results/{request_id}.json`.

### AWS CLI ví dụ

```bash
aws dynamodb get-item \
  --table-name NSGA2IS-SLS-dev-requests \
  --key '{"request_id": {"S": "paste-request-id-here"}}'

aws s3 cp \
  "s3://nsga2is-sls-dev-results-<account-id>/results/paste-request-id-here.json" \
  -
```

## 8. Deploy nhanh

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g serverless
serverless deploy --stage dev
```

## 9. Notes

- `progress` endpoint trả DTO trạng thái, không trả full result.
- `schedule` và `metrics` chỉ trả khi job đã `completed`.
- CORS lấy từ `APP_CORS_ALLOW_ORIGINS`.
- `APP_PROGRESS_UPDATE_INTERVAL` kiểm soát tần suất worker ghi progress xuống DynamoDB để giảm WCU và tránh throttling.
