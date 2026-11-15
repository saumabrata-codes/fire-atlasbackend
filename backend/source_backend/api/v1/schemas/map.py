from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from source_backend.api.v1.schemas.responses import DataMetadata


class MapDetection(BaseModel):
    source_record_id: str | None = None
    sensor: str
    observed_date: date
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    frp_mw: float | None = Field(default=None, ge=0)
    source_product: str | None = None
    confidence: str | float | int | None = None
    is_synthetic: bool = False
    source_attributes: dict[str, Any] = Field(default_factory=dict)


class MapResponse(BaseModel):
    records: list[MapDetection]
    metadata: DataMetadata