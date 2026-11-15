from __future__ import annotations

import httpx
import csv
import io
import logging

# FIRMS credentials are part of request paths; httpx's INFO log prints full URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class FirmsClient:
    """Small FIRMS Area API client. Area API windows are limited to 1-5 days."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_area(
        self, source: str, area: str = "world", day_range: int = 1,
        date: str | None = None,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("FIRMS_API_KEY is not configured")
        if not 1 <= day_range <= 5:
            raise ValueError("FIRMS Area API requests must cover 1 to 5 days")
        url = f"{self.base_url}/{self.api_key}/{source}/{area}/{day_range}"
        if date is not None:
            # Historical Area API requests use a date as the final path segment.
            from datetime import date as date_type
            date_type.fromisoformat(date)
            url = f"{url}/{date}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            body = response.text
        if not body.strip() or body.lstrip().lower().startswith(("error", "invalid")):
            raise RuntimeError(f"FIRMS returned an error response: {body[:200]}")
        return body

    async def fetch_availability(self, availability_url: str) -> list[dict[str, str]]:
        if not self.api_key:
            raise RuntimeError("FIRMS_API_KEY is not configured")
        url = f"{availability_url.rstrip('/')}/{self.api_key}/all"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")))
        rows = [{str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in reader]
        if not rows or "data_id" not in rows[0]:
            raise RuntimeError("FIRMS data availability response did not contain a data_id column")
        return rows
