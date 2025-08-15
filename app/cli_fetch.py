from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import List, Dict, Any

from app.settings import settings
from app.sources.fred import fetch_series
from app.sources.treasury import fetch_tga_latest
from app.ingest import upsert_series_vintages
from app.db import SessionLocal


def _parse_fred_observations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    # Note: FRED's top-level realtime_start/end describe the requested vintage window,
    # not the per-observation publication date. For MVP, omit publication_date here.
    pub_dt = None
    for obs in payload.get("observations", []):
        value_str = obs.get("value")
        if value_str in (None, "."):
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        out.append(
            {
                "observation_date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                "vintage_date": None,
                "publication_date": pub_dt,
                "fetched_at": datetime.now(UTC),
                # Store raw numeric; apply scaling via the 'scale' column in DB metadata
                "value_numeric": value,
            }
        )
    return out


def _parse_tga_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data", [])
    out: List[Dict[str, Any]] = []
    for row in data:
        # Filter to TGA account type if account_type provided (accept variants)
        acct = (row.get("account_type") or "").lower()
        if not ("treasury general" in acct and "account" in acct):
            continue
        # Per dataset notes, close_today_bal can be null; use open_today_bal as fallback
        val = row.get("close_today_bal")
        if val in (None, "null", ""):
            val = row.get("open_today_bal")
        if val in (None, "null", ""):
            continue
        try:
            num = float(val)
        except ValueError:
            continue
        out.append(
            {
                "observation_date": datetime.strptime(row["record_date"], "%Y-%m-%d").date(),
                "vintage_date": None,
                "publication_date": None,
                "fetched_at": datetime.now(UTC),
                "value_numeric": num,
            }
        )
    return out


async def fetch_core_series() -> None:
    async def fetch_and_ingest(series_id: str, units: str = "USD", scale: float = 1.0, observation_start: str | None = None):
        payload = await fetch_series(series_id, observation_start=observation_start)
        rows = _parse_fred_observations(payload)
        with SessionLocal() as s:
            upsert_series_vintages(s, series_id, rows, units=units, scale=scale, source="FRED", source_url="https://fred.stlouisfed.org")

    # FRED/ALFRED core
    await asyncio.gather(
        fetch_and_ingest("WALCL", units="USD", scale=1e6, observation_start="2010-01-01"),
        fetch_and_ingest("RESPPLLOPNWW", units="USD", scale=1e6, observation_start="2010-01-01"),
        fetch_and_ingest("RRPONTSYD", units="USD", scale=1e6, observation_start="2014-01-01"),
        fetch_and_ingest("SOFR", units="percent", scale=1.0, observation_start="2018-01-01"),
        fetch_and_ingest("IORB", units="percent", scale=1.0, observation_start="2008-01-01"),
        fetch_and_ingest("DTB3", units="percent", scale=1.0, observation_start="2000-01-01"),
        fetch_and_ingest("DTB4WK", units="percent", scale=1.0, observation_start="2001-01-01"),
    )

    # TGA via DTS
    try:
        payload = await fetch_tga_latest(limit=1000, pages=50)
        rows = _parse_tga_rows(payload)
        if rows:
            with SessionLocal() as s:
                # DTS values are rounded to millions; store scale=1e6
                upsert_series_vintages(s, "TGA", rows, units="USD", scale=1e6, source="DTS", source_url="https://api.fiscaldata.treasury.gov")
    except Exception as e:
        print(f"TGA fetch failed: {e}")


def main() -> None:
    asyncio.run(fetch_core_series())


if __name__ == "__main__":
    main()


