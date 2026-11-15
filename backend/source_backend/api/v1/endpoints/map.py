from fastapi import APIRouter

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.map import MapResponse
from source_backend.application.map_service import build_map_response

router = APIRouter()


@router.post("/map", response_model=MapResponse, tags=["Map"])
async def get_map_data(filters: DataFilter):
    return build_map_response(filters)