
from collections import defaultdict
from datetime import date
from typing import Any

from source_backend.api.v1.schemas.filters import (
    AggregationType,
    DataFilter,
)
from source_backend.api.v1.schemas.overview import (
    ActivityPeriod,
    FRPSummary,
    OverviewResponse,
    OverviewSummary,
    SensorOverview,
)
from source_backend.application.providers.firms_adapter import get_active_fire_data


def _get_period(record_date: date, aggregation: AggregationType) -> str:
    """Convert a date into the requested aggregation period."""

    if aggregation == AggregationType.DAILY:
        return record_date.isoformat()

    if aggregation == AggregationType.MONTHLY:
        return record_date.strftime("%Y-%m")

    if aggregation == AggregationType.YEARLY:
        return record_date.strftime("%Y")

    raise ValueError("Unsupported aggregation type.")


def _extract_bbox(
    filters: DataFilter,
) -> tuple[float, float, float, float] | None:
    """Convert the geography filter into provider bbox format."""

    if filters.geography.selection_type.value == "global":
        return None

    bbox = filters.geography.bbox

    if bbox is None:
        raise ValueError("Bounding box is required.")

    return (
        bbox.west,
        bbox.south,
        bbox.east,
        bbox.north,
    )


def build_overview(
    filters: DataFilter,
) -> OverviewResponse:
    """
    Build the FIRE ATLAS overview from filtered hotspot records.
    """

    bbox = _extract_bbox(filters)

    provider_result = get_active_fire_data(
        start_date=filters.start_date,
        end_date=filters.end_date,
        bbox=bbox,
        sensors=[sensor.value for sensor in filters.sensors],
    )

    records: list[dict[str, Any]] = provider_result["records"]
    metadata = provider_result["metadata"]

    sensor_counts = {
        "MODIS": 0,
        "VIIRS": 0,
    }

    period_counts: dict[str, int] = defaultdict(int)
    frp_values: list[float] = []

    for record in records:
        sensor = record["sensor"]

        if sensor in sensor_counts:
            sensor_counts[sensor] += 1

        record_date = date.fromisoformat(record["observed_at"])

        period = _get_period(record_date, filters.aggregation)
        period_counts[period] += 1

        frp = record.get("frp_mw")

        if frp is not None:
            frp_values.append(float(frp))

    activity_summary = [
        ActivityPeriod(
            period=period,
            detection_count=count,
        )
        for period, count in sorted(period_counts.items())
    ]

    frp_summary = FRPSummary(
        mean_frp_mw=(
            sum(frp_values) / len(frp_values)
            if frp_values else None
        ),
        max_frp_mw=max(frp_values) if frp_values else None,
        observations_with_frp=len(frp_values),
    )

    summary = OverviewSummary(
        total_hotspot_detections=len(records),
        sensor_counts=SensorOverview(**sensor_counts),
        activity_summary=activity_summary,
        frp_summary=frp_summary,
    )

    return OverviewResponse(
        requested_start_date=filters.start_date,
        requested_end_date=filters.end_date,
        summary=summary,
        metadata=metadata,
    )
