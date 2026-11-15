
from datetime import date

from pydantic import BaseModel, Field

from source_backend.api.v1.schemas.responses import DataMetadata


class SensorCounts(BaseModel):
    MODIS: int = Field(default=0, ge=0)
    VIIRS: int = Field(default=0, ge=0)


class SensorStatistics(BaseModel):
    detection_share_percent: float = Field(ge=0, le=100)
    mean_frp_mw: float | None = Field(default=None, ge=0)
    max_frp_mw: float | None = Field(default=None, ge=0)
    observations_with_frp: int = Field(default=0, ge=0)


class SensorComparison(BaseModel):
    total_hotspot_detections: int = Field(ge=0)
    sensor_counts: SensorCounts
    sensor_summaries: dict[str, SensorStatistics]


class SensorTimeSeriesPoint(BaseModel):
    period: str
    MODIS: int = Field(default=0, ge=0)
    VIIRS: int = Field(default=0, ge=0)
    total_detections: int = Field(ge=0)


class ProductSummary(BaseModel):
    source_product: str
    sensor: str
    detection_count: int = Field(ge=0)


class SensorComparisonResponse(BaseModel):
    requested_start_date: date
    requested_end_date: date
    comparison: SensorComparison
    time_series: list[SensorTimeSeriesPoint]
    product_summaries: list[ProductSummary]
    metadata: DataMetadata
