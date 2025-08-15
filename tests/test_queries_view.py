from datetime import date, datetime, timezone, timedelta

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.ingest import upsert_series_vintages
from app.queries import get_latest_series_values, get_as_of_series_values


@pytest.mark.integration
def test_series_latest_view_and_as_of(monkeypatch):
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM series_vintages"))
        session.commit()

        obs = date(2025, 8, 1)
        t0 = datetime(2025, 8, 2, 12, tzinfo=timezone.utc)
        t1 = datetime(2025, 8, 15, 12, tzinfo=timezone.utc)

        # Initial print
        upsert_series_vintages(session, "X", [
            {"observation_date": obs, "vintage_date": None, "publication_date": None, "fetched_at": t0, "value_numeric": 100.0},
        ], units="USD", scale=1.0, source="TEST")

        # Revised value later
        upsert_series_vintages(session, "X", [
            {"observation_date": obs, "vintage_date": None, "publication_date": None, "fetched_at": t1, "value_numeric": 110.0},
        ], units="USD", scale=1.0, source="TEST")

        latest = get_latest_series_values(session, ["X"])
        assert len(latest) == 1
        assert float(latest[0]["value_numeric"]) == 110.0

        as_of_rows = get_as_of_series_values(session, "X", as_of=t0)
        assert len(as_of_rows) == 1
        assert float(as_of_rows[0]["value_numeric"]) == 100.0
    finally:
        session.close()


