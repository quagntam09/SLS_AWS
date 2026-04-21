"""Ràng buộc cứng và cơ chế repair cho bài toán xếp lịch."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .dto import ScheduleGenerationRequestDTO
from ..core.settings import get_settings as _get_settings

SHIFT_NAMES = ("morning", "afternoon")
# Độ dài ca được đọc từ settings (APP_SHIFT_HOURS). Default 4.5h khi không cấu hình.
SHIFT_HOURS: float = _get_settings().shift_hours


# ---------------------------------------------------------------------------
# HARD CONSTRAINTS - Được đảm bảo 100% ngay từ validation
# ---------------------------------------------------------------------------

def _validate_hard_constraints(request: ScheduleGenerationRequestDTO) -> None:
    """
    Kiểm tra tất cả hard constraints.
    Nếu bất kỳ ràng buộc nào bị vi phạm, raise ValueError ngay lập tức.
    KHÔNG DÙNG PENALTY CHO HARD CONSTRAINTS.
    """
    period_start = request.start_date
    period_end = request.start_date + timedelta(days=request.num_days - 1)

    doctors_per_shift = request.rooms_per_shift * request.doctors_per_room

    if len(request.doctors) < doctors_per_shift:
        raise ValueError(
            f"[HC-01] Số bác sĩ ({len(request.doctors)}) không đủ cho mỗi ca. "
            f"Cần tối thiểu {doctors_per_shift} bác sĩ/ca "
            f"({request.rooms_per_shift} phòng × {request.doctors_per_room} BS/phòng)."
        )

    shifts_per_week = 7 * request.shifts_per_day
    max_weekly_shifts = request.max_weekly_hours_per_doctor / SHIFT_HOURS
    total_shifts_per_week = shifts_per_week * doctors_per_shift
    min_doctors_needed = total_shifts_per_week / max_weekly_shifts

    if len(request.doctors) < min_doctors_needed:
        raise ValueError(
            f"[HC-02] Số bác sĩ ({len(request.doctors)}) không đủ để đáp ứng giới hạn "
            f"{request.max_weekly_hours_per_doctor}h/tuần (tương đương {max_weekly_shifts:.1f} ca/tuần). "
            f"Cần ít nhất {int(np.ceil(min_doctors_needed))} bác sĩ để phân bổ workload "
            f"({total_shifts_per_week:.0f} ca/tuần)."
        )

    for doctor in request.doctors:
        days_off_in_period = [
            d for d in doctor.days_off
            if period_start <= d <= period_end
        ]
        if len(days_off_in_period) > request.max_days_off_per_doctor:
            raise ValueError(
                f"[HC-03] Bác sĩ '{doctor.name}' đăng ký {len(days_off_in_period)} ngày nghỉ "
                f"trong kỳ, vượt giới hạn {request.max_days_off_per_doctor} ngày."
            )

    interns = [d for d in request.doctors if d.experiences < 2]
    supervisors = [d for d in request.doctors if d.experiences >= 2 and d.has_valid_license]

    if interns and not supervisors:
        raise ValueError(
            f"[HC-04] Có {len(interns)} bác sĩ thực tập (kinh nghiệm < 2 năm) "
            f"nhưng không có bác sĩ chính thức (kinh nghiệm >= 2 năm) để giám sát."
        )

    doctors_without_license = [d for d in request.doctors if not d.has_valid_license]
    if doctors_without_license and len(doctors_without_license) == len(request.doctors):
        raise ValueError(
            f"[HC-05] Tất cả {len(request.doctors)} bác sĩ đều không có license hợp lệ, "
            f"không thể lập lịch trực."
        )

    for doctor in request.doctors:
        days_off_set = set(doctor.days_off)
        preferred_in_days_off = [d for d in doctor.preferred_extra_days if d in days_off_set]
        if preferred_in_days_off:
            raise ValueError(
                f"[HC-06] Bác sĩ '{doctor.name}' có ngày muốn trực thêm {preferred_in_days_off} "
                f"trùng với ngày nghỉ đã đăng ký."
            )

    total_shifts = request.num_days * request.shifts_per_day * doctors_per_shift
    avg_shifts_per_doctor = total_shifts / len(request.doctors)
    avg_hours_per_doctor = avg_shifts_per_doctor * SHIFT_HOURS

    if avg_hours_per_doctor > request.max_weekly_hours_per_doctor * (request.num_days / 7):
        raise ValueError(
            f"[HC-07] Workload trung bình mỗi bác sĩ: {avg_hours_per_doctor:.1f}h/kỳ "
            f"tương đương {(avg_hours_per_doctor * 7 / request.num_days):.1f}h/tuần, "
            f"vượt giới hạn {request.max_weekly_hours_per_doctor}h/tuần. "
            f"Cần tăng số bác sĩ hoặc giảm số ca."
        )

    if request.rooms_per_shift < 1:
        raise ValueError(f"[HC-08] Số phòng mỗi ca phải >= 1, hiện tại: {request.rooms_per_shift}")

    if request.doctors_per_room < 1:
        raise ValueError(f"[HC-08] Số bác sĩ mỗi phòng phải >= 1, hiện tại: {request.doctors_per_room}")

    if request.shifts_per_day not in [1, 2]:
        raise ValueError(
            f"[HC-09] Số ca mỗi ngày phải là 1 hoặc 2, hiện tại: {request.shifts_per_day}"
        )

    if request.num_days < 1 or request.num_days > 31:
        raise ValueError(
            f"[HC-10] Số ngày lập lịch phải từ 1 đến 31, hiện tại: {request.num_days}"
        )


# ---------------------------------------------------------------------------
# HARD CONSTRAINT MANAGER - Repair trong quá trình tối ưu
# ---------------------------------------------------------------------------

@dataclass
class DoctorConstraints:
    """Container for doctor constraints."""

    idx: int
    doctor_id: str
    has_license: bool
    is_intern: bool
    specialization: str
    forbidden_days: Set[int]
    preferred_extra_count: int


class HardConstraintManager:
    """
    Quản lý và đảm bảo các ràng buộc cứng trong quá trình tối ưu.
    Các ràng buộc đã được kiểm tra ở validation, ở đây chỉ repair các vi phạm
    phát sinh do mutation/crossover.
    """

    def __init__(self, request: ScheduleGenerationRequestDTO):
        self.request = request
        self.n_doctors = len(request.doctors)
        self.rooms = request.rooms_per_shift
        self.dproom = request.doctors_per_room
        self.n_days = request.num_days
        self.n_shifts = len(SHIFT_NAMES[:request.shifts_per_day])
        self.max_weekly_hours = request.max_weekly_hours_per_doctor

        self.doctor_id_to_idx = {d.id: idx for idx, d in enumerate(request.doctors)}
        self.doctor_idx_to_id = [d.id for d in request.doctors]

        self.doctors: List[DoctorConstraints] = []
        period_start = request.start_date

        for idx, doctor in enumerate(request.doctors):
            forbidden_days = set()
            for day_off in doctor.days_off:
                if period_start <= day_off < period_start + timedelta(days=request.num_days):
                    day_idx = (day_off - period_start).days
                    forbidden_days.add(day_idx)

            pref_in_period = len(
                [
                    d
                    for d in doctor.preferred_extra_days
                    if period_start <= d < period_start + timedelta(days=request.num_days)
                ]
            )
            self.doctors.append(DoctorConstraints(
                idx=idx,
                doctor_id=doctor.id,
                has_license=doctor.has_valid_license,
                is_intern=doctor.is_intern,
                specialization=doctor.specialization,
                forbidden_days=forbidden_days,
                preferred_extra_count=pref_in_period,
            ))

        self.specialists: Dict[str, List[int]] = defaultdict(list)
        for doc in self.doctors:
            self.specialists[doc.specialization].append(doc.idx)

    def repair(self, assignment: Dict[Tuple[int, int, int], List[int]]) -> Dict[Tuple[int, int, int], List[int]]:
        """Repair assignment để đảm bảo tất cả hard constraints."""
        repaired = {k: list(v) for k, v in assignment.items()}
        repaired = self._repair_forbidden_days(repaired)
        repaired = self._repair_duplicates(repaired)
        repaired = self._repair_intern_supervisors(repaired)
        repaired = self._repair_licenses(repaired)
        repaired = self._repair_room_capacity(repaired)
        repaired = self._rebalance_avoidable_zero_shifts(repaired)
        return repaired

    def _compute_shift_counts(self, assignment: Dict[Tuple[int, int, int], List[int]]) -> np.ndarray:
        """Đếm số ca hiện tại của từng bác sĩ (theo slot ngày-ca, không nhân số phòng)."""
        counts = np.zeros(self.n_doctors, dtype=np.int32)
        seen_slots = [set() for _ in range(self.n_doctors)]

        for (day_idx, shift_idx, _room_idx), doctors in assignment.items():
            shift_slot = day_idx * self.n_shifts + shift_idx
            for doctor_idx in doctors:
                if shift_slot not in seen_slots[doctor_idx]:
                    seen_slots[doctor_idx].add(shift_slot)
                    counts[doctor_idx] += 1

        return counts

    def _repair_forbidden_days(self, assignment: Dict) -> Dict:
        """Thay thế bác sĩ bị xếp vào ngày nghỉ."""
        for (day_idx, shift_idx, room_idx), doctors in assignment.items():
            for i, doctor_idx in enumerate(doctors):
                if day_idx in self.doctors[doctor_idx].forbidden_days:
                    replacement = self._find_replacement(
                        assignment,
                        day_idx, shift_idx, room_idx,
                        set(doctors), {day_idx}
                    )
                    if replacement is not None:
                        doctors[i] = replacement
        return assignment

    def _repair_duplicates(self, assignment: Dict) -> Dict:
        """Loại bỏ bác sĩ trùng trong cùng ca."""
        shift_doctors: Dict[Tuple[int, int], List[Tuple[int, int, int, int]]] = defaultdict(list)

        for (day_idx, shift_idx, room_idx), doctors in assignment.items():
            for pos, doctor_idx in enumerate(doctors):
                shift_doctors[(day_idx, shift_idx)].append((doctor_idx, room_idx, pos, day_idx))

        for (day_idx, shift_idx), slots in shift_doctors.items():
            shift_doctor_ids = {doctor_idx for doctor_idx, _room_idx, _pos, _ in slots}
            seen = set()
            duplicates = []

            for doctor_idx, room_idx, pos, _ in slots:
                if doctor_idx in seen:
                    duplicates.append((doctor_idx, room_idx, pos, day_idx))
                else:
                    seen.add(doctor_idx)

            for doctor_idx, room_idx, pos, day_idx in duplicates:
                doctors_list = assignment[(day_idx, shift_idx, room_idx)]
                replacement = self._find_replacement(
                    assignment,
                    day_idx, shift_idx, room_idx,
                    set(doctors_list) | shift_doctor_ids, {day_idx}
                )
                if replacement is not None:
                    doctors_list[pos] = replacement

        return assignment

    def _repair_intern_supervisors(self, assignment: Dict) -> Dict:
        """Đảm bảo mỗi intern có supervisor trong cùng ca."""
        for (day_idx, shift_idx, room_idx), doctors in assignment.items():
            has_supervisor = any(not self.doctors[d].is_intern for d in doctors)
            interns = [d for d in doctors if self.doctors[d].is_intern]

            if interns and not has_supervisor:
                supervisor = self._find_supervisor(assignment, day_idx, shift_idx, room_idx, set(doctors))
                if supervisor is not None:
                    idx = doctors.index(interns[0])
                    doctors[idx] = supervisor

        return assignment

    def _repair_licenses(self, assignment: Dict) -> Dict:
        """Thay thế bác sĩ không có license."""
        for (day_idx, shift_idx, room_idx), doctors in assignment.items():
            for i, doctor_idx in enumerate(doctors):
                if not self.doctors[doctor_idx].has_license:
                    replacement = self._find_replacement(
                        assignment,
                        day_idx, shift_idx, room_idx,
                        set(doctors), {day_idx},
                        require_license=True
                    )
                    if replacement is not None:
                        doctors[i] = replacement
        return assignment

    def _repair_room_capacity(self, assignment: Dict) -> Dict:
        """Điều chỉnh số lượng bác sĩ mỗi phòng đúng yêu cầu."""
        for (day_idx, shift_idx, room_idx), doctors in assignment.items():
            current = len(doctors)
            target = self.dproom

            if current < target:
                existing = set(doctors)
                for _ in range(target - current):
                    new_doctor = self._find_replacement(
                        assignment,
                        day_idx, shift_idx, room_idx,
                        existing, {day_idx}
                    )
                    if new_doctor is not None:
                        doctors.append(new_doctor)
                        existing.add(new_doctor)

            elif current > target:
                doctors.sort(key=lambda d: (
                    not self.doctors[d].has_license,
                    self.doctors[d].is_intern
                ))
                del doctors[target:]

        return assignment

    def _rebalance_avoidable_zero_shifts(self, assignment: Dict) -> Dict:
        """Giảm bác sĩ 0 ca có thể tránh bằng hoán đổi từ bác sĩ đang quá tải."""
        unavoidable_zeros = max(0, self.n_doctors - (self.n_days * self.n_shifts * self.rooms * self.dproom))

        for _ in range(self.n_doctors):
            counts = self._compute_shift_counts(assignment)
            zero_docs = [idx for idx, c in enumerate(counts) if c == 0]
            if len(zero_docs) <= unavoidable_zeros:
                break

            overloaded = np.argsort(-counts)
            improved = False

            for zero_doc in zero_docs:
                for donor in overloaded:
                    if donor == zero_doc or counts[donor] <= 1:
                        continue

                    for (day_idx, shift_idx, room_idx), doctors in assignment.items():
                        if donor not in doctors:
                            continue
                        if zero_doc in doctors:
                            continue
                        if day_idx in self.doctors[zero_doc].forbidden_days:
                            continue

                        pos = doctors.index(donor)
                        doctors[pos] = zero_doc

                        assignment = self._repair_intern_supervisors(assignment)
                        assignment = self._repair_licenses(assignment)
                        assignment = self._repair_duplicates(assignment)

                        improved = True
                        break

                    if improved:
                        break

                if improved:
                    break

            if not improved:
                break

        return assignment

    def _find_replacement(
        self,
        assignment: Dict,
        day_idx: int,
        shift_idx: int,
        room_idx: int,
        excluded: Set[int],
        available_days: Set[int],
        require_license: bool = False,
    ) -> Optional[int]:
        """Tìm bác sĩ thay thế phù hợp."""
        candidates = []

        for doctor in self.doctors:
            if doctor.idx in excluded:
                continue
            if available_days and day_idx not in available_days:
                continue
            if day_idx in doctor.forbidden_days:
                continue
            if require_license and not doctor.has_license:
                continue
            candidates.append(doctor.idx)

        if not candidates:
            for doctor in self.doctors:
                if doctor.idx not in excluded:
                    if available_days and day_idx not in available_days:
                        continue
                    candidates.append(doctor.idx)

        if any(self.doctors[e].is_intern for e in excluded):
            supervisors = [c for c in candidates if not self.doctors[c].is_intern]
            if supervisors:
                candidates = supervisors

        if not candidates:
            return None

        counts = self._compute_shift_counts(assignment)
        return min(candidates, key=lambda c: (counts[c], c))

    def _find_supervisor(
        self,
        assignment: Dict,
        day_idx: int,
        shift_idx: int,
        room_idx: int,
        excluded: Set[int],
    ) -> Optional[int]:
        """Tìm supervisor khả dụng."""
        candidates: List[int] = []
        for doctor in self.doctors:
            if doctor.idx in excluded:
                continue
            if day_idx in doctor.forbidden_days:
                continue
            if not doctor.has_license:
                continue
            if doctor.is_intern:
                continue
            candidates.append(doctor.idx)

        if not candidates:
            return None

        counts = self._compute_shift_counts(assignment)
        return min(candidates, key=lambda c: (counts[c], c))
