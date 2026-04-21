"""Validation sớm cho payload lập lịch trực trước khi đẩy job vào queue."""

from __future__ import annotations

from fastapi import HTTPException, status as http_status

from ...domain.schemas import ScheduleRunRequestDTO


def validate_schedule_feasibility(request_data: ScheduleRunRequestDTO) -> None:
    """Validate payload theo các giới hạn khả thi tối thiểu của hệ thống."""

    daily_demand_slots = (
        request_data.shifts_per_day
        * request_data.rooms_per_shift
        * request_data.doctors_per_room
    )
    total_doctors = len(request_data.doctors)

    violations: list[str] = []

    if daily_demand_slots > total_doctors:
        violations.append(
            "Daily Headcount Check failed: "
            f"cần {daily_demand_slots} bác sĩ/ngày nhưng chỉ có {total_doctors} bác sĩ."
        )

    if violations:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Payload không khả thi để xếp lịch trực.",
                "violations": violations,
                "checks": {
                    "daily_headcount": {
                        "daily_demand_slots": daily_demand_slots,
                        "total_doctors": total_doctors,
                        "passed": daily_demand_slots <= total_doctors,
                    }
                },
            },
        )
