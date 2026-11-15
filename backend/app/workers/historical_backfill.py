"""Durable FIRMS backfill worker. Run as `python -m app.workers.historical_backfill`."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.database.models import BackfillRun, IngestionJob, SourceFile, HotspotObservation, RawHotspot
from app.database.repositories.harmonization import harmonize_sensor_year
from app.database.repositories.ingestion import persist_raw_ingestion
from app.database.session import SessionLocal
from app.ingestion.firms.client import FirmsClient
from app.ingestion.jobs.archive import preserve_source
from app.ingestion.quality import eligible_detection
from app.ingestion.readers.firms_csv import parse_firms_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("fireatlas.backfill")

def prune_retention() -> None:
    settings = get_settings()
    cutoff = date.today() - timedelta(days=settings.firms_retention_months * 31)
    with SessionLocal() as db:
        boundary = datetime.combine(cutoff, datetime.min.time(), tzinfo=timezone.utc)
        db.execute(delete(RawHotspot).where(RawHotspot.acq_datetime < boundary))
        db.execute(delete(HotspotObservation).where(HotspotObservation.acq_datetime < boundary))
        db.commit()
    log.info("Retention prune completed; records before %s removed", cutoff)


def _plan(availability: list[dict[str, str]], sensors: list[str], start: date, end: date,
          covered_ranges: list[dict] | None = None) -> list[dict]:
    available = {item.get("data_id", "").upper(): item for item in availability}
    covered_ranges = covered_ranges or []
    specs = {
        "MODIS": ["MODIS_SP", "MODIS_NRT"],
        "VIIRS": ["VIIRS_SNPP_SP", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT",
                  "VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"],
    }
    plans: list[dict] = []
    for sensor in sensors:
        sensor_entries = []
        for product in specs[sensor]:
            entry = available.get(product)
            if not entry or not entry.get("min_date") or not entry.get("max_date"):
                continue
            first = max(start, date.fromisoformat(entry["min_date"]))
            last = min(end, date.fromisoformat(entry["max_date"]))
            if first <= last:
                while first <= last:
                    year_end = date(first.year, 12, 31)
                    segment_end = min(last, year_end)
                    sensor_entries.append({"sensor": sensor, "product": product,
                                           "start": first.isoformat(), "end": segment_end.isoformat(),
                                           "year": first.year})
                    first = segment_end + timedelta(days=1)
        # Use science-standard products wherever available; limit the overlapping
        # NRT period to dates newer than that product's standard record.
        by_family: dict[str, date] = {}
        for item in sensor_entries:
            if item["product"].endswith("_SP"):
                family = item["product"][:-3]
                by_family[family] = max(by_family.get(family, date.min), date.fromisoformat(item["end"]))
        for item in sensor_entries:
            if item["product"].endswith("_NRT"):
                family = item["product"][:-4]
                item["start"] = max(date.fromisoformat(item["start"]),
                                    by_family.get(family, date.min) + timedelta(days=1)).isoformat()
            if date.fromisoformat(item["start"]) <= date.fromisoformat(item["end"]):
                coverage = [(entry["start"], entry["end"]) for entry in covered_ranges
                            if entry["product"] == item["product"]]
                for gap_start, gap_end in _subtract_covered_ranges(
                        date.fromisoformat(item["start"]), date.fromisoformat(item["end"]), coverage):
                    plans.append({**item, "start": gap_start.isoformat(), "end": gap_end.isoformat()})
    return sorted(plans, key=lambda p: (p["year"], p["sensor"], p["start"], p["product"]))


def _save_run(run_id: str, **values) -> None:
    with SessionLocal() as db:
        db.query(BackfillRun).filter(BackfillRun.id == run_id).update(values)
        db.commit()


def _resume_paused_run(run: BackfillRun) -> None:
    """Rebuild an annual plan from the beginning; committed ranges are subtracted below."""
    if run.status == "paused":
        run.status = "queued"
        run.products = []
        run.product_index = 0
        run.cursor_date = run.start_date
        run.last_error = None


def _subtract_covered_ranges(start: date, end: date,
                             covered: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Return only dates not represented by committed source chunks."""
    cursor = start
    gaps: list[tuple[date, date]] = []
    for covered_start, covered_end in sorted(covered):
        if covered_end < cursor or covered_start > end:
            continue
        if covered_start > cursor:
            gaps.append((cursor, min(end, covered_start - timedelta(days=1))))
        cursor = max(cursor, covered_end + timedelta(days=1))
        if cursor > end:
            break
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps


