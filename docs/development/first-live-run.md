# First live run on Windows (legacy global stack)

For the current Asia and North America Docker stack, use the [repository startup and import instructions](../../README.md#run-locally).

This checklist starts the application against the already stored observations. FIRMS collection is paused by default until frontend acceptance. A previous live test on 2026-11-13 found detections in Prainha, Brazil using the box `-53.8,-1.4,-53.3,-0.9` (MODIS_NRT: 8; VIIRS_NOAA21_NRT: 69). Delhi/NCR returned zero for both sensors on the same date.

## 1. Request a NASA FIRMS key

Request a free MAP_KEY at <https://firms.modaps.eosdis.nasa.gov/api/map_key/>. NASA sends the key to the email address used for the request. Keep it private; do not put it in chat, source control, frontend variables, or screenshots.

## 2. Configure the local environment

From the repository root, open `.env` and set the key without quotes:

```dotenv
FIRMS_API_KEY=your_private_key_here
FIRMS_COLLECTION_ENABLED=false
```

Keep `DATABASE_URL` pointed at the local PostGIS service unless you intentionally use a different PostgreSQL/PostGIS server. The root `.env` is gitignored.

## 3. Start PostGIS and migrate

If Docker Desktop is not installed, install it from [Docker's Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/). During setup, use the WSL 2 backend if available, finish any requested WSL update or Windows restart, then open Docker Desktop and wait until its engine is running. The official guide describes the supported Windows install options and WSL setup.

Then run these commands in PowerShell from the repository root:

```powershell
docker compose up -d db
docker compose ps
docker compose exec db pg_isready -U fireatlas -d fireatlas
docker compose exec db psql -U fireatlas -d fireatlas -c "SELECT PostGIS_Full_Version();"
cd backend
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m alembic upgrade head
uvicorn app.main:app --reload
```

If PowerShell blocks virtual environment activation, run the commands in a new PowerShell process with an execution policy that permits local scripts, or invoke `.venv\Scripts\python.exe` directly for pip, Alembic, and Uvicorn.

The expected connection is `postgresql+psycopg://fireatlas:fireatlas@localhost:5432/fireatlas`, already in `.env.example`. The Compose file uses the `postgis/postgis:16-3.7` image and persists database files in the `fireatlas-postgres` named volume.

## 4. Start the frontend

In another PowerShell window, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The API documentation is at <http://localhost:8000/docs>. Use `/api/v1/health/ready` to confirm that the backend can reach PostgreSQL and call PostGIS.

The map uses a satellite basemap by default and does not require a Google Maps key. A user can enter a bounding box, or click a location on the map: the application creates a small surrounding study area and refreshes the stored observations, charts, summaries, imagery context, and explanation for that selection.

## 5. Check the currently stored observations

Use the map's date and area filters to query what is already in PostGIS. The sample-download controls remain disabled by the backend while `FIRMS_COLLECTION_ENABLED=false`; searches do not start a new FIRMS download. You can check current FIRMS product dates separately through `/api/v1/ingestion/availability`.

After frontend acceptance, enable collection by setting `FIRMS_COLLECTION_ENABLED=true` in `.env` and restarting the relevant services. Only then use the bounded one-day sample controls or start the historical year-by-year collector. The collector checks harmonization before advancing to the next sensor-year.

If a sample was previously downloaded while PostGIS was offline, the archived CSV can be replayed after the database is ready. The endpoint verifies the CSV against its manifest before committing any rows. For the verified 2026-11-13 Prainha files, run these PowerShell commands from any directory:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/ingestion/archive/MODIS/MODIS_NRT/2026/11/20261113T084520Z_20a86e1987e9.csv/replay"
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/ingestion/archive/VIIRS/VIIRS_NOAA21_NRT/2026/11/20261113T084525Z_c71180681400.csv/replay"
```

Each response should show `stored: true`, 8 MODIS rows or 69 VIIRS rows, and a job ID. The endpoint returns an error if the file or manifest checksum does not match.

If an ingestion returns `stored: false`, the source CSV is still archived locally; the response note explains that PostGIS was unreachable. If the browser says the MAP_KEY is missing, restart the backend after saving `.env` so the process reloads the setting. Never send the MAP_KEY in a message.

Historical collection is intentionally paused until frontend acceptance. After acceptance, explicitly set `FIRMS_COLLECTION_ENABLED=true`, then start `docker compose --profile collection up -d db ingestion-worker harmonization-worker`; the worker rebuilds an annual plan and subtracts committed source ranges before resuming. It plans one sensor-year at a time and requires harmonization verification before advancing. Track collection progress at `/api/v1/ingestion/backfills`.
