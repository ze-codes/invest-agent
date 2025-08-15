from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import text


def get_latest_series_values(db: Session, series_ids: List[str]) -> List[Dict[str, Any]]:
    q = text(
        """
        SELECT series_id, observation_date, vintage_id, value_numeric, units, scale,
               source, source_url, source_version, vintage_date, publication_date, fetched_at
        FROM series_latest
        WHERE series_id = ANY(:ids)
        ORDER BY series_id, observation_date
        """
    )
    rows = db.execute(q, {"ids": series_ids}).mappings().all()
    return [dict(r) for r in rows]


def get_as_of_series_values(db: Session, series_id: str, as_of: datetime) -> List[Dict[str, Any]]:
    q = text(
        """
        SELECT * FROM series_vintages
        WHERE series_id = :sid AND fetched_at <= :as_of
        QUALIFY ROW_NUMBER() OVER (
          PARTITION BY observation_date
          ORDER BY COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC, fetched_at DESC
        ) = 1
        ORDER BY observation_date
        """
    )
    # The QUALIFY clause is not standard Postgres; emulate via subquery
    q = text(
        """
        SELECT * FROM (
          SELECT sv.*, ROW_NUMBER() OVER (
            PARTITION BY observation_date
            ORDER BY COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC, fetched_at DESC
          ) AS rn
          FROM series_vintages sv
          WHERE sv.series_id = :sid AND sv.fetched_at <= :as_of
        ) t
        WHERE t.rn = 1
        ORDER BY t.observation_date
        """
    )
    rows = db.execute(q, {"sid": series_id, "as_of": as_of}).mappings().all()
    return [dict(r) for r in rows]


