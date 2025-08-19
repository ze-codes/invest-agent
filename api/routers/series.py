from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.queries import get_latest_series_values, get_as_of_series_values
from app.schemas import SeriesPoint, SeriesResponse


router = APIRouter()


@router.get("/series/{series_id}", response_model=SeriesResponse)
def get_series(series_id: str, start: Optional[str] = None, end: Optional[str] = None, limit: Optional[int] = 500, as_of: Optional[str] = None, db: Session = Depends(get_db)):
    # For MVP: ignore start/end in SQL and return up to limit latest points; enhance later
    if as_of:
        # Normalize common variants (e.g., 'Z' suffix). Clients should URL-encode '+' in offsets.
        norm = as_of.strip()
        if norm.endswith("Z"):
            norm = norm[:-1] + "+00:00"
        try:
            as_of_dt = datetime.fromisoformat(norm)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid as_of; use ISO 8601 (e.g., 2025-08-02T12:00:00Z)")
        rows = get_as_of_series_values(db, series_id, as_of=as_of_dt)
    else:
        rows = get_latest_series_values(db, [series_id])
        rows = [r for r in rows if r["series_id"] == series_id]

    if limit is not None and limit > 0:
        rows = rows[-limit:]

    points = [
        SeriesPoint(
            observation_date=r["observation_date"],
            value_numeric=float(r["value_numeric"]),
            units=r["units"],
            scale=float(r["scale"]),
            source=r["source"],
            vintage_id=str(r["vintage_id"]) if r.get("vintage_id") else None,
            vintage_date=r.get("vintage_date"),
            publication_date=r.get("publication_date"),
            fetched_at=r.get("fetched_at"),
        )
        for r in rows
    ]
    return SeriesResponse(series_id=series_id, points=points)


@router.get("/series/list")
def list_series_ids(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT DISTINCT series_id FROM series_vintages ORDER BY series_id")).fetchall()
    return [r[0] for r in rows]


