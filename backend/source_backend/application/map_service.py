from datetime import date

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.api.v1.schemas.map import MapDetection, MapResponse
from source_backend.application.providers.firms_adapter import get_active_fire_data


def _extract_bbox(filters: DataFilter):
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


def build_map_response(filters: DataFilter) -> MapResponse:
    provider_result = get_active_fire_data(
        start_date=filters.start_date,
        end_date=filters.end_date,
        bbox=_extract_bbox(filters),
        sensors=[sensor.value for sensor in filters.sensors],
    )

    map_records = []

    for record in provider_result["records"]:
        map_records.append(
            MapDetection(
                source_record_id=record.get("source_record_id"),
                sensor=record["sensor"],
                observed_date=date.fromisoformat(record["observed_at"]),
                latitude=record["latitude"],
                longitude=record["longitude"],
                frp_mw=record.get("frp_mw"),
                source_product=record.get("source_product"),
                confidence=record.get("confidence"),
                is_synthetic=record.get("is_synthetic", False),
                source_attributes=record.get("source_attributes", {}),
            )
        )

    return MapResponse(
        records=map_records,
        metadata=provider_result["metadata"],
    )
