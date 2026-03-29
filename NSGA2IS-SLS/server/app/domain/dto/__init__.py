"""DTO domain được tách theo nhóm nghiệp vụ.

Các module con chỉ re-export từ `server.app.domain.schemas` để giữ nguyên định nghĩa gốc.
"""

from .people import DoctorProfileDTO
from .profiles import (
    ScheduleProfileUpdateDTO,
    SchedulingOptimizerConfigDTO,
    SchedulingProfileDTO,
    SchedulingResolvedConfigDTO,
)
from .requests import ScheduleGenerationRequestDTO, ScheduleRunRequestDTO
from .jobs import (
    ScheduleJobDetailDTO,
    ScheduleJobStatusDTO,
    ScheduleRequestAcceptedDTO,
    SchedulingExecutionContextDTO,
    SchedulingJobRequestDTO,
)
from .results import (
    AlgorithmRunMetricsDTO,
    DoctorWorkloadBalanceDTO,
    ParetoScheduleAssignmentsDTO,
    ParetoScheduleMetricsItemDTO,
    ParetoScheduleOptionDTO,
    ScheduleGenerationEnvelopeDTO,
    ScheduleGenerationResultDTO,
    ScheduleJobMetricsResponseDTO,
    ScheduleJobScheduleResponseDTO,
    ScheduleQualityMetricsDTO,
    ScheduleSliceDTO,
    ShiftAssignmentDTO,
)

__all__ = [
    "DoctorProfileDTO",
    "ScheduleGenerationRequestDTO",
    "ScheduleRunRequestDTO",
    "ScheduleJobDetailDTO",
    "ScheduleJobStatusDTO",
    "ScheduleRequestAcceptedDTO",
    "SchedulingExecutionContextDTO",
    "SchedulingJobRequestDTO",
    "AlgorithmRunMetricsDTO",
    "DoctorWorkloadBalanceDTO",
    "ParetoScheduleAssignmentsDTO",
    "ParetoScheduleMetricsItemDTO",
    "ParetoScheduleOptionDTO",
    "ScheduleGenerationEnvelopeDTO",
    "ScheduleGenerationResultDTO",
    "ScheduleJobMetricsResponseDTO",
    "ScheduleJobScheduleResponseDTO",
    "ScheduleQualityMetricsDTO",
    "ScheduleSliceDTO",
    "ShiftAssignmentDTO",
    "ScheduleProfileUpdateDTO",
    "SchedulingOptimizerConfigDTO",
    "SchedulingProfileDTO",
    "SchedulingResolvedConfigDTO",
]
