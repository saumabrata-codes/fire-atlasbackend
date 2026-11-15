
import csv
import io
import json
from datetime import date
from typing import Any

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.application.providers.firms_adapter import get_active_fire_data


def build_csv_report(filters: DataFilter) -> tuple[str, dict[str, Any]]:
    """Build a CSV export and return it with retrieval metadata."""

    if filters.geography.selection_type.value == "global":
        bbox = None
    else:
        bounds = filters.geography.bbox
        if bounds is None:
            raise ValueError("Bounding box is required.")

        bbox = (
            bounds.west,
            bounds.south,
            bounds.east,
            bounds.north,
        )

    result = get_active_fire_data(
        start_date=filters.start_date,
        end_date=filters.end_date,
        bbox=bbox,
        sensors=[sensor.value for sensor in filters.sensors],
    )

    records = result["records"]
    metadata = result["metadata"]

    output = io.StringIO(newline="")

    fieldnames = [
        "source_record_id",
        "sensor",
        "observed_at",
        "latitude",
        "longitude",
        "frp_mw",
        "source_product",
        "confidence",
        "is_synthetic",
        "source_attributes",
    ]

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
    )

    writer.writeheader()

    for record in records:
        row = {
            field: record.get(field)
            for field in fieldnames
        }

        row["source_attributes"] = json.dumps(
            row["source_attributes"] or {},
            ensure_ascii=False,
        )

        writer.writerow(row)

    return output.getvalue(), metadata
