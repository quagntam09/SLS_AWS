"""
Use case sinh lịch trực bác sĩ.
"""

from __future__ import annotations

from typing import Callable

from ...core.settings import AppSettings, get_settings
from ...domain.nsga_scheduler import NsgaDutySchedulerService
from ...domain.dto import (
    ScheduleGenerationEnvelopeDTO,
    ScheduleGenerationRequestDTO,
    ScheduleRunRequestDTO,
    SchedulingJobRequestDTO,
)
from ..services.scheduling_request_adapter import resolve_generation_request


class GenerateScheduleUseCase:
    """Điểm vào của tầng ứng dụng cho nghiệp vụ tạo lịch."""

    def __init__(
        self,
        scheduler_service: NsgaDutySchedulerService | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.scheduler_service = scheduler_service or NsgaDutySchedulerService()
        self.settings = settings or get_settings()

    def _build_generation_request(
        self,
        request: ScheduleRunRequestDTO | SchedulingJobRequestDTO,
    ) -> ScheduleGenerationRequestDTO:
        return resolve_generation_request(request, settings=self.settings)

    def execute(
        self,
        request: ScheduleRunRequestDTO | SchedulingJobRequestDTO,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ScheduleGenerationEnvelopeDTO:
        generation_request = self._build_generation_request(request)
        return self.scheduler_service.generate(generation_request, progress_callback=progress_callback)
