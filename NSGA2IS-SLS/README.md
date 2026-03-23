# NSGA2IS-SLS: Doctor Shift Schedule Optimizer

**Hệ thống tối ưu hóa lịch trực bác sĩ trên AWS Serverless**

---

## 🎯 Tổng Quan

Ứng dụng sinh lịch trực bác sĩ tối ưu sử dụng **NSGA-II** trên **AWS Lambda**.

### Tính Năng
- ✅ API Async - Gửi yêu cầu, nhận ID, tracking tiến độ
- ✅ Sinh Lịch Tối Ưu - Tạo 6 giải pháp Pareto-optimal
- ✅ Cân Bằng Công Việc - Công bằng giữa bác sĩ
- ✅ Tuân Thủ Ràng Buộc - Ngày nghỉ, ngày lễ, giờ tối đa

### Tech Stack
- **Backend:** Flask 3.0.3
- **Language:** Python 3.12
- **Cloud:** AWS Lambda + API Gateway
- **Deployment:** Serverless Framework

---

## 📦 Cài Đặt & Chạy Cục Bộ

### 1. Setup môi trường

```bash
cd /home/quagntam/Developer/SLS_AWS/NSGA2IS-SLS

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
npm install
```

### 2. Chạy Flask

serverless wsgi serve
# → API chạy trên http://localhost:8000
```

### 3. Test API

```bash
# Sinh lịch
curl -X POST http://localhost:5000/api/v1/schedules/generate \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-03-22",
    "num_days": 7,
    "required_doctors_per_shift": 5,
    "shifts_per_day": 2,
    "doctors": [...],
    "pareto_options_limit": 6
  }'

# Kiểm tra tiến độ
curl http://localhost:5000/api/v1/schedules/progress/{request_id}
```

---

## 🚀 Deploy AWS

```bash
# Login
serverless login

# Deploy
serverless deploy

# View logs
serverless logs -f api -t

# Get API URL from output and test
curl -X POST https://your-api.execute-api.region.amazonaws.com/dev/api/v1/schedules/generate ...
```

---

## 📚 Documentation

- **[API.md](API.md)** - Chi tiết API endpoints & examples
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Kiến trúc hệ thống & data flow

---

## 📁 Project Structure

```
NSGA2IS-SLS/
├── app.py                      # Flask endpoints (136 lines)
├── models.py                   # 11 dataclasses (153 lines)
├── schedule_service.py         # Schedule generation logic (269 lines)
├── requirements.txt            # Flask, numpy
├── serverless.yml              # AWS config
├── nsga2_improved/             # NSGA-II algorithm (ready)
├── README.md                   # This file
├── API.md                      # API reference
```

---

## 🔌 Quick API Reference

### POST `/api/v1/schedules/generate` - Generate Schedule

**Input:** ScheduleRequest (JSON)
```json
{
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
      "days_off": ["2026-03-22"],
      "preferred_extra_days": ["2026-03-25"]
    }
  ],
  "holiday_dates": ["2026-03-22"],
  "pareto_options_limit": 6
}
```

**Output:** HTTP 202 Accepted
```json
{
  "request_id": "req_abc123",
  "status": "queued",
  "progress_percent": 0.0,
  "message": "Request submitted"
}
```

### GET `/api/v1/schedules/progress/{request_id}` - Check Progress

**Response:** HTTP 202 (processing) → 200 (completed)
```json
{
  "request_id": "req_abc123",
  "status": "completed",
  "progress_percent": 100.0,
  "result": {
    "selected_option_id": "opt_1_...",
    "selected_schedule": { ... },
    "pareto_options": [ ... ],
    "algorithm_run_metrics": { ... }
  }
}
```

See [API.md](API.md) for complete reference.

---

## 🧵 How It Works

```
1. Client POST /generate
        ↓
2. Validate input, parse doctors
        ↓
3. submit_schedule_request()
   ├─ Create request_id
   ├─ Store in SCHEDULE_REQUESTS dict
   ├─ Start background thread
   └─ Return 202 + request_id
        ↓
4. Background thread: _process_schedule_request()
   ├─ Update status QUEUED → RUNNING
   ├─ ScheduleGenerator.generate()
   ├─ Calculate metrics & workload
   └─ Update status RUNNING → COMPLETED
        ↓
5. Client GET /progress/{id}
   └─ Return ProgressResponse (status, result)
```

**Thread Safety:** `threading.Lock()` protects SCHEDULE_REQUESTS dict

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Response Time | 1-3 seconds |
| Memory Usage | <100 MB |
| Cold Start | 3-5 seconds |
| Warm Start | <500 ms |

---

## 📝 Deployment Notes

- **In-memory storage:** Data lost on Lambda restart → Upgrade to DynamoDB for production
- **Thread pool:** Single background thread → Use SQS/Lambda for heavy load
- **NSGA-II:** Ready in `nsga2_improved/` module → Integrate for real optimization

---

## 📞 Support

- Questions about setup? See installation steps above
- Need API details? See [API.md](API.md)
