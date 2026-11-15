from datetime import date

from fastapi import HTTPException


def validate_observation_filters(start: date | None, end: date | None,
                                west: float | None, south: float | None,
                                east: float | None, north: float | None) -> tuple[float, float, float, float] | None:
    bbox_values = (west, south, east, north)
    if any(value is not None for value in bbox_values) and any(value is None for value in bbox_values):
        raise HTTPException(status_code=422, detail="Provide all four bounding coordinates: west, south, east, north")
    if west is not None and (west >= east or south >= north):
        raise HTTPException(status_code=422, detail="Bounding box must have west < east and south < north")
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start date must not be later than end date")
    return (west, south, east, north) if west is not None else None
