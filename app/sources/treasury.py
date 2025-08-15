from __future__ import annotations

from typing import Dict, Any, List
import httpx


DTS_TGA_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"


async def fetch_tga_latest(limit: int = 1000, pages: int = 50) -> Dict[str, Any]:
    combined: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, pages + 1):
            params = {
                "sort": "-record_date",
                "page[number]": page,
                "page[size]": limit,
                "format": "json",
                # Request documented fields; we'll filter in code to capture naming variants
                "fields": "record_date,account_type,close_today_bal,open_today_bal",
            }
            r = await client.get(DTS_TGA_URL, params=params)
            r.raise_for_status()
            js = r.json()
            data = js.get("data", [])
            if not data:
                break
            combined.extend(data)
            if len(data) < limit:
                break
    return {"data": combined}