def _historical_coverage() -> list[dict]:
    """Read already-committed historical chunk ranges for duplicate-free resume planning."""
    with SessionLocal() as db:
        rows = db.execute(select(
            SourceFile.product_id, SourceFile.source_date_start, SourceFile.source_date_end
        ).join(IngestionJob, IngestionJob.source_file_id == SourceFile.id).where(
            IngestionJob.job_type == "historical",
            IngestionJob.status == "completed",
            SourceFile.source_date_start.is_not(None),
            SourceFile.source_date_end.is_not(None),
        ).distinct()).all()
    return [{"product": product, "start": first, "end": last}
            for product, first, last in rows]


def _range_already_committed(product: str, job_type: str, start: date, end: date) -> bool:
    """Guard the crash window between source commit and cursor commit."""
    with SessionLocal() as db:
        ranges = db.execute(select(
            SourceFile.source_date_start, SourceFile.source_date_end
        ).join(IngestionJob, IngestionJob.source_file_id == SourceFile.id).where(
            IngestionJob.job_type == job_type,
            IngestionJob.status == "completed",
            IngestionJob.product_id == product,
            SourceFile.source_date_start <= end,
            SourceFile.source_date_end >= start,
        ).distinct()).all()
    covered = [(left, right) for left, right in ranges if left is not None and right is not None]
    return not _subtract_covered_ranges(start, end, covered)


def _eligible_quality(row: dict) -> bool:
    """Keep valid-location/time records at NASA nominal or high confidence."""
    return eligible_detection(row)


async def _fetch_one(plan: dict, first: date, last: date, area: str) -> tuple[str, list[dict], int, int]:
    settings = get_settings()
    client = FirmsClient(settings.firms_api_key, settings.firms_base_url, timeout=180)
    days = (last - first).days + 1
    body = await client.fetch_area(plan["product"], area, days, first.isoformat())
    parsed = parse_firms_csv(body, plan["sensor"], plan["product"], "pending")
    downloaded_records = sum(1 for _ in csv.DictReader(io.StringIO(body.lstrip("\ufeff"))))
    eligible = [row for row in parsed if _eligible_quality(row)]
    return body, eligible, len(parsed), downloaded_records


def process_one_chunk(run_id: str) -> bool:
    """Process one API chunk and persist its cursor only after data commits."""
    if not get_settings().firms_collection_enabled:
        log.info("FIRMS collection is paused; no historical or daily chunk will be fetched")
        return False
    with SessionLocal() as db:
        run = db.get(BackfillRun, run_id)
        if run is None or run.status not in {"queued", "processing"}:
            return False
        if run.products and any("year" not in item for item in run.products):
            # Upgrade an old saved plan safely from committed chunk coverage.
            run.products = []
            run.product_index = 0
            run.cursor_date = run.start_date
        run.status = "processing"
        db.commit()
        run_data = {"products": run.products, "product_index": run.product_index,
                    "cursor_date": run.cursor_date, "end_date": run.end_date,
                    "area": run.area, "sensors": run.sensors,
                    "chunks_completed": run.chunks_completed,
                    "records_processed": run.records_processed, "run_type": run.run_type}

    if not run_data["products"]:
        settings = get_settings()
        client = FirmsClient(settings.firms_api_key, settings.firms_base_url, timeout=60)
        availability = asyncio.run(client.fetch_availability(settings.firms_availability_url))
        coverage = _historical_coverage() if run_data["run_type"] == "backfill" else []
        plans = _plan(availability, run_data["sensors"], run_data["cursor_date"],
                      run_data["end_date"], coverage)
        if not plans:
            _save_run(run_id, status="completed", products=[], last_error=None)
            return False
        first = date.fromisoformat(plans[0]["start"])
        _save_run(run_id, products=plans, product_index=0, cursor_date=first)
        run_data.update(products=plans, product_index=0, cursor_date=first)

    index = run_data["product_index"]
    products = run_data["products"]
    if index >= len(products):
        _save_run(run_id, status="completed", last_error=None)
        return False
    plan = products[index]
    cursor = max(run_data["cursor_date"], date.fromisoformat(plan["start"]))
    plan_end = date.fromisoformat(plan["end"])
    if cursor > plan_end:
        next_index = index + 1
        next_plan = products[next_index] if next_index < len(products) else None
        if next_plan is None or (next_plan["sensor"], next_plan["year"]) != (plan["sensor"], plan["year"]):
            verification = harmonize_sensor_year(plan["sensor"], plan["year"])
            log.info("Year harmonization verified before advancing: %s", verification)
        if next_index >= len(products):
            _save_run(run_id, status="completed", product_index=next_index, last_error=None)
            return False
        _save_run(run_id, product_index=next_index,
                  cursor_date=date.fromisoformat(products[next_index]["start"]))
        return True

    chunk_end = min(cursor + timedelta(days=4), plan_end)
    job_type = "daily_sync" if run_data["run_type"] == "daily_sync" else "historical"
    if _range_already_committed(plan["product"], job_type, cursor, chunk_end):
        _save_run(run_id, cursor_date=chunk_end + timedelta(days=1),
                  chunks_completed=run_data["chunks_completed"] + 1, last_error=None)
        return True
    settings = get_settings()
    body, accepted_rows, validated_records, downloaded_records = asyncio.run(
        _fetch_one(plan, cursor, chunk_end, run_data["area"]))
    archive = preserve_source(plan["sensor"], plan["product"], body, validated_records,
                              source_start=cursor, source_end=chunk_end)
    relative_path = archive["path"]
    for row in accepted_rows:
        row["source_file"] = relative_path
    with SessionLocal() as db:
        persist_raw_ingestion(
            db, plan["sensor"], plan["product"], chunk_end.isoformat(), archive,
            accepted_rows, downloaded_records,
            job_type=job_type,
        )
    prune_retention()

    next_date = chunk_end + timedelta(days=1)
    _save_run(run_id, cursor_date=next_date, chunks_completed=run_data["chunks_completed"] + 1,
              records_processed=run_data["records_processed"] + len(accepted_rows), last_error=None)
    log.info("Backfill %s: %s %s..%s (%s eligible of %s valid rows)", run_id,
             plan["product"], cursor, chunk_end, len(accepted_rows), validated_records)
    return True


