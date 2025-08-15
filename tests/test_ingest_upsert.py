from datetime import date, datetime, timezone

from app.ingest import upsert_series_vintages
from app.models import SeriesVintage
from app.db import SessionLocal, engine
from sqlalchemy import text


def test_upsert_series_vintages_idempotent(tmp_path, monkeypatch):
    # Use real DB connection configured for tests; assumes running Postgres per docker-compose
    session = SessionLocal()
    try:
        # Clean table for deterministic test
        session.execute(text("DELETE FROM series_vintages"))
        session.commit()

        rows = [
            {
                "observation_date": date(2025, 8, 11),
                "vintage_date": None,
                "publication_date": None,
                "fetched_at": datetime.now(timezone.utc),
                "value_numeric": 123.0,
            }
        ]

        n1 = upsert_series_vintages(session, "TEST_SERIES", rows, units="USD", scale=1.0, source="TEST")
        assert n1 == 1
        n2 = upsert_series_vintages(session, "TEST_SERIES", rows, units="USD", scale=1.0, source="TEST")
        assert n2 == 1

        # Ensure only one row exists and values persisted
        stored = session.query(SeriesVintage).filter(SeriesVintage.series_id == "TEST_SERIES").all()
        assert len(stored) == 1
        assert float(stored[0].value_numeric) == 123.0
    finally:
        session.close()


