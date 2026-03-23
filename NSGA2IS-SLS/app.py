from flask import Flask, jsonify, make_response, request

from models import ScheduleRequest, Doctor, RequestStatus
from schedule_service import submit_schedule_request, get_schedule_progress

app = Flask(__name__)


@app.route("/")
def hello_from_root():
    return jsonify(message='Hello from root!')

@app.route("/api/v1/schedules/generate", methods=["POST"])
def generate_schedule():
    """
    POST /api/v1/schedules/generate
    Generate doctor shift schedule.
    
    Request Body:
    {
        "start_date": "2026-03-22",
        "num_days": 7,
        "max_weekly_hours_per_doctor": 48,
        "max_days_off_per_doctor": 5,
        "required_doctors_per_shift": 5,
        "shifts_per_day": 2,
        "doctors": [...],
        "holiday_dates": [...],
        "pareto_options_limit": 6
    }
    
    Response: {request_id, status, progress_percent, message}
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = [
            "start_date", "num_days", "required_doctors_per_shift",
            "shifts_per_day", "doctors"
        ]
        if not all(field in data for field in required_fields):
            return make_response(
                jsonify(error="Missing required fields"),
                400
            )
        
        # Parse doctors
        doctors = [
            Doctor(
                id=doc["id"],
                name=doc["name"],
                experiences=doc.get("experiences", 0),
                department_id=doc.get("department_id", ""),
                specialization=doc.get("specialization", ""),
                days_off=doc.get("days_off", []),
                preferred_extra_days=doc.get("preferred_extra_days", []),
            )
            for doc in data.get("doctors", [])
        ]
        
        # Create request object
        schedule_request = ScheduleRequest(
            start_date=data["start_date"],
            num_days=data["num_days"],
            max_weekly_hours_per_doctor=data.get("max_weekly_hours_per_doctor", 48),
            max_days_off_per_doctor=data.get("max_days_off_per_doctor", 5),
            required_doctors_per_shift=data["required_doctors_per_shift"],
            shifts_per_day=data["shifts_per_day"],
            doctors=doctors,
            holiday_dates=data.get("holiday_dates", []),
            pareto_options_limit=data.get("pareto_options_limit", 6),
        )
        
        # Submit request
        request_id = submit_schedule_request(schedule_request)
        
        return jsonify(
            request_id=request_id,
            status=RequestStatus.QUEUED.value,
            progress_percent=0.0,
            message="Schedule generation request submitted"
        ), 202
    
    except Exception as e:
        return make_response(
            jsonify(error=str(e)),
            500
        )


@app.route("/api/v1/schedules/progress/<request_id>", methods=["GET"])
def get_schedule_progress_endpoint(request_id: str):
    """
    GET /api/v1/schedules/progress/{request_id}
    Get progress and result of schedule generation.
    
    Response: {request_id, status, progress_percent, message, result, error}
    """
    try:
        progress = get_schedule_progress(request_id)
        
        if progress is None:
            return make_response(
                jsonify(error="Request not found"),
                404
            )
        
        response_data = progress.to_dict()
        
        # Return appropriate status code
        status_code = 200
        if progress.status == RequestStatus.QUEUED or progress.status == RequestStatus.RUNNING:
            status_code = 202  # Accepted - still processing
        elif progress.status == RequestStatus.FAILED:
            status_code = 400  # Bad Request
        
        return jsonify(response_data), status_code
    
    except Exception as e:
        return make_response(
            jsonify(error=str(e)),
            500
        )


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
