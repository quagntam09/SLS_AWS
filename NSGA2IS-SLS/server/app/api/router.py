"""
Router tổng hợp cho toàn bộ API của hệ thống.
"""

from fastapi import APIRouter

from .v1.scheduling import profile_router as schedule_profile_router
from .v1.scheduling import router as scheduling_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(scheduling_router)
api_router.include_router(schedule_profile_router)
