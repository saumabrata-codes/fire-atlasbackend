# Database and processing layers

PostgreSQL/PostGIS stores FIRMS source rows, standardized records, spatial statistics, and the processing state needed to resume large jobs.

## Five data layers used by the pipeline

1. `source_files.raw_payload` stores the exact original CSV bytes in PostgreSQL; the same bytes are checksum-archived under `data/raw/`. `raw_hotspots` stores each valid source row with product, time, location, and source-file provenance.
2. `hotspot_observations` stores validated, normalized point records with sensor, product, time, confidence, FRP, and a spatial point index.
3. `spatial_grid_cells` stores occupied cells on a shared 0.25-degree grid in SRID 4326.
4. `sensor_aggregates` stores refreshable daily per-sensor, satellite, and product statistics for those cells. Chart and calendar requests read these precomputed rows rather than loading the map's point limit.
5. `harmonized_activity` stores versioned daily counts aligned to the shared grid, with separate MODIS and VIIRS models and per-row provenance. This makes the table directly usable for charts while avoiding an unsupported cross-sensor conversion. `/analytics/harmonized` reads this output.

`source_products`, `source_files`, `ingestion_jobs`, and `backfill_runs` manage product catalog, provenance, and resumable work. `harmonization_models`, `historical_baselines`, `anomaly_results`, `geographic_regions`, and `report_jobs` support the wider application. `backfill_runs` holds the date cursor and counters; a committed 1–5 day request is safe to replay.

## Processing and query behavior

The collector stores original CSV bytes and quality-screened raw rows in a transaction per FIRMS chunk. A separate processor promotes only still-missing eligible raw rows into normalized observations, then refreshes daily sensor aggregates and versioned harmonized activity. Unique identities and upserts make retries idempotent. User area/date searches prioritize only relevant pending source chunks and wait for a concurrent processor holding the chunk lock. Map queries use point observations; time-series and calendar queries use precomputed aggregates. Missing dates remain missing rather than being reported as zero activity.

Counts remain separated by MODIS and VIIRS. Spatial grid alignment makes geographies comparable, but does not itself make satellite detections scientifically equivalent. Cross-sensor calibrated values remain disabled until an approved method and validation metrics are provided; the current harmonization only aligns time and space.

Apply schema with `python -m alembic upgrade head` from `backend`. The Compose named volume `fireatlas-postgres` preserves the database; mount/backup `data/` to preserve the source CSV archive.
