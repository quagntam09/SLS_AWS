# API Reference

Tài liệu tham chiếu cho API lập lịch ca trực. Luồng thực tế là: API nhận request, ghi job vào DynamoDB, đẩy message vào SQS, worker xử lý job và lưu kết quả lên S3, rồi API đọc lại trạng thái/kết quả theo `request_id`.

## Base URL

- Local: `http://127.0.0.1:8000`
- Local docs: `http://127.0.0.1:8000/docs`
- AWS: URL từ `serverless info --stage <stage>`
- AWS current config: base path `/dev`

## Authentication

Auth API key là tuỳ chọn trong local, nhưng trong môi trường non-dev hệ thống yêu cầu `APP_API_KEY` để tránh mở endpoint công khai.

## 1. POST /api/v1/schedules/run

Tạo job sinh lịch mới.

Ví dụ dưới đây chỉ minh họa format. Payload thật phải có ít nhất 12 bác sĩ hợp lệ theo schema.

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
    { "id": "DOC001", "name": "Tran Van A", "experiences": 5, "department_id": "D1", "specialization": "General", "days_off": ["2026-03-28"], "preferred_extra_days": ["2026-03-29"], "has_valid_license": true, "is_intern": false },
    { "id": "DOC002", "name": "Tran Van B", "experiences": 7, "department_id": "D1", "specialization": "General", "days_off": [], "preferred_extra_days": [], "has_valid_license": true, "is_intern": false }
    // thêm tối thiểu 10 bác sĩ nữa
  ]
}
```

### Validation chính

- `doctors` phải có ít nhất 12 phần tử.
- `doctor.id` phải unique.
- `doctor.experiences` là số thực (`float`), không ép về `int`.
- `preferred_extra_days` là tín hiệu tối ưu cho scheduler, không phải validation loại trừ.
- `max_days_off_per_doctor` áp dụng cho số ngày nghỉ trong kỳ.
- `rooms_per_shift` nằm trong khoảng `1..10`.
- `doctors_per_room` nằm trong khoảng `1..15`.
- `shifts_per_day` chấp nhận `1` hoặc `2` (hard constraint HC-09).

### Response 202

```json
{
  "request_id": "req_550e8400e29b",
  "status": "queued",
  "progress_percent": 0,
  "message": "Schedule generation request accepted"
}
```

### Status codes

- `202`: request hợp lệ và đã được xếp hàng.
- `422`: lỗi validate schema của FastAPI/Pydantic.
- `503`: thiếu cấu hình AWS hoặc không truy cập được DynamoDB/SQS/S3.
- `500`: lỗi không mong đợi trong quá trình tạo request.

## 2. GET /api/v1/schedules/progress/{request_id}

Lấy trạng thái job hiện tại, không trả full result.

### Response 200

```json
{
  "request_id": "req_550e8400e29b",
  "status": "running",
  "progress_percent": 65,
  "message": "Schedule generation is running (generation 260/400)",
  "error": null
}
```

### Ý nghĩa status

- `queued`: đã ghi vào DynamoDB và đẩy sang queue.
- `running`: worker đang xử lý.
- `completed`: đã có kết quả trong S3.
- `failed`: job lỗi, xem `error`.

### Status codes

- `200`: tìm thấy `request_id`.
- `404`: không có `request_id`.

### Lưu ý

Worker không ghi progress ở mọi thế hệ. Tần suất ghi được điều khiển bởi `APP_PROGRESS_UPDATE_INTERVAL`; ở thế hệ cuối cùng worker luôn ghi `100%`.
Nếu job thất bại, API có thể trả `409` ở các endpoint lấy lịch hoặc metrics để báo rằng kết quả không còn khả dụng.

## 3. GET /api/v1/schedules/jobs/{request_id}/schedule

Lấy lịch đã hoàn tất và các phương án Pareto.

### Response 200

```json
{
  "request_id": "req_550e8400e29b",
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

- `200`: job đã `completed`.
- `404`: không có `request_id`.
- `409`: job chưa sẵn sàng hoặc job đã `failed`.

### Ghi chú

- Trường `selected` trong ví dụ chỉ minh họa cấu trúc tổng quát; response thực tế có đầy đủ các trường của DTO.

## 4. GET /api/v1/schedules/jobs/{request_id}/metrics

Lấy metrics thuật toán và metrics của từng phương án Pareto.

### Response 200

```json
{
  "request_id": "req_550e8400e29b",
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

- `200`: job đã `completed`.
- `404`: không có `request_id`.
- `409`: job chưa sẵn sàng hoặc job đã `failed`.

### Ghi chú

- `algorithm_run_metrics` có thể là `null` nếu lần chạy không ghi được metadata thuật toán đầy đủ.

## 5. GET /health

### Response 200

```json
{
  "status": "ok"
}
```

## 6. Ghi chú vận hành

- `progress` chỉ trả DTO trạng thái, không trả full result.
- `schedule` và `metrics` chỉ trả khi job đã `completed`.
- Kết quả hoàn chỉnh được lưu dưới key `{S3_RESULT_PREFIX}/{request_id}.json` trong S3 (default prefix `results`).
- Tham số thuật toán (`APP_SHIFT_HOURS`, `APP_MAX_CONSECUTIVE_DAYS`, v.v.) được cấu hình qua biến môi trường — xem [ARCHITECTURE.md](ARCHITECTURE.md#7-runtime-và-cấu-hình).
- Checklist kiểm tra triển khai AWS nằm trong [deploy/ecs-fargate/README.md](deploy/ecs-fargate/README.md).
