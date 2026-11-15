# Local development

Use the Windows setup and live-data checklist in `docs/development/first-live-run.md`. Keep the FIRMS key in the ignored root `.env`. Start `docker compose up -d db`, migrate from `backend`, and run the Vite client from `frontend`. The PostGIS named volume and `data/raw` archive are persistent project data.
