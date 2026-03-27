"""Validation sớm cho payload lập lịch trực trước khi đẩy job vào queue."""

from __future__ import annotations

from fastapi import HTTPException, status as http_status

from ...domain.schemas import ScheduleRunRequestDTO


HOURS_PER_SHIFT = 8
WEEKS_PER_SCHEDULE = 7


def validate_schedule_feasibility(request_data: ScheduleRunRequestDTO) -> None:
    """Validate payload theo các giới hạn khả thi tối thiểu của hệ thống."""

    daily_demand_slots = (
        request_data.shifts_per_day
        * request_data.rooms_per_shift
        * request_data.doctors_per_room
    )
    total_doctors = len(request_data.doctors)
    weekly_hours_needed = daily_demand_slots * WEEKS_PER_SCHEDULE * HOURS_PER_SHIFT
    max_weekly_capacity = total_doctors * request_data.max_weekly_hours_per_doctor

    violations: list[str] = []

    if daily_demand_slots > total_doctors:
        violations.append(
            "Daily Headcount Check failed: "
            f"cần {daily_demand_slots} bác sĩ/ngày nhưng chỉ có {total_doctors} bác sĩ."
        )

    if weekly_hours_needed > max_weekly_capacity:
        violations.append(
            "Weekly Hours Check failed: "
            f"cần {weekly_hours_needed} giờ/tuần nhưng quỹ tối đa chỉ là "
            f"{max_weekly_capacity} giờ/tuần."
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
                    },
                    "weekly_hours": {
                        "weekly_hours_needed": weekly_hours_needed,
                        "max_weekly_capacity": max_weekly_capacity,
                        "passed": weekly_hours_needed <= max_weekly_capacity,
                    },
                },
            },
        )
