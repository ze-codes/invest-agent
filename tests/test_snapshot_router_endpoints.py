from datetime import date, datetime, timezone

from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from app.db import SessionLocal
from app.models import IndicatorRegistry
from app.ingest import upsert_series_vintages


client = TestClient(app)


def seed_basic_data(session):
    session.execute(text("DELETE FROM snapshot_indicators"))
    session.execute(text("DELETE FROM snapshots"))
    session.execute(text("DELETE FROM frozen_inputs"))
    session.execute(text("DELETE FROM series_vintages"))
    session.execute(text("DELETE FROM indicator_registry"))
    session.commit()

    session.add_all([
        IndicatorRegistry(
            indicator_id="walcl",
            name="Fed balance sheet",
            category="core_plumbing",
            series_json=["WALCL"],
            cadence="weekly",
            directionality="higher_is_supportive",
            trigger_default="z20 >= +1",
            scoring="z",
        ),
        IndicatorRegistry(
            indicator_id="tga_delta",
            name="TGA 5d Δ",
            category="core_plumbing",
            series_json=["TGA"],
            cadence="daily",
            directionality="higher_is_draining",
            trigger_default="Δ >= +75e9/5d",
            scoring="z",
        ),
    ])
    session.commit()

    # Minimal series data
    days = [date(2025, 8, d) for d in range(1, 25)]
    for idx, d in enumerate(days):
        upsert_series_vintages(
            session,
            "TGA",
            [{"observation_date": d, "vintage_date": None, "publication_date": None, "fetched_at": datetime(2025, 8, 25, tzinfo=timezone.utc), "value_numeric": 800.0 + idx}],
            units="USD",
            scale=1.0,
            source="DTS",
        )
    weeks = [date(2025, 8, 1), date(2025, 8, 8), date(2025, 8, 15), date(2025, 8, 22)]
    for idx, d in enumerate(weeks):
        upsert_series_vintages(
            session,
            "WALCL",
            [{"observation_date": d, "vintage_date": None, "publication_date": None, "fetched_at": datetime(2025, 8, 25, tzinfo=timezone.utc), "value_numeric": 8500.0 + 10 * idx}],
            units="USD",
            scale=1e6,
            source="FRED",
        )


def test_snapshot_and_router_endpoints_basic():
    session = SessionLocal()
    try:
        seed_basic_data(session)
        r1 = client.get("/snapshot?horizon=1w&k=5")
        assert r1.status_code == 200
        js = r1.json()
        assert js["regime"]["label"] in ("Positive", "Neutral", "Negative")
        assert 0 < len(js["indicators"]) <= 5

        r2 = client.get("/router?horizon=1w&k=5")
        assert r2.status_code == 200
        js2 = r2.json()
        assert js2["horizon"] == "1w"
        assert 0 < len(js2["picks"]) <= 5
    finally:
        session.close()




