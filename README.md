# FireAtlas

FireAtlas is a dashboard for exploring NASA FIRMS active-fire observations in Asia and North America. It combines a React and Vite frontend, a FastAPI backend, and a PostGIS database. The dashboard includes maps, activity trends, sensor comparisons, and downloadable reports. A detection is a satellite observation and can represent one of several observations of the same fire.

## Run locally

Install Docker with Docker Compose, clone this repository, and run these commands from its root in PowerShell.

```powershell
git clone https://github.com/SAYANDEEP-2003/Fire-Atlas.git
cd Fire-Atlas
docker compose up -d --build --wait
```

- [Dashboard](http://localhost:5173)
- [Dashboard API docs](http://localhost:8000/docs)
- [Source API docs](http://localhost:8000/source/docs)

A fresh installation starts with an empty regional database. Use the import command below to populate the dashboard. The synthetic fixtures in [data/samples](data/samples/) are for development and parser checks.

## Import regional observations

Obtain a [NASA FIRMS map key](https://firms.modaps.eosdis.nasa.gov/api/map_key/), copy `.env.example` to `.env`, and set `FIRMS_API_KEY` in the local file.

```powershell
Copy-Item .env.example .env
# Set FIRMS_API_KEY in .env before running the importer.
docker compose run --rm --no-deps backend python -m app.workers.regional_import 2025-11-15 2026-11-14
```

The example imports a rolling one-year window. Replace the two dates with the inclusive range you need. The worker uses standard MODIS and NOAA-20 VIIRS records for historical dates and near-real-time records for newer dates. It checks FIRMS product availability, filters detections to Asia and North America using Natural Earth map units, and resumes from committed date ranges when you repeat the command. The Asian portion of Russia uses an approximate split at 60°E.

Downloaded CSVs are written to the local `data/regional/` folder. Observations and aggregates persist in the `regional-postgres` Docker volume. GitHub contains the importer, documentation, and small synthetic fixtures. Each installation imports its own observational data.

## Project layout

- [frontend](frontend/) contains the dashboard and its same-origin API proxy.
- [backend](backend/) contains the API, importer, and database migrations.
- [docs](docs/) contains architecture, API, and development notes.

The project is distributed under the [license](LICENSE).
