# API guide

Start the API with `uvicorn app.main:app --reload` from `backend`. Interactive OpenAPI documentation is available at `/docs`.

The versioned router is assembled in `app/api/v1/router.py`; endpoint groups live in `app/api/v1/endpoints`. Health/readiness, summary, map hotspots, calendar, sensor comparison, anomaly, report, and FIRMS ingestion routes are grouped by responsibility. Daily, monthly, and yearly calendar routes accept date, sensor, and bounding-box filters and use the same prepared aggregates as chart requests. `GET /api/v1/anomalies/summary` accepts date, sensor, and bounding-box filters and returns an elementary monthly screen only when six consecutive observed month buckets are available. Its `covered_days` value counts dates with stored detections, not complete satellite-observation coverage. See the OpenAPI schema for current request and response models.

`POST /api/v1/analytics/explain` accepts a user question plus optional date, sensor, and bounding-box filters. The API builds its context from stored analytics and sends the question as untrusted content to the configured LLM. If no model is configured or the provider fails, the response includes the verified 10–20-line summary and identifies that the LLM explanation is unavailable.
