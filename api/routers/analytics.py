from fastapi import APIRouter, Depends
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import SnapshotResponse, RouterResponse
from app.snapshot import compute_snapshot, compute_router


router = APIRouter()


@router.get("/snapshot", response_model=SnapshotResponse)
def get_snapshot(horizon: str, k: int = 8, full: bool = False, as_of: Optional[str] = None, db: Session = Depends(get_db)):
    as_of_dt = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except Exception:
            as_of_dt = None
    snap = compute_snapshot(db, horizon=horizon, k=k, as_of=as_of_dt)
    return snap


@router.get("/router", response_model=RouterResponse)
def get_router(horizon: str, k: int = 8, db: Session = Depends(get_db)):
    res = compute_router(db, horizon=horizon, k=k)
    return res


