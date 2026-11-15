from datetime import date
from fastapi import APIRouter, Query

from app.application.imagery import LAYERS, build_region_imagery, build_worldview_url
from app.geospatial.bounds import validate_observation_filters

router = APIRouter()


@router.get("/imagery/worldview-link")
def worldview_link(
    day: date,
    west: float = Query(-180, ge=-180, le=180),
    south: float = Query(-90, ge=-90, le=90),
    east: float = Query(180, ge=-180, le=180),
    north: float = Query(90, ge=-90, le=90),
) -> dict:
    """Return a date/area-specific NASA Worldview browse link for visual context."""
    validate_observation_filters(None, None, west, south, east, north)
    bounds = (west, south, east, north)
    return {
        "provider": "NASA Worldview / GIBS",
        "day": day.isoformat(),
        "bounds": [west, south, east, north],
        "layers": LAYERS,
        "images": build_region_imagery(day, bounds),
        "browse_url": build_worldview_url(day, bounds),
        "note": "Browse imagery is visual context. Layer availability and date coverage vary; it does not replace FIRMS detections or analysis.",
    }
