from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Snapshot as SnapshotModel


router = APIRouter()


@router.get("/snapshot/history")
def get_snapshot_history(horizon: str = "1w", days: int = 180, slim: bool = True, db: Session = Depends(get_db)):
    # Return saved snapshots within the last N days (or all if days <= 0)
    q = db.query(SnapshotModel).filter(SnapshotModel.horizon == horizon)
    if days and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = q.filter(SnapshotModel.as_of >= cutoff)
    rows: List[SnapshotModel] = q.order_by(SnapshotModel.as_of.asc()).all()

    # De-duplicate by day: keep the last snapshot per DATE(as_of)
    by_day: dict[str, SnapshotModel] = {}
    for r in rows:
        key = r.as_of.date().isoformat()
        by_day[key] = r  # ascending order ensures last wins

    out = []
    for key in sorted(by_day.keys()):
        r = by_day[key]
        item = {
            "as_of": r.as_of,
            "regime": {
                "label": r.regime_label,
                "tilt": r.tilt,
                "score": r.score,
                "max_score": r.max_score,
            },
        }
        if not slim:
            item["snapshot_id"] = str(r.snapshot_id)
            item["frozen_inputs_id"] = str(r.frozen_inputs_id)
        out.append(item)
    return {"horizon": horizon, "days": days, "slim": slim, "items": out}


@router.get("/indicators/{indicator_id}/history")
def get_indicator_history(indicator_id: str, horizon: str = "1w", days: int = 180, db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days and days > 0 else None
    if cutoff:
        q = text(
            """
            SELECT s.as_of, si.value_numeric, si.z20, si.status, si.flip_trigger
            FROM snapshots s
            JOIN snapshot_indicators si ON si.snapshot_id = s.snapshot_id
            WHERE si.indicator_id = :iid AND s.horizon = :h AND s.as_of >= :cut
            ORDER BY s.as_of ASC
            """
        )
        rows = db.execute(q, {"iid": indicator_id, "h": horizon, "cut": cutoff}).mappings().all()
    else:
        q = text(
            """
            SELECT s.as_of, si.value_numeric, si.z20, si.status, si.flip_trigger
            FROM snapshots s
            JOIN snapshot_indicators si ON si.snapshot_id = s.snapshot_id
            WHERE si.indicator_id = :iid AND s.horizon = :h
            ORDER BY s.as_of ASC
            """
        )
        rows = db.execute(q, {"iid": indicator_id, "h": horizon}).mappings().all()

    # de-dup by day
    by_day: dict[str, dict] = {}
    for r in rows:
        key = r["as_of"].date().isoformat()
        by_day[key] = dict(r)
    items = [{
        "as_of": v["as_of"],
        "value_numeric": float(v["value_numeric"]) if v["value_numeric"] is not None else None,
        "z20": float(v["z20"]) if v["z20"] is not None else None,
        "status": v["status"],
        "flip_trigger": v["flip_trigger"],
    } for k, v in sorted(by_day.items())]
    return {"indicator_id": indicator_id, "horizon": horizon, "days": days, "items": items}


