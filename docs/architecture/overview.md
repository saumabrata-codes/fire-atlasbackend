# Architecture overview

FireAtlas runs as a React/Vite client, a FastAPI service, and PostgreSQL with PostGIS. NASA FIRMS CSV responses are archived under `data/raw`, parsed by sensor-specific readers, validated, and written to the normalized observation table with source and job provenance. The API serves map features, summaries, calendar aggregates, sensor comparisons, anomaly summaries, and reports.

The first delivery is a bounded real-data ingestion slice. Analytics model packages are reserved for later scientific work; their presence does not imply that every advanced method is implemented or validated.

## Local services

`docker-compose.yml` starts the persistent PostGIS database. Run Alembic from `backend`, start FastAPI there, then start Vite from `frontend`. The frontend obtains data only through the API; credentials remain in the root `.env` and backend process.
