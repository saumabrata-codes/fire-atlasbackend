
from datetime import date

from pydantic import BaseModel, Field

from source_backend.api.v1.schemas.responses import DataMetadata


class SensorOverview(BaseModel):
    MODIS: int = Field(default=0, ge=0)
    VIIRS: int = Field(default=0, ge=0)


class ActivityPeriod(BaseModel):
    period: str
    detection_count: int = Field(ge=0)


class FRPSummary(BaseModel):
    mean_frp_mw: float | None = None
    max_frp_mw: float | None = None
    observations_with_frp: int = Field(default=0, ge=0)


class OverviewSummary(BaseModel):
    total_hotspot_detections: int = Field(ge=0)
    sensor_counts: SensorOverview
    activity_summary: list[ActivityPeriod]
    frp_summary: FRPSummary


class OverviewResponse(BaseModel):
    requested_start_date: date
    requested_end_date: date
    summary: OverviewSummary
    metadata: DataMetadata
