"""Router API v1 cho nghiệp vụ lập lịch ca trực (1 endpoint submit)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status as http_status
from botocore.exceptions import BotoCoreError, ClientError

from ...application.services.async_schedule_service import (
    create_schedule_request,
    get_schedule_progress as load_schedule_progress,
)
from ...application.services.schedule_view_builder import (
    build_metrics_response,
    build_schedule_response,
)
from ...domain.schemas import (
    ScheduleGenerationEnvelopeDTO,
    ScheduleJobMetricsResponseDTO,
    ScheduleJobScheduleResponseDTO,
    ScheduleJobStatusDTO,
    ScheduleRequestAcceptedDTO,
    ScheduleRunRequestDTO,
)
from .schedule_validation import validate_schedule_feasibility

router = APIRouter(prefix="/schedules", tags=["Schedules"])
logger = logging.getLogger(__name__)


def _require_completed_envelope(request_id: str) -> ScheduleGenerationEnvelopeDTO:
    progress = load_schedule_progress(request_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy request_id")

    status = str(progress.get("status", "queued")).upper()
    if status == "FAILED":
        raise HTTPException(
            status_code=409,
            detail=progress.get("error") or "Sinh lịch thất bại",
        )
    if status != "COMPLETED" or progress.get("result") is None:
        raise HTTPException(
            status_code=409,
            detail="Lịch chưa sẵn sàng hoặc job đang chạy",
        )
    return ScheduleGenerationEnvelopeDTO.model_validate(progress["result"])


@router.post(
    "/run",
    response_model=ScheduleRequestAcceptedDTO,
    summary="Bắt đầu tạo lịch trực",
    status_code=http_status.HTTP_202_ACCEPTED,
)
def run_schedule(payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    """Đưa job vào hàng đợi tối ưu NSGA-II với payload nghiệp vụ."""
    try:
        validate_schedule_feasibility(payload)
        return ScheduleRequestAcceptedDTO.model_validate(
            create_schedule_request(payload.model_dump(mode="json"))
        )
    except HTTPException:
        raise
    except (RuntimeError, BotoCoreError, ClientError) as exc:
        logger.exception("Unable to submit schedule request")
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while submitting schedule request")
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while submitting schedule request",
        ) from exc


@router.get(
    "/progress/{request_id}",
    response_model=ScheduleJobStatusDTO,
    summary="Theo dõi tiến độ job (không kèm lịch/chỉ số)",
)
def get_schedule_progress(request_id: str) -> ScheduleJobStatusDTO:
    progress = load_schedule_progress(request_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy request_id")
    return ScheduleJobStatusDTO(
        request_id=progress["request_id"],
        status=str(progress.get("status", "queued")),
        progress_percent=int(progress.get("progress_percent", 0)),
        message=progress.get("message", ""),
        error=progress.get("error"),
    )


@router.get(
    "/jobs/{request_id}/schedule",
    response_model=ScheduleJobScheduleResponseDTO,
    summary="Lấy lịch trực và các phương án Pareto (sau khi job xong)",
)
def get_job_schedule(request_id: str) -> ScheduleJobScheduleResponseDTO:
    envelope = _require_completed_envelope(request_id)
    return build_schedule_response(request_id, envelope)


@router.get(
    "/jobs/{request_id}/metrics",
    response_model=ScheduleJobMetricsResponseDTO,
    summary="Lấy chỉ số công bằng và fitness từng phương án (sau khi job xong)",
)
def get_job_metrics(request_id: str) -> ScheduleJobMetricsResponseDTO:
    envelope = _require_completed_envelope(request_id)
    return build_metrics_response(request_id, envelope)
