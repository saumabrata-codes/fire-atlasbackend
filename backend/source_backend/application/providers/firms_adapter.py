from datetime import date
from typing import Any

from source_backend.ingestion.firms.local_provider import RegionalCSVProvider


def get_active_fire_data(
    start_date: date,
    end_date: date,
    bbox: tuple[float, float, float, float] | None = None,
    sensors: list[str] | None = None,
) -> dict[str, Any]:
    """Load observations from local regional FIRMS CSV archives."""

    sensor_names = sorted({
        str(sensor).upper()
        for sensor in (sensors or ["MODIS", "VIIRS"])
    })

    provider = RegionalCSVProvider()

    observations = provider.iter_observations(
        start_date=start_date,
        end_date=end_date,
        bbox=bbox,
        sensors=sensor_names,
    )


    records = []

    seen = set()
    for observation in observations:
        key = (
            observation.source_dataset, observation.satellite, observation.instrument,
            observation.acquisition_date, observation.acquisition_time,
            observation.latitude, observation.longitude,
        )
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "source_record_id": (
                f"{observation.source_dataset}:"
                f"{observation.acquisition_date.isoformat()}:"
                f"{len(records)}"
            ),
            "sensor": observation.instrument.upper(),
            "observed_at": observation.acquisition_date.isoformat(),
            "latitude": observation.latitude,
            "longitude": observation.longitude,
            "frp_mw": observation.frp,
            "source_product": observation.source_dataset,
            "confidence": observation.confidence,
            "is_synthetic": False,
            "source_attributes": observation.to_dict(),
        })

    sensor_counts = {
        sensor: sum(
            record["sensor"] == sensor
            for record in records
        )
        for sensor in ("MODIS", "VIIRS")
    }

    report = provider.get_report()
    invalid_rows = report["invalid_rows"]

    if records and invalid_rows:
        data_status = "partial"
    elif records:
        data_status = "available"
    elif report["files_scanned"] > 0:
        data_status = "no_matching_records"
    else:
        data_status = "unavailable"

    return {
        "records": records,
        "metadata": {
            "provider": "local_csv",
            "is_synthetic": False,
            "requested_start_date": start_date.isoformat(),
            "requested_end_date": end_date.isoformat(),
            "sensors_requested": sensor_names,
            "records_returned": len(records),
            "sensor_record_counts": sensor_counts,
            "data_status": data_status,
            "source_datasets": sorted({
                record["source_product"]
                for record in records
            }),
            "availability_status": (
                "local_archive_scanned"
                if report["files_scanned"] > 0
                else "no_files_found"
            ),
            "successful_requests": 0,
            "empty_requests": 0,
            "failed_requests": 0,
            "invalid_observations": invalid_rows,
            "note": (
                f"Local CSV archive. "
                f"Files scanned: {report['files_scanned']}; "
                f"rows scanned: {report['rows_scanned']}; "
                f"invalid rows: {invalid_rows}. "
                "Archive coverage does not guarantee observations "
                "for every requested date."
            ),
        },
    }
