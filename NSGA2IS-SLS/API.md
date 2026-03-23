# API Reference - NSGA2IS-SLS

---

## POST `/api/v1/schedules/generate`

Gửi yêu cầu sinh lịch trực và nhận request_id để tracking tiến độ.

### Request

**Method:** POST  
**Content-Type:** application/json  
**HTTP Status:** 202 Accepted

#### Headers
```
Content-Type: application/json
```

#### Body

```json
{
  "start_date": "2026-03-22",
  "num_days": 7,
  "max_weekly_hours_per_doctor": 48,
  "max_days_off_per_doctor": 5,
  "required_doctors_per_shift": 5,
  "shifts_per_day": 2,
  "doctors": [
    {
      "id": "string",
      "name": "string",
      "experiences": 0,
      "department_id": "string",
      "specialization": "string",
      "days_off": ["2026-03-22"],
      "preferred_extra_days": ["2026-03-22"]
    }
  ],
  "holiday_dates": ["2026-03-22"],
  "pareto_options_limit": 6
}
```

#### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `start_date` | string | Yes | Ngày bắt đầu xếp lịch (YYYY-MM-DD) |
| `num_days` | integer | Yes | Số ngày xếp lịch |
| `max_weekly_hours_per_doctor` | integer | No | Số giờ làm tối đa/tuần (default: 48) |
| `max_days_off_per_doctor` | integer | No | Số ngày nghỉ tối đa (default: 5) |
| `required_doctors_per_shift` | integer | Yes | Số bác sĩ cần mỗi ca trực |
| `shifts_per_day` | integer | Yes | Số ca trực mỗi ngày |
| `doctors` | array | Yes | Danh sách bác sĩ (tối thiểu 1) |
| `holiday_dates` | array | No | Danh sách ngày lễ |
| `pareto_options_limit` | integer | No | Số lịch tối ưu cần trả về (default: 6) |

#### Doctor Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | ID duy nhất của bác sĩ |
| `name` | string | Tên bác sĩ |
| `experiences` | integer | Số năm kinh nghiệm |
| `department_id` | string | ID phòng ban |
| `specialization` | string | Chuyên ngành |
| `days_off` | array | Danh sách ngày đã đăng ký nghỉ |
| `preferred_extra_days` | array | Danh sách ngày muốn trực thêm |

### Response

**HTTP 202 Accepted**

```json
{
  "request_id": "req_a1b2c3d4e5f6",
  "status": "queued",
  "progress_percent": 0.0,
  "message": "Schedule generation request submitted"
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | ID duy nhất để tracking tiến độ |
| `status` | string | Trạng thái (queued, running, completed, failed) |
| `progress_percent` | number | Phần trăm tiến độ (0-100) |
| `message` | string | Thông báo mô tả |

### Errors

#### HTTP 400 Bad Request
```json
{
  "error": "Missing required fields"
}
```

#### HTTP 500 Internal Server Error
```json
{
  "error": "Internal server error message"
}
```

### Examples

#### cURL
```bash
curl -X POST http://localhost:5000/api/v1/schedules/generate \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-03-22",
    "num_days": 7,
    "required_doctors_per_shift": 5,
    "shifts_per_day": 2,
    "doctors": [
      {
        "id": "DOC001",
        "name": "Trần Văn A",
        "experiences": 5,
        "department_id": "DEPT001",
        "specialization": "Ngoại khoa",
        "days_off": [],
        "preferred_extra_days": []
      }
    ],
    "pareto_options_limit": 6
  }'
```

#### Python
```python
import requests
import json

url = "http://localhost:5000/api/v1/schedules/generate"
payload = {
    "start_date": "2026-03-22",
    "num_days": 7,
    "required_doctors_per_shift": 5,
    "shifts_per_day": 2,
    "doctors": [
        {
            "id": "DOC001",
            "name": "Trần Văn A",
            "experiences": 5,
            "department_id": "DEPT001",
            "specialization": "Ngoại khoa",
            "days_off": [],
            "preferred_extra_days": []
        }
    ],
    "pareto_options_limit": 6
}

