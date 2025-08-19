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


def get_latest_series_points(db: Session, series_id: str, limit: int = 40) -> List[Dict[str, Any]]:
    q = text(
        """
        SELECT * FROM (
          SELECT DISTINCT ON (series_id, observation_date)
            series_id, observation_date, vintage_id, value_numeric, units, scale,
            source, source_url, source_version, vintage_date, publication_date, fetched_at
          FROM series_vintages
          WHERE series_id = :sid
          ORDER BY series_id, observation_date,
                   COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC,
                   fetched_at DESC
        ) t
        ORDER BY observation_date DESC
        LIMIT :lim
        """
    )
    rows = db.execute(q, {"sid": series_id, "lim": limit}).mappings().all()
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: r["observation_date"])  # return ascending
    return out


def get_as_of_series_points(db: Session, series_id: str, as_of: datetime, limit: int = 40) -> List[Dict[str, Any]]:
    """Return at most `limit` series points as of a given timestamp.

    For each observation_date, pick the latest vintage available up to `as_of`,
    then return the last `limit` observations in ascending order.
    """
    q = text(
        """
        SELECT * FROM (
          SELECT DISTINCT ON (series_id, observation_date)
            series_id, observation_date, vintage_id, value_numeric, units, scale,
            source, source_url, source_version, vintage_date, publication_date, fetched_at
          FROM series_vintages
          WHERE series_id = :sid AND fetched_at <= :as_of
          ORDER BY series_id, observation_date,
                   COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC,
                   fetched_at DESC
        ) t
        ORDER BY observation_date DESC
        LIMIT :lim
        """
    )
    rows = db.execute(q, {"sid": series_id, "as_of": as_of, "lim": limit}).mappings().all()
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: r["observation_date"])  # return ascending
    return out


def get_as_of_series_points_by_pub(db: Session, series_id: str, as_of: datetime, limit: int = 40) -> List[Dict[str, Any]]:
    """Return points as of a date using publication/vintage timelines.

    Includes vintages with COALESCE(vintage_date, publication_date::date, fetched_at::date) <= as_of::date.
    This is useful for historical backfills when data was ingested recently.
    """
    q = text(
        """
        SELECT * FROM (
          SELECT DISTINCT ON (series_id, observation_date)
            series_id, observation_date, vintage_id, value_numeric, units, scale,
            source, source_url, source_version, vintage_date, publication_date, fetched_at
          FROM series_vintages
          WHERE series_id = :sid
            AND COALESCE(vintage_date, publication_date::date, fetched_at::date) <= CAST(:as_of AS date)
          ORDER BY series_id, observation_date,
                   COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC,
                   fetched_at DESC
        ) t
        ORDER BY observation_date DESC
        LIMIT :lim
        """
    )
    rows = db.execute(q, {"sid": series_id, "as_of": as_of, "lim": limit}).mappings().all()
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: r["observation_date"])  # ascending
    return out


def get_series_points_up_to_observation_date(db: Session, series_id: str, as_of: datetime, limit: int = 40) -> List[Dict[str, Any]]:
    """Return points with observation_date <= as_of (date-only cutoff).

    For each observation_date up to the cutoff, choose the most recent vintage
    (by COALESCE(vintage_date, publication_date::date, fetched_at::date), then fetched_at) so the
    time series reflects the best-known values for those observation dates.
    """
    q = text(
        """
        SELECT * FROM (
          SELECT DISTINCT ON (series_id, observation_date)
            series_id, observation_date, vintage_id, value_numeric, units, scale,
            source, source_url, source_version, vintage_date, publication_date, fetched_at
          FROM series_vintages
          WHERE series_id = :sid
            AND observation_date <= CAST(:as_of AS date)
          ORDER BY series_id, observation_date,
                   COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC,
                   fetched_at DESC
        ) t
        ORDER BY observation_date DESC
        LIMIT :lim
        """
    )
    rows = db.execute(q, {"sid": series_id, "as_of": as_of, "lim": limit}).mappings().all()
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: r["observation_date"])  # ascending
    return out


