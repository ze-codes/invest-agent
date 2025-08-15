from __future__ import annotations

from datetime import datetime
from typing import Iterable, Dict, Any, Optional
import httpx

from app.settings import settings


FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


async def fetch_series(
    series_id: str,
    realtime_start: Optional[str] = None,
    realtime_end: Optional[str] = None,
    last_n: int = 200,
    observation_start: Optional[str] = None,
    observation_end: Optional[str] = None,
) -> Dict[str, Any]:
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": last_n,
    }
    # For MVP, use FRED latest (no vintage); include optional realtime_* and observation_* if provided
    if realtime_start:
        params["realtime_start"] = realtime_start
    if realtime_end:
        params["realtime_end"] = realtime_end
    if observation_start:
        params["observation_start"] = observation_start
    if observation_end:
        params["observation_end"] = observation_end

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(FRED_BASE, params=params)
        r.raise_for_status()
        return r.json()


