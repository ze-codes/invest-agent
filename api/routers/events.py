from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.snapshot import compute_snapshot


router = APIRouter()


@router.post("/events/recompute")
def recompute_and_save(horizon: str = "1w", k: int = 8, as_of: str | None = None, as_of_mode: str = "fetched", db: Session = Depends(get_db)):
    as_of_dt = None
    if as_of:
        norm = as_of.strip()
        if norm.endswith("Z"):
            norm = norm[:-1] + "+00:00"
        try:
            as_of_dt = datetime.fromisoformat(norm)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid as_of; use ISO 8601")
    # Upsert by day: remove any existing snapshot for same horizon + date(as_of)
    target_dt = as_of_dt or datetime.now(timezone.utc)
    db.execute(text("DELETE FROM snapshots WHERE horizon = :h AND DATE(as_of) = :d"), {"h": horizon, "d": target_dt.date()})
    db.commit()
    snap = compute_snapshot(db, horizon=horizon, k=k, save=True, as_of=as_of_dt, as_of_mode=as_of_mode)
    return {
        "as_of": snap["as_of"],
        "snapshot": snap,
    }


@router.post("/events/backfill_history")
def backfill_history(horizon: str = "1w", days: int = 180, k: int = 8, as_of_mode: str = "obs", db: Session = Depends(get_db)):
    # Compute and persist daily snapshots for the last N days as of each day end (UTC midnight+23:59:59)
    now = datetime.now(timezone.utc)
    count = 0
    for i in range(days, -1, -1):
        as_of_dt = now - timedelta(days=i)
        # Normalize to end of day for determinism
        as_of_dt = as_of_dt.replace(hour=23, minute=59, second=59, microsecond=0)
        # Upsert by day: delete existing snapshot for same day/horizon
        db.execute(text("DELETE FROM snapshots WHERE horizon = :h AND DATE(as_of) = :d"), {"h": horizon, "d": as_of_dt.date()})
        db.commit()
        compute_snapshot(db, horizon=horizon, k=k, save=True, as_of=as_of_dt, as_of_mode=as_of_mode)
        count += 1
    return {"horizon": horizon, "days": days, "persisted": count}


