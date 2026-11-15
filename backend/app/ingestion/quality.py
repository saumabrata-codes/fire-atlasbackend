"""Shared conservative FIRMS confidence gate for searchable fire detections."""


def eligible_detection(row: dict) -> bool:
    confidence = str(row.get("confidence") or "").strip().lower()
    sensor = str(row.get("sensor") or "").upper()
    if sensor == "VIIRS":
        # NASA FIRMS VIIRS confidence categories are low / nominal / high.
        return confidence in {"n", "h", "nominal", "high"}
    if sensor != "MODIS":
        return False
    if confidence in {"n", "h", "nominal", "high"}:
        return True
    try:
        return float(confidence) >= 30.0
    except ValueError:
        return False
