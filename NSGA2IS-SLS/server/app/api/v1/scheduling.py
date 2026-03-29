"""Router API v1 cho nghiệp vụ lập lịch ca trực (1 endpoint submit)."""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status as http_status
from botocore.exceptions import BotoCoreError, ClientError

from ...infrastructure.aws.job_state_store import (
    create_schedule_request,
    get_schedule_progress as load_schedule_progress,
)
from ...core.settings import get_settings
from ...application.services.schedule_view_builder import (
    build_job_detail_response,
    build_metrics_response,
    build_schedule_response,
)
from ...application.services.scheduling_profile_registry import get_profile_registry
from ...application.services.scheduling_request_adapter import resolve_scheduling_job_request
from ...domain.dto import (
    ScheduleGenerationEnvelopeDTO,
    ScheduleJobDetailDTO,
    ScheduleJobMetricsResponseDTO,
    ScheduleJobScheduleResponseDTO,
    ScheduleJobStatusDTO,
    ScheduleRequestAcceptedDTO,
    ScheduleRunRequestDTO,
    ScheduleProfileUpdateDTO,
    SchedulingProfileDTO,
)
from .schedule_validation import validate_schedule_feasibility

logger = logging.getLogger(__name__)


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    api_key = (get_settings().api_key or "").strip()
    if not api_key:
        return

    if not x_api_key or not hmac.compare_digest(x_api_key.strip(), api_key):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "X-API-Key"},
        )



router = APIRouter(prefix="/schedules", tags=["Schedules"], dependencies=[Depends(require_api_key)])
profile_router = APIRouter(prefix="/schedule-profiles", tags=["Schedule Profiles"], dependencies=[Depends(require_api_key)])
_profile_registry = get_profile_registry()


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


def _submit_schedule_request(payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    validate_schedule_feasibility(payload)
    job_request = resolve_scheduling_job_request(payload, settings=get_settings(), registry=_profile_registry)
    accepted = create_schedule_request(job_request.model_dump(mode="json"))
    return ScheduleRequestAcceptedDTO(
        request_id=accepted["request_id"],
        status=accepted["status"],
        progress_percent=accepted["progress_percent"],
        message=accepted["message"],
        schedule_type=job_request.schedule_type,
        profile_id=job_request.profile_id,
        response_profile=job_request.response_profile,
    )


def _submit_schedule_request_http(payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    try:
        return _submit_schedule_request(payload)
    except HTTPException:
        raise
    except (RuntimeError, BotoCoreError, ClientError) as exc:
        logger.exception("Unable to submit schedule request")
        raise HTTPException(
            status_code=503,
            detail="Unable to submit schedule request",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while submitting schedule request")
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while submitting schedule request",
        ) from exc


@router.post(
    "/run",
    response_model=ScheduleRequestAcceptedDTO,
    summary="Bắt đầu tạo lịch trực",
    status_code=http_status.HTTP_202_ACCEPTED,
)
def run_schedule(payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    """Đưa job vào hàng đợi tối ưu NSGA-II với payload nghiệp vụ."""
    return _submit_schedule_request_http(payload)


@router.post(
    "/run/{schedule_type}",
    response_model=ScheduleRequestAcceptedDTO,
    summary="Bắt đầu tạo lịch theo schedule_type",
    status_code=http_status.HTTP_202_ACCEPTED,
)
def run_schedule_by_type(schedule_type: str, payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    request_data = payload.model_copy(update={"schedule_type": schedule_type})
    return _submit_schedule_request_http(request_data)


@router.post(
    "/run/profile/{profile_id}",
    response_model=ScheduleRequestAcceptedDTO,
    summary="Bắt đầu tạo lịch theo profile_id",
    status_code=http_status.HTTP_202_ACCEPTED,
)
def run_schedule_by_profile(profile_id: str, payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    request_data = payload.model_copy(update={"profile_id": profile_id})
    return _submit_schedule_request_http(request_data)


@router.post(
    "/run/custom",
    response_model=ScheduleRequestAcceptedDTO,
    summary="Bắt đầu tạo lịch custom",
    status_code=http_status.HTTP_202_ACCEPTED,
)
def run_custom_schedule(payload: ScheduleRunRequestDTO) -> ScheduleRequestAcceptedDTO:
    request_data = payload.model_copy(update={"schedule_type": "custom"})
    return _submit_schedule_request_http(request_data)


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
    "/jobs/{request_id}",
    response_model=ScheduleJobDetailDTO,
    summary="Lấy trạng thái job kèm kết quả nếu đã hoàn tất",
)
def get_job_detail(request_id: str) -> ScheduleJobDetailDTO:
    progress = load_schedule_progress(request_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy request_id")

    envelope = None
    if progress.get("result") is not None:
        envelope = ScheduleGenerationEnvelopeDTO.model_validate(progress["result"])

    return build_job_detail_response(
        request_id=progress["request_id"],
        status=str(progress.get("status", "queued")),
        progress_percent=int(progress.get("progress_percent", 0)),
        message=progress.get("message", ""),
        error=progress.get("error"),
        envelope=envelope,
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


@profile_router.get(
    "",
    response_model=list[SchedulingProfileDTO],
    summary="Danh sách schedule profiles",
)
def list_schedule_profiles() -> list[SchedulingProfileDTO]:
    return _profile_registry.list_profiles()


@profile_router.get(
    "/{profile_id}",
    response_model=SchedulingProfileDTO,
    summary="Lấy schedule profile theo profile_id",
)
def get_schedule_profile(profile_id: str) -> SchedulingProfileDTO:
    profile = _profile_registry.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy profile_id")
    return profile


@profile_router.post(
    "",
    response_model=SchedulingProfileDTO,
    summary="Tạo hoặc cập nhật schedule profile",
    status_code=http_status.HTTP_201_CREATED,
)
def create_schedule_profile(payload: SchedulingProfileDTO) -> SchedulingProfileDTO:
    return _profile_registry.upsert_profile(payload)


@profile_router.patch(
    "/{profile_id}",
    response_model=SchedulingProfileDTO,
    summary="Cập nhật một phần schedule profile",
)
def patch_schedule_profile(profile_id: str, payload: ScheduleProfileUpdateDTO) -> SchedulingProfileDTO:
    try:
        return _profile_registry.update_profile(profile_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy profile_id") from exc
