"""
Data models for schedule generation API.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class RequestStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Doctor:
    id: str
    name: str
    experiences: int
    department_id: str
    specialization: str
    days_off: List[str] = field(default_factory=list)
    preferred_extra_days: List[str] = field(default_factory=list)


@dataclass
class ScheduleMetrics:
    hard_violation_score: float = 0.0
    soft_violation_score: float = 0.0
    fairness_std: float = 0.0
    shift_fairness_std: float = 0.0
    day_off_fairness_std: float = 0.0
    day_off_fairness_jain: float = 0.0
    weekly_fairness_jain: float = 0.0
    monthly_fairness_jain: float = 0.0
    yearly_fairness_jain: float = 0.0
    holiday_fairness_jain: float = 0.0
    hard_score_visual: float = 0.0
    soft_score_visual: float = 0.0
    fairness_score_visual: float = 0.0
    overall_score_visual: float = 0.0
    score_badges: Dict[str, str] = field(default_factory=dict)
    weekly_underwork_doctors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShiftAssignment:
    date: str
    shift: str
    doctor_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DoctorWorkloadBalance:
    doctor_id: str
    doctor_name: str
    weekly_shift_count: int = 0
    monthly_shift_count: int = 0
    yearly_estimated_shift_count: int = 0
    holiday_shift_count: int = 0
    day_off_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParetoOption:
    option_id: str
    metrics: ScheduleMetrics = field(default_factory=ScheduleMetrics)
    assignments: List[ShiftAssignment] = field(default_factory=list)
    doctor_workload_balances: List[DoctorWorkloadBalance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "option_id": self.option_id,
            "metrics": self.metrics.to_dict(),
            "assignments": [a.to_dict() for a in self.assignments],
            "doctor_workload_balances": [b.to_dict() for b in self.doctor_workload_balances],
        }


@dataclass
class AlgorithmRunMetrics:
    elapsed_seconds: float = 0.0
    n_generations: int = 0
    population_size: int = 0
    pareto_front_size: int = 0
    best_hard_objective: float = 0.0
    best_balance_objective: float = 0.0
    convergence_hard_ratio: float = 0.0
    convergence_balance_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScheduleResult:
    selected_option_id: str = ""
    selected_schedule: Optional[Dict[str, Any]] = None
    pareto_options: List[ParetoOption] = field(default_factory=list)
    algorithm_run_metrics: AlgorithmRunMetrics = field(default_factory=AlgorithmRunMetrics)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_option_id": self.selected_option_id,
            "selected_schedule": self.selected_schedule or {},
            "pareto_options": [opt.to_dict() for opt in self.pareto_options],
            "algorithm_run_metrics": self.algorithm_run_metrics.to_dict(),
        }


@dataclass
class ScheduleRequest:
    start_date: str
    num_days: int
    max_weekly_hours_per_doctor: int
    max_days_off_per_doctor: int
    required_doctors_per_shift: int
    shifts_per_day: int
    doctors: List[Doctor]
    holiday_dates: List[str] = field(default_factory=list)
    pareto_options_limit: int = 6


@dataclass
class ProgressResponse:
    request_id: str
    status: RequestStatus
    progress_percent: float = 0.0
    message: str = ""
    result: Optional[ScheduleResult] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "message": self.message,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
        }