response = requests.post(url, json=payload)
data = response.json()
print(f"Request ID: {data['request_id']}")
```

---

## GET `/api/v1/schedules/progress/{request_id}`

Lấy tiến độ hiện tại và kết quả của yêu cầu sinh lịch.

### Request

**Method:** GET  
**HTTP Status:** 200 OK (completed) or 202 Accepted (processing)

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `request_id` | string | Yes | ID của request sinh lịch |

### Response

#### HTTP 202 Accepted (Still Processing)

```json
{
  "request_id": "req_a1b2c3d4e5f6",
  "status": "running",
  "progress_percent": 45.0,
  "message": "Processing schedule generation...",
  "result": null,
  "error": null
}
```

#### HTTP 200 OK (Completed)

```json
{
  "request_id": "req_a1b2c3d4e5f6",
  "status": "completed",
  "progress_percent": 100.0,
  "message": "Schedule generation completed successfully",
  "result": {
    "selected_option_id": "opt_1_1711123456789",
    "selected_schedule": {
      "start_date": "2026-03-22",
      "num_days": 7,
      "required_doctors_per_shift": 5,
      "shifts_per_day": 2,
      "metrics": {
        "hard_violation_score": 0,
        "soft_violation_score": 2.5,
        "fairness_std": 0.82,
        "shift_fairness_std": 0.82,
        "day_off_fairness_std": 1.2,
        "day_off_fairness_jain": 0.93,
        "weekly_fairness_jain": 0.95,
        "monthly_fairness_jain": 0.95,
        "yearly_fairness_jain": 0.95,
        "holiday_fairness_jain": 0.92,
        "hard_score_visual": 0,
        "soft_score_visual": 8.5,
        "fairness_score_visual": 8.5,
        "overall_score_visual": 9.2,
        "score_badges": {
          "fairness": "good",
          "compliance": "excellent"
        },
        "weekly_underwork_doctors": []
      },
      "assignments": [
        {
          "date": "2026-03-22",
          "shift": "shift_1",
          "doctor_ids": ["DOC001", "DOC002", "DOC003", "DOC004", "DOC005"]
        }
      ]
    },
    "pareto_options": [
      {
        "option_id": "opt_1_1711123456789",
        "metrics": { },
        "assignments": [ ],
        "doctor_workload_balances": [
          {
            "doctor_id": "DOC001",
            "doctor_name": "Trần Văn A",
            "weekly_shift_count": 6,
            "monthly_shift_count": 24,
            "yearly_estimated_shift_count": 312,
            "holiday_shift_count": 1,
            "day_off_count": 1
          }
        ]
      }
    ],
    "algorithm_run_metrics": {
      "elapsed_seconds": 1.234,
      "n_generations": 100,
      "population_size": 10,
      "pareto_front_size": 6,
      "best_hard_objective": 0,
      "best_balance_objective": 0.82,
      "convergence_hard_ratio": 1.0,
      "convergence_balance_ratio": 0.92
    }
  },
  "error": null
}
```

### Errors

#### HTTP 404 Not Found
```json
{
  "error": "Request not found"
}
```

#### HTTP 400 Bad Request (Failed)
```json
{
  "request_id": "req_a1b2c3d4e5f6",
  "status": "failed",
  "error": "Error message describing what went wrong"
}
```

### Examples

#### cURL
```bash
# Kiểm tra tiến độ (lần 1 - đang xử lý)
curl http://localhost:5000/api/v1/schedules/progress/req_a1b2c3d4e5f6

# Output
{
  "request_id": "req_a1b2c3d4e5f6",
  "status": "running",
  "progress_percent": 50.0
}

# Kiểm tra tiến độ (lần 2 - hoàn thành)
curl http://localhost:5000/api/v1/schedules/progress/req_a1b2c3d4e5f6

# Output (with full result)
{
  "request_id": "req_a1b2c3d4e5f6",
  "status": "completed",
  "progress_percent": 100.0,
  "result": { ... }
}
```

#### Python
```python
import requests
import time

request_id = "req_a1b2c3d4e5f6"
url = f"http://localhost:5000/api/v1/schedules/progress/{request_id}"

# Poll until completed
while True:
    response = requests.get(url)
    data = response.json()
    
    print(f"Status: {data['status']}, Progress: {data['progress_percent']}%")
    
    if data['status'] == 'completed':
        print("Schedule generated successfully!")
        print(data['result'])
        break
    elif data['status'] == 'failed':
        print(f"Error: {data['error']}")
        break
    
    time.sleep(1)  # Wait 1 second before polling again
```

---

## Status Values

| Status | Description |
|--------|-------------|
| `queued` | Yêu cầu đã được tiếp nhận, đang chờ xử lý |
| `running` | Đang sinh lịch |
| `completed` | Hoàn thành thành công, kết quả sẵn sàng |
| `failed` | Lỗi khi sinh lịch |

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request completed successfully |
| 202 | Accepted - Request received, still processing |
| 400 | Bad Request - Invalid input or failed request |
| 404 | Not Found - Request ID not found |
| 500 | Internal Server Error - Server error |

---

## Workflow Example

```
1. POST /api/v1/schedules/generate
   → Get request_id: "req_abc123"
   ← HTTP 202 + { request_id: "req_abc123", status: "queued" }

2. GET /api/v1/schedules/progress/req_abc123
   ← HTTP 202 + { status: "running", progress_percent: 30 }

3. Wait 1-2 seconds...

4. GET /api/v1/schedules/progress/req_abc123
   ← HTTP 200 + { status: "completed", result: {...} }
   
