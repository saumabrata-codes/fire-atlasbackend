
from fastapi import APIRouter

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.overview import OverviewResponse
from source_backend.application.overview_service import build_overview

router = APIRouter()


@router.post(
    "/overview",
    response_model=OverviewResponse,
    tags=["Overview"],
)
async def get_overview(filters: DataFilter):
    """
    Return aggregated hotspot activity for the selected filters.
    """

    return build_overview(filters)
