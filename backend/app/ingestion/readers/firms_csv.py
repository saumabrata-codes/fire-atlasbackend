"""Source-specific FIRMS CSV parsing into a common display/storage contract."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime, time, timezone
from typing import Any


def _float(value: str | None) -> float | None:
    if value is None or value.strip() in {"", "N", "null", "None"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _utc_timestamp(row: dict[str, str]) -> str | None:
    raw_datetime = row.get("acq_datetime") or row.get("acq_datetime_utc")
    if raw_datetime:
        try:
            parsed = datetime.fromisoformat(raw_datetime.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    raw_day, raw_time = row.get("acq_date", ""), row.get("acq_time", "")
    try:
        day = date.fromisoformat(raw_day)
        hhmm = raw_time.strip().zfill(4)
        parsed_time = time(int(hhmm[:2]), int(hhmm[2:4]))
        return datetime.combine(day, parsed_time, tzinfo=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def parse_firms_csv(text: str, sensor: str, product: str, source_file: str) -> list[dict[str, Any]]:
    """Parse a FIRMS CSV while preserving every original source field."""
    normalized_sensor = sensor.upper()
    if normalized_sensor not in {"MODIS", "VIIRS"}:
        raise ValueError("sensor must be MODIS or VIIRS")
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    for index, raw in enumerate(reader, start=1):
        source_raw = {str(k): v for k, v in raw.items() if k}
        source = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        latitude = _float(source.get("latitude"))
        longitude = _float(source.get("longitude"))
        if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        acquired_at = _utc_timestamp(source)
        if not acquired_at:
            continue
        identity = "|".join([
            normalized_sensor,
            product,
            source.get("satellite", "").upper(),
            acquired_at,
            f"{latitude:.5f}",
            f"{longitude:.5f}",
        ])
        rows.append({
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            "source_record": index,
            "latitude": latitude,
            "longitude": longitude,
            "acq_datetime": acquired_at,
            "satellite": source.get("satellite", "unknown").upper(),
            "instrument": source.get("instrument", normalized_sensor).upper(),
            "sensor": normalized_sensor,
            "product": product,
            "confidence": source.get("confidence") or None,
            "frp": _float(source.get("frp")),
            "brightness": _float(source.get("brightness")),
            "bright_t31": _float(source.get("bright_t31")),
            "daynight": source.get("daynight") or None,
            "source_file": source_file,
            "raw": source,
            "source_raw": source_raw,
        })
    return rows
