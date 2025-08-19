from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import SnapshotResponse, RouterResponse
from app.snapshot import compute_snapshot, compute_router


router = APIRouter()


@router.get("/snapshot", response_model=SnapshotResponse)
def get_snapshot(horizon: str, k: int = 8, full: bool = False, db: Session = Depends(get_db)):
    snap = compute_snapshot(db, horizon=horizon, k=k)
    return snap


@router.get("/router", response_model=RouterResponse)
def get_router(horizon: str, k: int = 8, db: Session = Depends(get_db)):
    res = compute_router(db, horizon=horizon, k=k)
    return res


