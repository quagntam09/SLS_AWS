"""Cấu hình ứng dụng đọc từ biến môi trường (.env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Thông số cấu hình cho backend scheduling.

    Tất cả giá trị được đọc từ biến môi trường (prefix APP_) hoặc file .env.
    Không có magic number nào được hardcode trong code domain - thay đổi bằng env var.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="APP_",
        extra="ignore",
    )

    # --- Optimizer ---
    optimizer_population_size: int = Field(default=250, ge=50, le=500)
    optimizer_generations: int = Field(default=400, ge=50, le=800)
    pareto_options_limit: int = Field(default=6, ge=3, le=6)
    progress_update_interval: int = Field(default=50, ge=1, le=1000)
    randomization_strength: float = Field(default=0.08, ge=0.0, le=0.35)
    random_seed: int | None = None

    # --- Domain constraints ---
    # Độ dài mỗi ca trực (giờ). Thay đổi nếu bệnh viện điều chỉnh ca 6h hoặc 8h.
    shift_hours: float = Field(default=4.5, ge=1.0, le=24.0)
    # Số ngày liên tiếp tối đa được phép trực (SC-01).
    max_consecutive_days: int = Field(default=5, ge=1, le=14)

    # --- Storage ---
    # Prefix thư mục trong S3 bucket nơi lưu kết quả lịch.
    s3_result_prefix: str = Field(default="results")

    # --- API / Security ---
    cors_allow_origins: str = Field(default="http://localhost:3000")
    api_key: str | None = Field(default=None, description="API key tùy chọn để bảo vệ endpoint nghiệp vụ")
    env: str = Field(default="development", description="Môi trường chạy app")

    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "development", "local"}

    def requires_api_key(self) -> bool:
        return not self.is_dev()

    def get_api_key(self) -> str | None:
        value = (self.api_key or "").strip()
        return value or None


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Trả về singleton settings để tái sử dụng và test dễ dàng."""

    return AppSettings()
