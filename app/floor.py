from __future__ import annotations

from datetime import datetime, UTC
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from app.queries import get_latest_series_points
from app.ingest import upsert_series_vintages


def compute_bill_rrp_points(db: Session, days_back: int = 200) -> List[Dict[str, Any]]:
    """Compute daily bill_rrp = min(DTB3, DTB4WK) − RRP_RATE, in basis points.

    Inputs are in percent. Output value_numeric is in bps.
    Returns ascending by date.  
    """
    dtb3 = get_latest_series_points(db, "DTB3", limit=days_back)
    dtb4 = get_latest_series_points(db, "DTB4WK", limit=days_back)
    rrp = get_latest_series_points(db, "RRP_RATE", limit=days_back)

    # Index by date
    def by_date(rows: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
        return {r["observation_date"]: r for r in rows}

    b3 = by_date(dtb3)
    b4 = by_date(dtb4)
    rr = by_date(rrp)

    all_dates = sorted(set(b3) | set(b4) | set(rr))
    out: List[Dict[str, Any]] = []
    for d in all_dates:
        b3v = float(b3.get(d, {}).get("value_numeric") or 0)
        b4v = float(b4.get(d, {}).get("value_numeric") or 0)
        rrv = float(rr.get(d, {}).get("value_numeric") or 0)
        if d not in rr or (d not in b3 and d not in b4):
            continue
        bill_pct = min(v for v in [b3v if d in b3 else None, b4v if d in b4 else None] if v is not None)
        spread_bps = (bill_pct - rrv) * 100.0
        out.append({"observation_date": d, "value_numeric": spread_bps})
    return out


def upsert_bill_rrp_spread(db: Session, *, series_id: str = "BILL_RRP_BPS", days_back: int = 200) -> int:
    rows = compute_bill_rrp_points(db, days_back=days_back)
    now = datetime.now(UTC)
    payload = [
        {
            "observation_date": r["observation_date"],
            "vintage_date": None,
            "publication_date": None,
            "fetched_at": now,
            "value_numeric": r["value_numeric"],
        }
        for r in rows
    ]
    return upsert_series_vintages(
        db,
        series_id,
        payload,
        units="bps",
        scale=1.0,
        source="DERIVED",
        source_url=None,
    )


