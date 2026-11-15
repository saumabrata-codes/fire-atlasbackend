import csv
from pathlib import Path

from app.core.config import get_settings
from app.ingestion.readers.firms_csv import parse_firms_csv

ROOT = Path(__file__).resolve().parents[3]
SAMPLE_PATHS = {
    "MODIS": (ROOT / "data/samples/modis/sample_modis.csv", "MODIS_NRT_SAMPLE"),
    "VIIRS": (ROOT / "data/samples/viirs/sample_viirs.csv", "VIIRS_SNPP_SAMPLE"),
}


def load_sample_observations() -> list[dict]:
    if get_settings().fireatlas_regional_only:
        return []
    observations = []
    for sensor, (path, product) in SAMPLE_PATHS.items():
        if not path.exists():
            continue
        observations.extend(parse_firms_csv(path.read_text(encoding="utf-8-sig"), sensor, product, path.name))
    return observations
