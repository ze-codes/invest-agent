from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.queries import get_latest_series_points
from app.ingest import upsert_series_vintages


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def compute_weekly_net_settlements(db: Session, weeks_back: int = 12) -> List[Dict[str, Any]]:
    """Compute weekly net settlements = Issues − Redemptions − Interest.

    - Issues: `UST_AUCTION_ISSUES` (by issue_date proxy for settlement).
    - Redemptions: `UST_REDEMPTIONS` (DTS Public Debt Transactions, daily; in millions → scale column handles USD conversion).
    - Interest: `UST_INTEREST` (DTS Deposits/Withdrawals, daily; in millions → scale column handles USD conversion).
    Values are scaled to USD using each row's `scale`.
    Returns list of rows: { observation_date: week_monday, value_numeric: net_usd } sorted by week.
    """
    # Fetch a generous number of recent points; caller can slice as needed
    issues = get_latest_series_points(db, "UST_AUCTION_ISSUES", limit=weeks_back * 40)
    redemptions = get_latest_series_points(db, "UST_REDEMPTIONS", limit=weeks_back * 40)
    interest = get_latest_series_points(db, "UST_INTEREST", limit=weeks_back * 40)

    # Restrict calculation window to the overlap across all three inputs
    def _min_max(rows: List[Dict[str, Any]]) -> tuple[date | None, date | None]:
        if not rows:
            return None, None
        return rows[0]["observation_date"], rows[-1]["observation_date"]

    i_min, i_max = _min_max(issues)
    r_min, r_max = _min_max(redemptions)
    n_min, n_max = _min_max(interest)

    # If any input is missing entirely, return empty (cannot compute overlap)
    if not (i_min and r_min and n_min and i_max and r_max and n_max):
        return []

    common_start = max(i_min, r_min, n_min)
    common_end = min(i_max, r_max, n_max)
    if common_start > common_end:
        return []

    start_week = _monday_of_week(common_start)
    end_week = _monday_of_week(common_end)

    weekly: Dict[date, Dict[str, float]] = {}
    presence: Dict[date, Dict[str, bool]] = {}

    def add_to(bucket_key: str, rows: List[Dict[str, Any]]):
        for r in rows:
            obs_date = r["observation_date"]
            # Skip observations outside of the common overlap
            if obs_date < common_start or obs_date > common_end:
                continue
            week = _monday_of_week(obs_date)
            scaled_val = float(r["value_numeric"]) * float(r.get("scale", 1) or 1)
            agg = weekly.setdefault(week, {"issues": 0.0, "redemptions": 0.0, "interest": 0.0})
            agg[bucket_key] += scaled_val
            pres = presence.setdefault(week, {"issues": False, "redemptions": False, "interest": False})
            pres[bucket_key] = True

    add_to("issues", issues)
    add_to("redemptions", redemptions)
    add_to("interest", interest)

    out: List[Dict[str, Any]] = []
    for week, vals in weekly.items():
        # Ensure we only output within the common week bounds
        if week < start_week or week > end_week:
            continue
        # Require that all components are present for this week
        have = presence.get(week, {})
        if not (have.get("issues") and have.get("redemptions") and have.get("interest")):
            continue
        net = vals["issues"] - vals["redemptions"] - vals["interest"]
        out.append({"observation_date": week, "value_numeric": net})

    out.sort(key=lambda r: r["observation_date"])  # ascending by week
    # Limit to requested recent weeks
    if weeks_back and len(out) > weeks_back:
        out = out[-weeks_back:]
    return out


def upsert_weekly_net_settlements(db: Session, *, series_id: str = "UST_NET_SETTLE_W", weeks_back: int = 108) -> int:
    """Compute weekly net settlements and persist as a derived series.

    Each row is stored with units USD, scale=1.0, source="DERIVED".
    """
    rows = compute_weekly_net_settlements(db, weeks_back=weeks_back)
    # Attach required metadata fields
    from datetime import datetime, UTC
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
        units="USD",
        scale=1.0,
        source="DERIVED",
        source_url=None,
    )


