"""Load NASA FIRMS observations for Asia and North America into PostGIS."""

import argparse
import asyncio
import csv
import hashlib
import io
import json
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text

from app.core.config import get_settings
from app.database.models import SourceFile
from app.database.repositories import persist_ingestion
from app.database.session import SessionLocal
from app.ingestion.firms.client import FirmsClient
from app.ingestion.readers.firms_csv import parse_firms_csv
from app.workers.historical_backfill import _plan


REGIONS = {
    "asia_firms": ("Asia", ("25,-12,180,84", "-180,49,-168,84")),
    "north_america": ("North America", ("-180,5,-10,85", "170,49,180,73")),
}
PRODUCTS = {
    "MODIS_SP": "MODIS",
    "MODIS_NRT": "MODIS",
    "VIIRS_NOAA20_SP": "VIIRS",
    "VIIRS_NOAA20_NRT": "VIIRS",
}
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "regional"
BOUNDARIES_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
    "geojson/ne_50m_admin_0_map_units.geojson"
)


def region_geometries(boundaries: dict, continent: str) -> str:
    return json.dumps([
        {
            "geometry": feature["geometry"],
            "siberia": feature["properties"]["ADMIN"] == "Russia",
        }
        for feature in boundaries["features"]
        if feature["properties"]["CONTINENT"] == continent
        or (continent == "Asia" and feature["properties"]["ADMIN"] == "Russia")
    ])


def prepare_mask(db, geometries: str) -> bytes:
    wkb = db.scalar(text("""
        WITH units AS (
            SELECT ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(geometry), 4326)) AS geom,
                   siberia
            FROM jsonb_to_recordset(CAST(:geometries AS jsonb))
                 AS feature(geometry jsonb, siberia boolean)
        ), region AS (
            SELECT ST_UnaryUnion(ST_Collect(
                CASE WHEN siberia THEN ST_Intersection(geom, ST_Union(
                    ST_MakeEnvelope(60, 0, 180, 90, 4326),
                    ST_MakeEnvelope(-180, 0, -168, 90, 4326)
                )) ELSE geom END
            )) AS geom
            FROM units
        )
        SELECT ST_AsBinary(geom) FROM region
    """), {"geometries": geometries})
    return bytes(wkb)


def filter_region(db, body: str, mask: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(body.lstrip("\ufeff")))
    if not reader.fieldnames or not {"latitude", "longitude"}.issubset(reader.fieldnames):
        raise ValueError("FIRMS response is missing latitude and longitude headers")
    rows, points = [], []
    for row in reader:
        try:
            latitude, longitude = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError):
            continue
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            points.append({"row_index": len(rows), "lat": latitude, "lon": longitude})
            rows.append(row)
    matches = db.scalars(text("""
        WITH region AS MATERIALIZED (
            SELECT ST_GeomFromWKB(:mask, 4326) AS geom
        )
        SELECT point.row_index
        FROM json_to_recordset(CAST(:points AS json))
             AS point(row_index integer, lat double precision, lon double precision)
        CROSS JOIN region
        WHERE ST_Covers(region.geom, ST_SetSRID(ST_MakePoint(point.lon, point.lat), 4326))
        ORDER BY point.row_index
    """), {"mask": mask, "points": json.dumps(points)})
    return [rows[index] for index in matches]


def store_window(db, rows: list[dict], region: str, product: str, start: date, end: date) -> int:
    if not rows:
        return 0
    # Different area requests can cover the same point near the antimeridian.
    fields = list(dict.fromkeys(key for row in rows for key in row if key))
    rows = list({tuple(row.get(key) for key in fields): row for row in rows}.values())
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    body = stream.getvalue()
    payload = body.encode()
    checksum = hashlib.sha256(payload).hexdigest()
    path = DATA_DIR / region / f"{product}_{start}_{end}_{checksum[:12]}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    observations = parse_firms_csv(body, PRODUCTS[product], product, path.name)
    observations = list({row["id"]: row for row in observations}.values())
    archive = {
        "path": str(path.relative_to(DATA_DIR.parents[1])),
        "sha256": checksum,
        "file_size": len(payload),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "source_date_start": start.isoformat(),
        "source_date_end": end.isoformat(),
    }
    if not path.exists():
        temporary = path.with_suffix(".csv.part")
        temporary.write_bytes(payload)
        temporary.replace(path)
    _, stored = persist_ingestion(
        db, PRODUCTS[product], product, end.isoformat(), archive, observations,
        job_type="regional_import",
    )
    return stored


