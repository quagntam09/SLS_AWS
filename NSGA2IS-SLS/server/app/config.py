"""Cau hinh ung dung doc tu bien moi truong (.env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Thong so cau hinh cho backend scheduling."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="APP_",
        extra="ignore",
    )

    optimizer_population_size: int = Field(default=250, ge=50, le=500)
    optimizer_generations: int = Field(default=400, ge=50, le=800)
    pareto_options_limit: int = Field(default=6, ge=3, le=6)
    progress_update_interval: int = Field(default=50, ge=1, le=1000)
    randomization_strength: float = Field(default=0.08, ge=0.0, le=0.35)
    random_seed: int | None = None
    cors_allow_origins: str = Field(default="http://localhost:3000")
    api_key: str | None = Field(default=None, description="API key tuy chon de bao ve endpoint nghiep vu")
    env: str = Field(default="development", description="Môi trường chạy app")

    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "development", "local"}


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Tra ve singleton settings de tai su dung va test de dang."""

    return AppSettings()
