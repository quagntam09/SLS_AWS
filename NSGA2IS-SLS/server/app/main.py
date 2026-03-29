"""
Entrypoint FastAPI cho hệ thống lập lịch ca trực bác sĩ.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from .api.router import api_router
from .config import get_settings

logger = logging.getLogger("uvicorn.error")


def _resolve_root_path() -> str:
    root_path = os.getenv("ROOT_PATH", "").strip()
    if not root_path:
        return ""
    if not root_path.startswith("/"):
        root_path = f"/{root_path}"
    return root_path.rstrip("/") if root_path != "/" else root_path


def _resolve_cors_origins() -> list[str]:
    raw_origins = get_settings().cors_allow_origins
    origins: list[str] = []

    for origin in raw_origins.split(","):
        candidate = origin.strip()
        if not candidate:
            continue
        if candidate == "*":
            raise RuntimeError("APP_CORS_ALLOW_ORIGINS must not contain wildcard '*'")

        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(f"Invalid CORS origin: {candidate}")
        if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            raise RuntimeError(f"CORS origin must not include a path, query, or fragment: {candidate}")

        origins.append(f"{parsed.scheme}://{parsed.netloc}")

    if not origins:
        raise RuntimeError("APP_CORS_ALLOW_ORIGINS must define at least one valid origin")

    return origins

app = FastAPI(
    title="Doctor Duty Scheduling API",
    description="API lập lịch ca trực bác sĩ bằng NSGA-II cải tiến",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path=_resolve_root_path(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def log_env_settings_on_startup() -> None:
    """Log cấu hình đọc từ .env khi chạy môi trường dev."""
    settings = get_settings()
    if not settings.is_dev():
        return

    logger.info("[DEV] APP_ENV=%s", settings.env)
    logger.info("[DEV] APP_OPTIMIZER_POPULATION_SIZE=%s", settings.optimizer_population_size)
    logger.info("[DEV] APP_OPTIMIZER_GENERATIONS=%s", settings.optimizer_generations)
    logger.info("[DEV] APP_PARETO_OPTIONS_LIMIT=%s", settings.pareto_options_limit)
    logger.info("[DEV] APP_RANDOMIZATION_STRENGTH=%s", settings.randomization_strength)
    logger.info("[DEV] APP_RANDOM_SEED=%s", settings.random_seed)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)


@app.exception_handler(Exception)
def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"},
    )

# AWS Lambda entrypoint for API Gateway HTTP API events.
handler = Mangum(app, lifespan="off", api_gateway_base_path="/dev")
