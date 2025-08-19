from datetime import date, datetime, timezone

from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from app.db import SessionLocal
from app.models import IndicatorRegistry
from app.ingest import upsert_series_vintages


client = TestClient(app)


def seed_with_missing_and_present(session):
    session.execute(text("DELETE FROM snapshot_indicators"))
    session.execute(text("DELETE FROM snapshots"))
    session.execute(text("DELETE FROM frozen_inputs"))
    session.execute(text("DELETE FROM series_vintages"))
    session.execute(text("DELETE FROM indicator_registry"))
    session.commit()

    # One indicator with real data (TGA), one with no data (BOJ_ASSETS), and one with no series declared
    session.add_all([
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
        IndicatorRegistry(
            indicator_id="boj_bs",
            name="BoJ balance sheet 1w Δ (local)",
            category="global",
            series_json=["BOJ_ASSETS"],  # no data will be seeded for this series
            cadence="weekly",
            directionality="higher_is_supportive",
            trigger_default="acceleration => supportive",
            scoring="z",
        ),
        IndicatorRegistry(
            indicator_id="no_series",
            name="No series indicator",
            category="stress",
            series_json=[],  # explicitly empty -> should be treated as n/a
            cadence="daily",
            directionality="higher_is_draining",
            trigger_default="> 0 => headwind",
            scoring="z",
        ),
    ])
    session.commit()

    # Seed only TGA so that tga_delta is available
    days = [date(2025, 8, d) for d in range(1, 25)]
    for idx, d in enumerate(days):
        upsert_series_vintages(
            session,
            "TGA",
            [
                {
                    "observation_date": d,
                    "vintage_date": None,
                    "publication_date": None,
                    "fetched_at": datetime(2025, 8, 25, tzinfo=timezone.utc),
                    "value_numeric": 800.0 + idx,
                }
            ],
            units="USD",
            scale=1.0,
            source="DTS",
        )


def test_snapshot_and_router_exclude_missing():
    session = SessionLocal()
    try:
        seed_with_missing_and_present(session)

        # Snapshot should include tga_delta and exclude boj_bs and no_series
        r = client.get("/snapshot?horizon=1w&k=10")
        assert r.status_code == 200
        js = r.json()
        ids = {row["id"] for row in js["indicators"]}
        assert "tga_delta" in ids
        assert "boj_bs" not in ids
        assert "no_series" not in ids

        # Router should also exclude indicators without data
        r2 = client.get("/router?horizon=1w&k=10")
        assert r2.status_code == 200
        js2 = r2.json()
        pick_ids = {p["id"] for p in js2["picks"]}
        assert "tga_delta" in pick_ids
        assert "boj_bs" not in pick_ids
        assert "no_series" not in pick_ids
    finally:
        session.close()


