from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class GeographicSelectionType(str, Enum):
    GLOBAL = "global"
    BOUNDING_BOX = "bounding_box"


class SensorType(str, Enum):
    MODIS = "MODIS"
    VIIRS = "VIIRS"


class AggregationType(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class BoundingBox(BaseModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def validate_boundaries(self):
        if self.west > self.east:
            raise ValueError("west must be less than or equal to east")

        if self.south > self.north:
            raise ValueError("south must be less than or equal to north")

        return self


class GeographyFilter(BaseModel):
    selection_type: GeographicSelectionType
    bbox: BoundingBox | None = None

    @model_validator(mode="after")
    def validate_geography(self):
        if self.selection_type == GeographicSelectionType.GLOBAL:
            if self.bbox is not None:
                raise ValueError("bbox must not be provided for global selection")

        if self.selection_type == GeographicSelectionType.BOUNDING_BOX:
            if self.bbox is None:
                raise ValueError("bbox is required for bounding_box selection")

        return self


class DataFilter(BaseModel):
    start_date: date
    end_date: date

    geography: GeographyFilter

    sensors: list[SensorType] = Field(
        default_factory=lambda: [SensorType.MODIS, SensorType.VIIRS]
    )

    aggregation: AggregationType = AggregationType.DAILY

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")
        if not self.sensors:
            raise ValueError("At least one sensor must be selected.")

        if len(self.sensors) != len(set(self.sensors)):
            raise ValueError("Duplicate sensor selections are not allowed.")

        return self