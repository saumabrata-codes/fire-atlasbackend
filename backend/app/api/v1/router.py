from fastapi import APIRouter

from app.api.v1.endpoints import analytics, anomalies, calendar, health, imagery, ingestion, observations, raw, reports, sensors

router = APIRouter()
for endpoint_router in (
    analytics.router,
    imagery.router,
    raw.router,
    health.router,
    observations.router,
    calendar.router,
    sensors.router,
    anomalies.router,
    reports.router,
    ingestion.router,
):
    router.include_router(endpoint_router)
