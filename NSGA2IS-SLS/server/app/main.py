"""
Entrypoint FastAPI cho hệ thống lập lịch ca trực bác sĩ.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from app.api.router import api_router
from app.config import get_settings

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Doctor Duty Scheduling API",
    description="API lập lịch ca trực bác sĩ bằng NSGA-II cải tiến",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in get_settings().cors_allow_origins.split(",")
        if origin.strip()
    ],
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
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# AWS Lambda entrypoint for API Gateway HTTP API events.
handler = Mangum(app)
