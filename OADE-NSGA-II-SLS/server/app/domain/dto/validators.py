"""Shared validation helpers for schedule request DTOs."""

from __future__ import annotations

from typing import List

from ..schemas import DoctorProfileDTO


def ensure_unique_doctor_ids(doctors: List[DoctorProfileDTO]) -> List[DoctorProfileDTO]:
    ids = [doctor.id for doctor in doctors]
    if len(ids) != len(set(ids)):
        raise ValueError("Danh sách bác sĩ có id trùng")
    return doctors


def ensure_doctor_days_off_within_limit(
    doctors: List[DoctorProfileDTO],
    max_days_off_per_doctor: int,
) -> None:
    for doctor in doctors:
        unique_days_off = set(doctor.days_off)
        if len(unique_days_off) > max_days_off_per_doctor:
            raise ValueError(
                f"Bác sĩ {doctor.id} vượt quá số ngày nghỉ tối đa "
                f"({len(unique_days_off)} > {max_days_off_per_doctor})"
            )
