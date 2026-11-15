
from fastapi import APIRouter

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.calendar import CalendarResponse
from source_backend.application.calendar_service import build_calendar


router = APIRouter()


@router.post(
    "/calendar",
    response_model=CalendarResponse,
    summary="Get fire activity calendar",
)
def get_calendar(
    filters: DataFilter,
) -> CalendarResponse:
    return build_calendar(filters)
