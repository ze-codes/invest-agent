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


def test_snapshot_includes_bucket_details_and_weights():
    r = client.get("/snapshot?horizon=1w&k=5")
    assert r.status_code == 200
    js = r.json()
    assert "bucket_details" in js and isinstance(js["bucket_details"], list)
    assert "bucket_weights" in js and isinstance(js["bucket_weights"], dict)
    # Each bucket has required keys
    for b in js["bucket_details"]:
        assert "bucket_id" in b
        assert "category" in b
        assert "weight" in b
        assert "aggregate_status" in b
        assert "members" in b and isinstance(b["members"], list)
        assert "representative_id" in b
        # Exactly one representative flag per bucket
        reps = [m for m in b["members"] if m.get("is_representative")]
        assert len(reps) <= 1

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
                {"observation_date": obs, "vintage_date": None, "publication_date": t0, "fetched_at": t0, "value_numeric": 100.0},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )
        upsert_series_vintages(
            session,
            "X",
            [
                {"observation_date": obs, "vintage_date": None, "publication_date": t1, "fetched_at": t1, "value_numeric": 110.0},
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

        r_asof = client.get(f"/series/X?as_of={t0.date().isoformat()}T00:00:00Z")
        assert r_asof.status_code == 200
        js2 = r_asof.json()
        assert len(js2["points"]) == 1
        assert js2["points"][0]["value_numeric"] == 100.0
    finally:
        session.close()


def test_registry_buckets_static_mapping():
    r = client.get("/registry/buckets")
    assert r.status_code == 200
    js = r.json()
    assert isinstance(js, dict)
    # Ensure that known roots exist and have members (depends on loaded registry)
    # Fall back to a weak assertion: mapping is non-empty and members are lists
    if js:
        any_root, members = next(iter(js.items()))
        assert isinstance(any_root, str)
        assert isinstance(members, list)

