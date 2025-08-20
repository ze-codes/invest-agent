from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import IndicatorRegistry, SeriesVintage
from app.schemas import IndicatorRegistryEntry
from app.snapshot import _resolve_series_id


router = APIRouter()


@router.get("/indicators", response_model=list[IndicatorRegistryEntry])
def list_indicators(only_available: bool = False, db: Session = Depends(get_db)):
    rows = db.query(IndicatorRegistry).order_by(IndicatorRegistry.indicator_id).all()

    def indicator_has_data(ind: IndicatorRegistry) -> bool:
        series_ids = ind.series_json or []
        if not series_ids:
            return False
        for sid in series_ids:
            resolved = _resolve_series_id(sid)
            exists = (
                db.query(SeriesVintage)
                .filter(SeriesVintage.series_id == resolved)
                .limit(1)
                .first()
                is not None
            )
            if exists:
                return True
        return False

    filtered = [r for r in rows if (indicator_has_data(r) if only_available else True)]

    return [
        IndicatorRegistryEntry(
            id=r.indicator_id,
            name=r.name,
            category=r.category,
            series=r.series_json,
            cadence=r.cadence,
            directionality=r.directionality,
            trigger_default=r.trigger_default,
            scoring=r.scoring,
            z_cutoff=float(r.z_cutoff) if r.z_cutoff is not None else None,
            persistence=r.persistence,
            duplicates_of=r.duplicates_of,
            notes=r.notes,
        )
        for r in filtered
    ]


@router.get("/indicators/list")
def list_indicator_ids(only_available: bool = False, db: Session = Depends(get_db)):
    rows = db.query(IndicatorRegistry).order_by(IndicatorRegistry.indicator_id).all()

    if not only_available:
        return [r.indicator_id for r in rows]

    # Filter to indicators that have at least one backing series with data
    out: list[str] = []
    for ind in rows:
        series_ids = ind.series_json or []
        has_any = False
        for sid in series_ids:
            resolved = _resolve_series_id(sid)
            if (
                db.query(SeriesVintage)
                .filter(SeriesVintage.series_id == resolved)
                .limit(1)
                .first()
                is not None
            ):
                has_any = True
                break
        if has_any:
            out.append(ind.indicator_id)
    return out


