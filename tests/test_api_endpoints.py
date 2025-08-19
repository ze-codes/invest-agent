from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from app.db import SessionLocal
from app.models import IndicatorRegistry
from app.ingest import upsert_series_vintages


client = TestClient(app)


def test_indicators_typed_response():
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM snapshot_indicators"))
        session.execute(text("DELETE FROM snapshots"))
        session.execute(text("DELETE FROM frozen_inputs"))
        session.execute(text("DELETE FROM indicator_registry"))
        session.commit()

        rec = IndicatorRegistry(
            indicator_id="rrp_delta",
            name="ON RRP 5d Δ",
            category="core_plumbing",
            series_json=["RRPONTSYD"],
            cadence="daily",
            directionality="lower_is_supportive",
            trigger_default="Δ <= -100e9/5d",
            scoring="z",
        )
        session.add(rec)
        session.commit()

        r = client.get("/indicators")
        assert r.status_code == 200
        js = r.json()
        assert isinstance(js, list) and len(js) == 1
        assert js[0]["id"] == "rrp_delta"
        assert js[0]["series"] == ["RRPONTSYD"]
    finally:
        session.close()


def test_series_latest_and_as_of():
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM series_vintages"))
        session.commit()

        obs = date(2025, 8, 1)
        t0 = datetime(2025, 8, 2, 12, tzinfo=timezone.utc)
        t1 = datetime(2025, 8, 15, 12, tzinfo=timezone.utc)

        # Insert two versions for same observation via ingestion helper
        upsert_series_vintages(
            session,
            "X",
            [
                {"observation_date": obs, "vintage_date": None, "publication_date": None, "fetched_at": t0, "value_numeric": 100.0},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )
        upsert_series_vintages(
            session,
            "X",
            [
                {"observation_date": obs, "vintage_date": None, "publication_date": None, "fetched_at": t1, "value_numeric": 110.0},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )

        r_latest = client.get("/series/X")
        assert r_latest.status_code == 200
        js = r_latest.json()
        assert js["series_id"] == "X"
        assert len(js["points"]) == 1
        assert js["points"][0]["value_numeric"] == 110.0

        r_asof = client.get(f"/series/X?as_of={t0.isoformat().replace('+00:00','Z')}")
        assert r_asof.status_code == 200
        js2 = r_asof.json()
        assert len(js2["points"]) == 1
        assert js2["points"][0]["value_numeric"] == 100.0
    finally:
        session.close()


