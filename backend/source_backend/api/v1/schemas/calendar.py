
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

from source_backend.api.v1.schemas.filters import AggregationType
from source_backend.api.v1.schemas.responses import DataMetadata
from source_backend.api.v1.schemas.sensors import SensorCounts


class CalendarPeriodStatus(str, Enum):
    OBSERVED_WITH_DETECTIONS = "observed_with_detections"
    OBSERVED_ZERO_DETECTIONS = "observed_zero_detections"
    MISSING = "missing"
    INCOMPLETE = "incomplete"


class CalendarPeriod(BaseModel):
    period: str
    MODIS: int = Field(default=0, ge=0)
    VIIRS: int = Field(default=0, ge=0)
    total_detections: int = Field(ge=0)
    status: CalendarPeriodStatus


class CalendarActivitySummary(BaseModel):
    total_detections: int = Field(ge=0)
    periods_with_detections: int = Field(ge=0)
    highest_activity_period: str | None = None
    highest_activity_detections: int = Field(default=0, ge=0)


class CalendarResponse(BaseModel):
    requested_start_date: date
    requested_end_date: date
    aggregation: AggregationType
    calendar_periods: list[CalendarPeriod]
    activity_summary: CalendarActivitySummary
    sensor_summary: SensorCounts
    metadata: DataMetadata
