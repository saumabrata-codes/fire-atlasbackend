
from typing import Any

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.calendar import (
    CalendarResponse,
    CalendarActivitySummary,
    CalendarPeriod,
)
from source_backend.api.v1.schemas.sensors import SensorCounts
from source_backend.application.providers.firms_adapter import get_active_fire_data
from source_backend.analytics.temporal.calendar import calculate_calendar


def _extract_bbox(filters: DataFilter):
    if filters.geography.selection_type.value == "global":
        return None

    bbox = filters.geography.bbox

    if bbox is None:
        raise ValueError("Bounding box is required.")

    return bbox.west, bbox.south, bbox.east, bbox.north


def _adapt_mock_observations(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert mock records into the canonical observation contract."""

    observations = []

    for record in records:
        observations.append({
            "instrument": record["sensor"],
            "acquisition_date": record["observed_at"],
        })

    return observations


def build_calendar(
    filters: DataFilter,
) -> CalendarResponse:

    bbox = _extract_bbox(filters)

    provider_result = get_active_fire_data(
        start_date=filters.start_date,
        end_date=filters.end_date,
        bbox=bbox,
        sensors=[sensor.value for sensor in filters.sensors],
    )

    records = provider_result["records"]
    metadata = provider_result["metadata"]

    observations = _adapt_mock_observations(records)

    calculations = calculate_calendar(
        observations=observations,
        aggregation=filters.aggregation.value,
    )

    return CalendarResponse(
        requested_start_date=filters.start_date,
        requested_end_date=filters.end_date,
        aggregation=filters.aggregation,
        calendar_periods=[
            CalendarPeriod(**period)
            for period in calculations["calendar_periods"]
        ],
        activity_summary=CalendarActivitySummary(
            **calculations["activity_summary"]
        ),
        sensor_summary=SensorCounts(
            **calculations["sensor_summary"]
        ),
        metadata=metadata,
    )
