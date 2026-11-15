
from fastapi import APIRouter

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.sensors import SensorComparisonResponse
from source_backend.application.sensor_comparison_service import (
    build_sensor_comparison,
)


router = APIRouter()


@router.post(
    "/sensors",
    response_model=SensorComparisonResponse,
    summary="Get MODIS and VIIRS sensor comparison",
)
def get_sensor_comparison(
    filters: DataFilter,
) -> SensorComparisonResponse:
    return build_sensor_comparison(filters)
