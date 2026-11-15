
from typing import Any

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.sensors import (
    SensorComparison,
    SensorComparisonResponse,
)
from source_backend.application.providers.firms_adapter import get_active_fire_data
from source_backend.analytics.sensor_comparison.calculations import (
    calculate_sensor_comparison,
)


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
    """Convert mock-provider records into the canonical observation contract."""

    observations = []

    for record in records:
        observations.append({
            "instrument": record["sensor"],
            "acquisition_date": record["observed_at"],
            "source_dataset": record.get("source_product"),
            "frp": record.get("frp_mw"),
        })

    return observations


def build_sensor_comparison(
    filters: DataFilter,
) -> SensorComparisonResponse:

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

    calculations = calculate_sensor_comparison(
        observations=observations,
        aggregation=filters.aggregation.value,
    )

    comparison = SensorComparison(
        total_hotspot_detections=calculations["total_hotspot_detections"],
        sensor_counts=calculations["sensor_counts"],
        sensor_summaries=calculations["sensor_summaries"],
    )

    return SensorComparisonResponse(
        requested_start_date=filters.start_date,
        requested_end_date=filters.end_date,
        comparison=comparison,
        time_series=calculations["time_series"],
        product_summaries=calculations["product_summaries"],
        metadata=metadata,
    )
