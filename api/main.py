from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import os

from app.db import get_db
from app.models import IndicatorRegistry

app = FastAPI(title="invest-agent API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/indicators")
def list_indicators(db: Session = Depends(get_db)):
    rows = db.query(IndicatorRegistry).order_by(IndicatorRegistry.indicator_id).all()
    return [
        {
            "id": r.indicator_id,
            "name": r.name,
            "category": r.category,
            "series": r.series_json,
            "cadence": r.cadence,
            "directionality": r.directionality,
            "trigger_default": r.trigger_default,
            "scoring": r.scoring,
            "z_cutoff": float(r.z_cutoff) if r.z_cutoff is not None else None,
            "persistence": r.persistence,
            "duplicates_of": r.duplicates_of,
            "notes": r.notes,
        }
        for r in rows
    ]


