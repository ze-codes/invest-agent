from __future__ import annotations

from datetime import datetime, UTC
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SeriesVintage


def upsert_series_vintages(db: Session, series_id: str, rows: List[Dict[str, Any]], *, units: str, scale: float, source: str, source_url: str | None = None, source_version: str | None = None) -> int:
    count = 0
    for r in rows:
        observation_date = r["observation_date"]
        vintage_date = r.get("vintage_date")
        publication_date = r.get("publication_date")
        fetched_at = r.get("fetched_at") or datetime.now(UTC)
        # Do not derive publication_date; downstream queries will use fetched_at when publication_date is null.
        value_numeric = r["value_numeric"]

        filters = [
            SeriesVintage.series_id == series_id,
            SeriesVintage.observation_date == observation_date,
        ]
        if vintage_date is None:
            filters.append(SeriesVintage.vintage_date.is_(None))
        else:
            filters.append(SeriesVintage.vintage_date == vintage_date)
        if publication_date is None:
            filters.append(SeriesVintage.publication_date.is_(None))
        else:
            filters.append(SeriesVintage.publication_date == publication_date)

        existing = db.query(SeriesVintage).filter(*filters).first()

        if existing:
            existing.value_numeric = value_numeric
            existing.units = units
            existing.scale = scale
            existing.source = source
            existing.source_url = source_url
            existing.source_version = source_version
        else:
            db.add(
                SeriesVintage(
                    series_id=series_id,
                    observation_date=observation_date,
                    vintage_date=vintage_date,
                    publication_date=publication_date,
                    fetched_at=fetched_at,
                    value_numeric=value_numeric,
                    units=units,
                    scale=scale,
                    source=source,
                    source_url=source_url,
                    source_version=source_version,
                )
            )
        count += 1
    db.commit()
    return count


