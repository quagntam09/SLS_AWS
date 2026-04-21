"""Chuẩn hóa request xếp lịch theo request/profile/default."""

from __future__ import annotations

from typing import Any

from ...core.settings import AppSettings, get_settings
from ...domain.dto import (
    ScheduleGenerationRequestDTO,
    ScheduleRunRequestDTO,
    SchedulingJobRequestDTO,
    SchedulingOptimizerConfigDTO,
    SchedulingProfileDTO,
    SchedulingResolvedConfigDTO,
)
from .scheduling_profile_registry import SchedulingProfileRegistry, get_profile_registry


def _resolve_numeric_override(
    override_value: Any,
    profile_value: Any,
    default_value: Any,
) -> Any:
    if override_value is not None:
        return override_value
    if profile_value is not None:
        return profile_value
    return default_value


def _resolve_profile(
    request: ScheduleRunRequestDTO,
    registry: SchedulingProfileRegistry,
) -> SchedulingProfileDTO:
    return registry.resolve_profile(profile_id=request.profile_id, schedule_type=request.schedule_type)


def _profile_allows_override(profile: SchedulingProfileDTO, field_name: str) -> bool:
    if field_name in profile.locked_fields:
        return False
    if profile.allowed_override_fields and field_name not in profile.allowed_override_fields:
        return False
    return True


def resolve_scheduling_job_request(
    request: ScheduleRunRequestDTO,
    settings: AppSettings | None = None,
    registry: SchedulingProfileRegistry | None = None,
) -> SchedulingJobRequestDTO:
    """Merge legacy request overrides with profile and server defaults."""

    resolved_settings = settings or get_settings()
    resolved_registry = registry or get_profile_registry()
    resolved_profile = _resolve_profile(request, resolved_registry)

    response_profile = (
        request.response_profile if _profile_allows_override(resolved_profile, "response_profile") else None
    ) or resolved_profile.response_profile or "legacy"
    schedule_type = (
        request.schedule_type if _profile_allows_override(resolved_profile, "schedule_type") else None
    ) or resolved_profile.schedule_type or "legacy"

    optimizer_population_size = (
        request.optimizer_population_size if _profile_allows_override(resolved_profile, "optimizer_population_size") else None
    )
    optimizer_generations = (
        request.optimizer_generations if _profile_allows_override(resolved_profile, "optimizer_generations") else None
    )
    random_seed = request.random_seed if _profile_allows_override(resolved_profile, "random_seed") else None
    randomization_strength = (
        request.randomization_strength if _profile_allows_override(resolved_profile, "randomization_strength") else None
    )
    pareto_options_limit = (
        request.pareto_options_limit if _profile_allows_override(resolved_profile, "pareto_options_limit") else None
    )

    optimizer = SchedulingOptimizerConfigDTO(
        population_size=_resolve_numeric_override(
            optimizer_population_size,
            resolved_profile.optimizer_population_size,
            resolved_settings.optimizer_population_size,
        ),
        generations=_resolve_numeric_override(
            optimizer_generations,
            resolved_profile.optimizer_generations,
            resolved_settings.optimizer_generations,
        ),
        random_seed=_resolve_numeric_override(
            random_seed,
            resolved_profile.random_seed,
            resolved_settings.random_seed,
        ),
        randomization_strength=_resolve_numeric_override(
            randomization_strength,
            resolved_profile.randomization_strength,
            resolved_settings.randomization_strength,
        ),
        pareto_options_limit=_resolve_numeric_override(
            pareto_options_limit,
            resolved_profile.pareto_options_limit,
            resolved_settings.pareto_options_limit,
        ),
    )

    resolved_config = SchedulingResolvedConfigDTO(
        schedule_type=schedule_type,
        profile_id=resolved_profile.profile_id,
        profile_version=resolved_profile.profile_version,
        rule_version=resolved_profile.rule_version,
        response_profile=response_profile,
        optimizer=optimizer,
        metadata={**resolved_profile.metadata, **request.metadata},
        business_constraints={**request.business_constraints},
    )

    return SchedulingJobRequestDTO(
        schedule_type=schedule_type,
        profile_id=resolved_profile.profile_id,
        tenant_id=request.tenant_id,
        department_id=request.department_id,
        response_profile=response_profile,
        business_request=request.model_copy(deep=True),
        resolved_profile=resolved_profile,
        resolved_config=resolved_config,
        metadata={**request.metadata, "profile_rule_version": resolved_profile.rule_version},
    )


def resolve_generation_request(
    request: ScheduleRunRequestDTO | SchedulingJobRequestDTO,
    settings: AppSettings | None = None,
    registry: SchedulingProfileRegistry | None = None,
) -> ScheduleGenerationRequestDTO:
    """Convert a legacy or normalized request into the core algorithm DTO."""

    if isinstance(request, SchedulingJobRequestDTO):
        normalized_request = request.business_request
        resolved_profile = request.resolved_profile
        resolved_config = request.resolved_config
    else:
        job_request = resolve_scheduling_job_request(request, settings=settings, registry=registry)
        normalized_request = job_request.business_request
        resolved_profile = job_request.resolved_profile
        resolved_config = job_request.resolved_config

    return ScheduleGenerationRequestDTO(
        start_date=normalized_request.start_date,
        num_days=normalized_request.num_days,
        max_weekly_hours_per_doctor=normalized_request.max_weekly_hours_per_doctor,
        max_days_off_per_doctor=normalized_request.max_days_off_per_doctor,
        rooms_per_shift=normalized_request.rooms_per_shift,
        doctors_per_room=normalized_request.doctors_per_room,
        shifts_per_day=normalized_request.shifts_per_day,
        doctors=normalized_request.doctors,
        random_seed=resolved_config.optimizer.random_seed,
        randomization_strength=resolved_config.optimizer.randomization_strength,
        optimizer_population_size=resolved_config.optimizer.population_size,
        optimizer_generations=resolved_config.optimizer.generations,
        pareto_options_limit=resolved_config.optimizer.pareto_options_limit,
        schedule_type=resolved_config.schedule_type,
        profile_id=resolved_profile.profile_id,
        tenant_id=request.tenant_id if isinstance(request, SchedulingJobRequestDTO) else normalized_request.tenant_id,
        department_id=request.department_id if isinstance(request, SchedulingJobRequestDTO) else normalized_request.department_id,
        response_profile=resolved_config.response_profile,
        business_constraints=resolved_config.business_constraints,
        metadata=resolved_config.metadata,
    )