def run_worker(poll_seconds: int = 10) -> None:
    settings = get_settings()
    if not settings.firms_collection_enabled:
        log.info("FIRMS collection is disabled; worker will wait without queueing or fetching data")
        while True:
            time.sleep(poll_seconds)
    if not settings.firms_api_key:
        raise RuntimeError("FIRMS_API_KEY is not configured")
    configured_start = date.fromisoformat(settings.firms_backfill_start)
    configured_end = date.fromisoformat(settings.firms_backfill_end)
    with SessionLocal() as db:
        configured_run = db.scalar(select(BackfillRun).where(
            BackfillRun.start_date == configured_start, BackfillRun.end_date == configured_end,
            BackfillRun.run_type == "backfill"
        ).order_by(BackfillRun.created_at.desc()).limit(1))
        if configured_run is None:
            db.add(BackfillRun(id=str(uuid4()), start_date=configured_start, end_date=configured_end,
                               cursor_date=configured_start, sensors=["MODIS", "VIIRS"],
                               products=[], area=settings.firms_area, status="queued"))
        else:
            _resume_paused_run(configured_run)
        db.commit()
    log.info("FIRMS backfill worker started")
    while True:
        try:
            _queue_daily_sync_if_due()
            with SessionLocal() as db:
                run_id = db.scalar(select(BackfillRun.id)
                                   .where(BackfillRun.status.in_(["queued", "processing"]))
                                   .order_by(BackfillRun.created_at).limit(1))
            if run_id:
                try:
                    process_one_chunk(run_id)
                except Exception as exc:  # network/FIRMS faults remain resumable
                    log.exception("Backfill chunk failed for %s", run_id)
                    _save_run(run_id, status="queued", last_error=str(exc)[:2000])
                    time.sleep(60)
            else:
                time.sleep(poll_seconds)
        except SQLAlchemyError:
            log.exception("Database unavailable; retrying")
            time.sleep(poll_seconds)


def _queue_daily_sync_if_due() -> None:
    target = datetime.now(timezone.utc).date() - timedelta(days=1)
    with SessionLocal() as db:
        active_backfill = db.scalar(select(BackfillRun.id).where(
            BackfillRun.run_type == "backfill", BackfillRun.status.in_(["queued", "processing"])
        ).limit(1))
        if active_backfill:
            return
        active = db.scalar(select(BackfillRun.id).where(
            BackfillRun.run_type == "daily_sync", BackfillRun.status.in_(["queued", "processing"])
        ).limit(1))
        if active:
            return
        last_completed = db.scalar(select(BackfillRun.end_date).where(
            BackfillRun.run_type == "daily_sync", BackfillRun.status == "completed"
        ).order_by(BackfillRun.end_date.desc()).limit(1))
        last_backfill = db.scalar(select(BackfillRun.end_date).where(
            BackfillRun.run_type == "backfill", BackfillRun.status == "completed"
        ).order_by(BackfillRun.end_date.desc()).limit(1))
        latest_covered = max((day for day in (last_completed, last_backfill) if day is not None),
                             default=None)
        if latest_covered and latest_covered >= target:
            return
        start = latest_covered + timedelta(days=1) if latest_covered else target - timedelta(days=4)
        db.add(BackfillRun(id=str(uuid4()), start_date=start, end_date=target,
                           cursor_date=start, sensors=["MODIS", "VIIRS"], products=[],
                           area=get_settings().firms_area, run_type="daily_sync", status="queued"))
        db.commit()


if __name__ == "__main__":
    run_worker()
