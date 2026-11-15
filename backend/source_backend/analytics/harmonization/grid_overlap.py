from collections import defaultdict
from math import floor
from typing import Any, Iterable

from pyproj import Transformer


DEFAULT_GRID_SIZES_M = (1_000, 5_000, 10_000)
SUPPORTED_SENSORS = {"MODIS", "VIIRS"}

_TRANSFORMER = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:6933",
    always_xy=True,
)


def assign_grid_cell(
    longitude: float,
    latitude: float,
    grid_size_m: int,
    transformer: Transformer | None = None,
) -> tuple[int, int]:
    """Project WGS84 coordinates and assign them to a metric grid cell."""
    if grid_size_m <= 0:
        raise ValueError("grid_size_m must be greater than zero.")

    if not (-180 <= longitude <= 180):
        raise ValueError("longitude must be between -180 and 180.")

    if not (-90 <= latitude <= 90):
        raise ValueError("latitude must be between -90 and 90.")

    projection = transformer or _TRANSFORMER
    x, y = projection.transform(longitude, latitude)

    return floor(x / grid_size_m), floor(y / grid_size_m)


def calculate_grid_overlap(
    observations: Iterable[dict[str, Any]],
    grid_size_m: int,
) -> dict[str, Any]:
    """
    Classify observed date-grid cells by sensor presence.

    Overlap percentage = shared date-grid cells / all observed date-grid cells.
    This measures co-occurrence, not matched fires or sensor calibration.
    """
    if grid_size_m <= 0:
        raise ValueError("grid_size_m must be greater than zero.")

    cells: dict[tuple[str, int, int], set[str]] = defaultdict(set)

    for row in observations:
        try:
            longitude = float(row["longitude"])
            latitude = float(row["latitude"])
            acquisition_date = str(row["acquisition_date"]).strip()
            sensor = str(row["instrument"]).strip().upper()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid observation: {row}") from exc

        if not acquisition_date:
            raise ValueError("acquisition_date cannot be empty.")

        if sensor not in SUPPORTED_SENSORS:
            raise ValueError(f"Unsupported sensor: {sensor}")

        grid_x, grid_y = assign_grid_cell(
            longitude, latitude, grid_size_m
        )
        cells[(acquisition_date, grid_x, grid_y)].add(sensor)

    shared = sum(
        sensors == SUPPORTED_SENSORS for sensors in cells.values()
    )
    modis_only = sum(
        sensors == {"MODIS"} for sensors in cells.values()
    )
    viirs_only = sum(
        sensors == {"VIIRS"} for sensors in cells.values()
    )
    total = len(cells)

    return {
        "grid_size_m": grid_size_m,
        "total_grid_days": total,
        "shared": shared,
        "modis_only": modis_only,
        "viirs_only": viirs_only,
        "overlap_percent": round(shared / total * 100, 2) if total else 0.0,
    }


def analyze_grid_sensitivity(
    observations: Iterable[dict[str, Any]],
    grid_sizes_m: Iterable[int] = DEFAULT_GRID_SIZES_M,
) -> list[dict[str, Any]]:
    """Run the same grid overlap calculation at multiple resolutions."""
    rows = list(observations)
    return [
        calculate_grid_overlap(rows, grid_size)
        for grid_size in grid_sizes_m
    ]
