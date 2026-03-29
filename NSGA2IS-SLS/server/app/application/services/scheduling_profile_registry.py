"""Registry lưu trữ profile xếp lịch cho legacy, general, department và custom."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List

from ...domain.dto import SchedulingProfileDTO, ScheduleProfileUpdateDTO

PROFILE_STORE_ENV = "APP_SCHEDULE_PROFILE_STORE_PATH"
DEFAULT_PROFILE_STORE_PATH = ".scheduling_profiles.json"

_DEFAULT_PROFILES: tuple[SchedulingProfileDTO, ...] = (
    SchedulingProfileDTO(
        profile_id="legacy",
        schedule_type="legacy",
        profile_version="1.0.0",
        rule_version="1.0.0",
        description="Legacy profile preserving the current API behaviour.",
        response_profile="legacy",
        optimizer_population_size=250,
        optimizer_generations=400,
        random_seed=None,
        randomization_strength=0.08,
        pareto_options_limit=6,
        allowed_override_fields=[
            "optimizer_population_size",
            "optimizer_generations",
            "random_seed",
            "randomization_strength",
            "pareto_options_limit",
            "response_profile",
        ],
        locked_fields=["schedule_type"],
        metadata={"is_default": True},
    ),
    SchedulingProfileDTO(
        profile_id="hospital_general_day_shift",
        schedule_type="general",
        profile_version="1.0.0",
        rule_version="1.0.0",
        description="General-purpose scheduling profile for day-focused hospitals.",
        response_profile="detailed",
        optimizer_population_size=300,
        optimizer_generations=450,
        random_seed=None,
        randomization_strength=0.08,
        pareto_options_limit=6,
        allowed_override_fields=[
            "optimizer_population_size",
            "optimizer_generations",
            "random_seed",
            "randomization_strength",
            "pareto_options_limit",
            "response_profile",
        ],
        locked_fields=["schedule_type"],
        metadata={"is_default": True},
    ),
    SchedulingProfileDTO(
        profile_id="department_custom_fairness",
        schedule_type="department",
        profile_version="1.0.0",
        rule_version="1.0.0",
        description="Department-level profile with fairness-oriented defaults.",
        response_profile="compact",
        optimizer_population_size=250,
        optimizer_generations=400,
        random_seed=None,
        randomization_strength=0.1,
        pareto_options_limit=6,
        allowed_override_fields=[
            "optimizer_population_size",
            "optimizer_generations",
            "random_seed",
            "randomization_strength",
            "pareto_options_limit",
            "response_profile",
        ],
        locked_fields=["schedule_type"],
        metadata={"is_default": True},
    ),
    SchedulingProfileDTO(
        profile_id="night_shift_priority",
        schedule_type="custom",
        profile_version="1.0.0",
        rule_version="1.0.0",
        description="Custom profile optimized for night shift prioritization.",
        response_profile="detailed",
        optimizer_population_size=350,
        optimizer_generations=500,
        random_seed=None,
        randomization_strength=0.12,
        pareto_options_limit=8,
        allowed_override_fields=[
            "optimizer_population_size",
            "optimizer_generations",
            "random_seed",
            "randomization_strength",
            "pareto_options_limit",
            "response_profile",
        ],
        locked_fields=["schedule_type"],
        metadata={"is_default": True},
    ),
)


class SchedulingProfileRegistry:
    """Simple file-backed profile registry with built-in defaults."""

    def __init__(self, store_path: str | Path | None = None) -> None:
        resolved_path = store_path or os.getenv(PROFILE_STORE_ENV) or DEFAULT_PROFILE_STORE_PATH
        self.store_path = Path(resolved_path)
        self._lock = RLock()
        self._profiles: Dict[str, SchedulingProfileDTO] | None = None

    def _load_defaults(self) -> Dict[str, SchedulingProfileDTO]:
        return {profile.profile_id: profile for profile in _DEFAULT_PROFILES}

    def _load_from_disk(self) -> Dict[str, SchedulingProfileDTO]:
        if not self.store_path.is_file():
            return self._load_defaults()

        raw_data = json.loads(self.store_path.read_text(encoding="utf-8"))
        if not isinstance(raw_data, list):
            raise ValueError("Schedule profile store must contain a JSON list")

        profiles: Dict[str, SchedulingProfileDTO] = {}
        for item in raw_data:
            profile = SchedulingProfileDTO.model_validate(item)
            profiles[profile.profile_id] = profile

        for default_profile in self._load_defaults().values():
            profiles.setdefault(default_profile.profile_id, default_profile)

        return profiles

    def _ensure_loaded(self) -> Dict[str, SchedulingProfileDTO]:
        with self._lock:
            if self._profiles is None:
                self._profiles = self._load_from_disk()
            return self._profiles

    def _persist(self) -> None:
        with self._lock:
            profiles = self._ensure_loaded()
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [profile.model_dump(mode="json") for profile in sorted(profiles.values(), key=lambda item: item.profile_id)]
            self.store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_profiles(self) -> List[SchedulingProfileDTO]:
        profiles = self._ensure_loaded()
        return sorted(profiles.values(), key=lambda profile: profile.profile_id)

    def get_profile(self, profile_id: str | None) -> SchedulingProfileDTO | None:
        if not profile_id:
            return None

        profiles = self._ensure_loaded()
        profile = profiles.get(profile_id)
        if profile is not None:
            return profile

        for candidate in profiles.values():
            if candidate.schedule_type == profile_id:
                return candidate

        return None

    def resolve_profile(
        self,
        profile_id: str | None = None,
        schedule_type: str | None = None,
    ) -> SchedulingProfileDTO:
        candidate = self.get_profile(profile_id)
        if candidate is not None:
            return candidate

        if schedule_type:
            schedule_profile = self.get_profile(schedule_type)
            if schedule_profile is not None:
                return schedule_profile

        return self.get_profile("legacy") or next(iter(self._ensure_loaded().values()))

    def upsert_profile(self, profile: SchedulingProfileDTO) -> SchedulingProfileDTO:
        with self._lock:
            profiles = self._ensure_loaded()
            profiles[profile.profile_id] = profile
            self._persist()
            return profile

    def update_profile(self, profile_id: str, patch: ScheduleProfileUpdateDTO) -> SchedulingProfileDTO:
        with self._lock:
            profiles = self._ensure_loaded()
            current = profiles.get(profile_id)
            if current is None:
                raise KeyError(profile_id)

            update_data: Dict[str, Any] = patch.model_dump(exclude_unset=True)
            updated = current.model_copy(update=update_data)
            profiles[profile_id] = updated
            self._persist()
            return updated


_registry: SchedulingProfileRegistry | None = None


def get_profile_registry() -> SchedulingProfileRegistry:
    """Return a process-local singleton registry."""

    global _registry
    if _registry is None:
        _registry = SchedulingProfileRegistry()
    return _registry


def list_default_profile_ids() -> Iterable[str]:
    return tuple(profile.profile_id for profile in _DEFAULT_PROFILES)
