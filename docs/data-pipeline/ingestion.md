# FIRMS collection and harmonization

## Raw collection

The global collector is opt-in so routine backend startup does not begin NASA downloads. It requests 1–5 days per FIRMS Area API call, archives the original CSV and checksum manifest, stores the exact CSV bytes in source_files.raw_payload, and inserts quality-screened source rows into raw_hotspots. Stable row fingerprints and a unique key prevent duplicates.

Missing coordinates or acquisition time are discarded. MODIS low-confidence values below 30 and VIIRS low (l) or missing confidence are excluded from raw_hotspots. This gate is intentionally conservative; raw CSV files remain preserved for provenance.

Collection is intentionally paused until frontend acceptance. When it is resumed, the worker plans by calendar year, requests each NASA-available MODIS range first and then VIIRS for that year, and will not advance to the next sensor/year until harmonization verification succeeds. The gate compares raw-row and normalized-point counts per product within the current year. For chunks entirely within that year it uses each source file's stored row count; for chunks crossing a year boundary it counts only that year's raw rows. It also recomputes daily cell/source counts, FRP and day/night statistics from points, then compares those values with `sensor_aggregates`, and checks `harmonized_activity` values, period bounds, model status, and product/satellite provenance. If normalized points exist but derived values are missing or differ, the gate refreshes only the derived tables from those points and repeats verification once; it does not download or reinsert raw/point records. FIRMS product availability determines the actual start and end of each sensor record. Requests remain within the API's 1–5 day limit.

Start PostGIS and the processing worker without collection:

    docker compose up -d db harmonization-worker

After frontend acceptance, explicitly enable the collection profile:

    docker compose --profile collection up -d db ingestion-worker harmonization-worker

On explicit resume, the worker rebuilds the annual product plan from the configured start and subtracts date ranges already represented by successfully committed historical source files. This reconciles older saved plans safely and avoids refetching completed MODIS chunks while filling missing sensor/year ranges. A crash after a source chunk commits but before its cursor update is also checked against its committed source range before another FIRMS request. Collection date defaults are FIRMS_BACKFILL_START=2000-01-01 and FIRMS_BACKFILL_END=2026-11-13; NASA availability excludes dates before each product existed. VIIRS Suomi-NPP starts in 2012; MODIS coverage starts in 2000.

## Raw-to-analytics processing

harmonization-worker scans only source files with quality-eligible raw rows that are still missing from hotspot_observations. Each source file is locked while it is processed, so the background worker and a user request cannot harmonize the same chunk concurrently. Processing promotes rows into the normalized point table, then refreshes the corresponding quarter-degree sensor_aggregates and daily harmonized_activity tables. Existing points and aggregates use unique keys/upserts; a completed row is not inserted again.

The current method is a descriptive spatial and daily alignment. MODIS and VIIRS remain separate sensor series; no cross-sensor calibration or conversion factor is implied. Each completed yearly sensor range is checked for eligible raw rows missing from normalized points, points missing a grid aggregate, and grid aggregates missing harmonized activity. A failed check prevents the collector from advancing.

The request path also checks a requested date and area before serving map/chart data. It processes only pending source chunks intersecting that date and, when a bounding box is supplied, containing eligible raw detections in that box. It waits on the source-file database lock if the automation is already processing that chunk. No FIRMS download is triggered by a search. If no stored source files cover the requested dates, the API reports that raw data is unavailable.

## Search and summary endpoints

- POST /api/v1/analytics/prepare prepares already-collected data for a date range and bounding box.
- GET /api/v1/map/hotspots returns persisted point records and includes preprocessing status for date-filtered searches.
- GET /api/v1/analytics/timeseries returns chart-ready sensor counts and FRP from precomputed aggregates.
- GET /api/v1/analytics/harmonized returns the common-grid daily activity series.
- GET /api/v1/calendar/daily, /monthly, and /yearly accept date, sensor, and bounding-box filters and provide observed buckets without zero-filling missing periods.
- GET /api/v1/analytics/region-summary returns a 13–14-line data summary including trend, a simple spike screen, sensor counts, and limitations for imagery and disruption inference; area requests include the chart grid's spatial precision and date/bounds-specific NASA GIBS image URLs.
- GET /api/v1/imagery/worldview-link returns a NASA Worldview browse link plus individual MODIS and VIIRS WMS image URLs for the requested date and bounds. Imagery is visual context, fetched by the client from NASA, and is not stored as FIRMS observation data.

An optional OpenAI-compatible language model can explain that summary. Configure LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL in the backend environment. Without those values, the deterministic summary remains available. The model is instructed to use only supplied metrics, avoid treating detections as unique fires, avoid claiming sensor calibration, and not infer damage or unseen satellite imagery.

All chart values are satellite hotspot detections, not confirmed fire perimeters or impacts. Satellite image scenes are not included in FIRMS hotspot CSVs and require a separate imagery source.
