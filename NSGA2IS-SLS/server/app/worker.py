import json
import traceback

from app.application.services.async_schedule_service import (
    mark_completed,
    mark_failed,
    mark_running,
)
from app.application.use_cases.generate_schedule import GenerateScheduleUseCase
from app.domain.schemas import ScheduleRunRequestDTO


def handler(event, context):
    records = event.get("Records", [])
    for record in records:
        request_id = ""
        try:
            body = json.loads(record["body"])
            request_id = str(body["request_id"])
            payload = body["payload"]

            schedule_request = ScheduleRunRequestDTO.model_validate(payload)
            mark_running(request_id)
            result = GenerateScheduleUseCase().execute(schedule_request)
            mark_completed(request_id, result.model_dump(mode="json"))
        except Exception:
            if request_id:
                mark_failed(request_id, traceback.format_exc())

    return {"statusCode": 200, "processed": len(records)}
