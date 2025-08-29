from typing import List, Dict

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

@router.get("/registry/buckets")
def get_registry_buckets(db: Session = Depends(get_db)) -> Dict[str, List[str]]:
    """Return static mapping of bucket roots to member indicator IDs.

    Root is `duplicates_of` if present, else the indicator itself.
    """
    rows = db.query(IndicatorRegistry).order_by(IndicatorRegistry.indicator_id).all()
    reg_by_id = {r.indicator_id: r for r in rows}
    def root_id(indicator_id: str) -> str:
        r = reg_by_id.get(indicator_id)
        if r is None:
            return indicator_id
        return r.duplicates_of or indicator_id
    buckets: Dict[str, List[str]] = {}
    for r in rows:
        rid = root_id(r.indicator_id)
        buckets.setdefault(rid, []).append(r.indicator_id)
    # Sort members for stable output
    for rid in buckets.keys():
        buckets[rid].sort()
    return buckets



