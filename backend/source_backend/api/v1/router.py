from fastapi import APIRouter

from source_backend.api.v1.endpoints import health, overview
from source_backend.api.v1.endpoints.map import router as map_router
from source_backend.api.v1.endpoints.sensors import router as sensors_router
from source_backend.api.v1.endpoints.calendar import router as calendar_router
from source_backend.api.v1.endpoints.report import router as report_router

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(overview.router)
api_router.include_router(map_router)
api_router.include_router(sensors_router)
api_router.include_router(calendar_router)
api_router.include_router(report_router)