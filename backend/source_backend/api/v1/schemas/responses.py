
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataStatus(str, Enum):
    AVAILABLE = "available"
    NO_DATA = "no_data"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NO_MATCHING_RECORDS = "no_matching_records"


class FireRecord(BaseModel):
    source_record_id: str | None = None
    sensor: str
    observed_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    frp_mw: float | None = Field(default=None, ge=0)

    source_product: str | None = None
    confidence: str | float | int | None = None
    is_synthetic: bool = False

    # Retains original sensor-specific source fields.
    source_attributes: dict[str, Any] = Field(default_factory=dict)


class SensorRecordCounts(BaseModel):
    MODIS: int = Field(default=0, ge=0)
    VIIRS: int = Field(default=0, ge=0)



class DataMetadata(BaseModel):
    provider: str
    is_synthetic: bool

    requested_start_date: date
    requested_end_date: date

    sensors_requested: list[str]
    records_returned: int = Field(ge=0)

    sensor_record_counts: SensorRecordCounts
    data_status: DataStatus

    # NASA FIRMS source information
    source_datasets: list[str] = Field(default_factory=list)
    availability_status: str | None = None

    # Provider retrieval statistics
    successful_requests: int = Field(default=0, ge=0)
    empty_requests: int = Field(default=0, ge=0)
    failed_requests: int = Field(default=0, ge=0)
    invalid_observations: int = Field(default=0, ge=0)

    note: str | None = None



class ActiveFireDataResponse(BaseModel):
    records: list[FireRecord]
    metadata: DataMetadata