async def collect(start: date, end: date, batch_days: int = 2) -> None:
    settings = get_settings()
    client = FirmsClient(settings.firms_api_key, settings.firms_base_url, timeout=90)
    availability = await client.fetch_availability(settings.firms_availability_url)
    # Select one consistent VIIRS platform for the annual series alongside MODIS.
    availability = [row for row in availability
                    if row["data_id"].startswith(("MODIS_", "VIIRS_NOAA20_"))]
    if not _plan(availability, ["MODIS", "VIIRS"], start, end):
        raise RuntimeError("No available FIRMS products overlap the requested dates")
    path = DATA_DIR / "natural-earth-map-units.geojson"
    if not path.exists():
        async with httpx.AsyncClient(timeout=60) as http:
            response = await http.get(BOUNDARIES_URL)
            response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    boundaries = json.loads(path.read_bytes())
    batches = []
    with SessionLocal() as db:
        masks = {region: prepare_mask(db, region_geometries(boundaries, continent))
                 for region, (continent, _) in REGIONS.items()}
        for region in REGIONS:
            covered = [
                {"product": product, "start": first, "end": last}
                for product, first, last in db.execute(
                    select(SourceFile.product_id, SourceFile.source_date_start, SourceFile.source_date_end)
                    .where(SourceFile.file_path.startswith(f"data/regional/{region}/"),
                           SourceFile.source_date_start <= end, SourceFile.source_date_end >= start)
                )
            ]
            for plan in _plan(availability, ["MODIS", "VIIRS"], start, end, covered):
                first, final_day = date.fromisoformat(plan["start"]), date.fromisoformat(plan["end"])
                while first <= final_day:
                    last = min(first + timedelta(days=batch_days - 1), final_day)
                    batches.append((last, first, region, plan["product"]))
                    first = last + timedelta(days=1)
    batches.sort(reverse=True)
    print(f"{len(batches)} regional product windows to import", flush=True)
    async def download(batch):
        last, first, region, product = batch
        _, areas = REGIONS[region]
        for attempt in range(4):
            try:
                return await asyncio.gather(*(
                    client.fetch_area(product, area, (last - first).days + 1, first.isoformat())
                    for area in areas
                ))
            except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError):
                if attempt == 3:
                    raise
                await asyncio.sleep(5 * 2**attempt)

    def persist(batch, bodies):
        last, first, region, product = batch
        with SessionLocal() as db:
            rows = [row for body in bodies for row in filter_region(db, body, masks[region])]
            stored = store_window(db, rows, region, product, first, last)
        continent, _ = REGIONS[region]
        print(f"{continent} {product} {first}–{last}: {stored:,} stored", flush=True)

    # Prefetch a bounded number of windows while a single writer commits in order.
    pending = deque()
    batch_iterator = iter(batches)
    for batch in batches[:3]:
        pending.append((next(batch_iterator), asyncio.create_task(download(batch))))
    try:
        while pending:
            batch, request = pending.popleft()
            bodies = await request
            next_batch = next(batch_iterator, None)
            if next_batch is not None:
                pending.append((next_batch, asyncio.create_task(download(next_batch))))
            await asyncio.to_thread(persist, batch, bodies)
    finally:
        for _, request in pending:
            request.cancel()
        await asyncio.gather(*(request for _, request in pending), return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", type=date.fromisoformat)
    parser.add_argument("end", type=date.fromisoformat)
    parser.add_argument("--batch-days", type=int, choices=range(1, 6), default=2)
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("start must be on or before end")
    if not get_settings().firms_api_key:
        parser.error("FIRMS_API_KEY is required")
    try:
        asyncio.run(collect(args.start, args.end, args.batch_days))
    except httpx.HTTPStatusError as error:
        parser.exit(1, f"Regional import failed with HTTP {error.response.status_code}.\n")
    except httpx.RequestError as error:
        parser.exit(1, f"Regional import connection failed ({type(error).__name__}).\n")
    except RuntimeError:
        parser.exit(1, "Regional import failed because FIRMS returned an error response.\n")


if __name__ == "__main__":
    main()
