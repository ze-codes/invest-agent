from datetime import date, datetime, timezone, timedelta

from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from app.db import SessionLocal
from app.models import IndicatorRegistry
from app.ingest import upsert_series_vintages


client = TestClient(app)


def reset_db(session):
    session.execute(text("DELETE FROM snapshot_indicators"))
    session.execute(text("DELETE FROM snapshots"))
    session.execute(text("DELETE FROM frozen_inputs"))
    session.execute(text("DELETE FROM series_vintages"))
    session.execute(text("DELETE FROM indicator_registry"))
    session.commit()


def seed_series(session, sid: str, values: list[float], start_day: int = 1):
    base = datetime(2025, 8, 25, tzinfo=timezone.utc)
    days = [date(2025, 8, start_day + i) for i in range(len(values))]
    for idx, d in enumerate(days):
        upsert_series_vintages(
            session,
            sid,
            [
                {
                    "observation_date": d,
                    "vintage_date": None,
                    "publication_date": None,
                    "fetched_at": base + timedelta(minutes=idx),
                    "value_numeric": values[idx],
                }
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )


def test_persistence_hysteresis():
    session = SessionLocal()
    try:
        reset_db(session)
        # Indicator with persistence=2 and z cutoff 1.0
        session.add(
            IndicatorRegistry(
                indicator_id="p2",
                name="Persistence 2",
                category="core_plumbing",
                series_json=["P2"],
                cadence="daily",
                directionality="higher_is_supportive",
                trigger_default="z20 >= +1",
                scoring="z",
                z_cutoff=1.0,
                persistence=2,
            )
        )
        session.commit()

        # Case A: only the last point is a strong positive outlier → should NOT flip due to persistence=2
        values = [0.0] * 19 + [10.0]
        seed_series(session, "P2", values)
        r = client.get("/snapshot?horizon=1w&k=5")
        assert r.status_code == 200
        js = r.json()
        # Find p2 row
        row = next((it for it in js["indicators"] if it["id"] == "p2"), None)
        # p2 might be included depending on |z| vs others; if not, increase k or filter by id
        if row is None:
            # Increase K to force inclusion
            r = client.get("/snapshot?horizon=1w&k=10")
            js = r.json()
            row = next((it for it in js["indicators"] if it["id"] == "p2"), None)
        assert row is not None
        assert row["status"] == "0"  # no flip yet due to persistence requirement

        # Case B: make the last two points strong positives → should flip to +1
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="p2",
                name="Persistence 2",
                category="core_plumbing",
                series_json=["P2"],
                cadence="daily",
                directionality="higher_is_supportive",
                trigger_default="z20 >= +1",
                scoring="z",
                z_cutoff=1.0,
                persistence=2,
            )
        )
        session.commit()
        values = [0.0] * 18 + [10.0, 10.0]
        seed_series(session, "P2", values)
        r2 = client.get("/snapshot?horizon=1w&k=10")
        assert r2.status_code == 200
        js2 = r2.json()
        row2 = next((it for it in js2["indicators"] if it["id"] == "p2"), None)
        assert row2 is not None
        assert row2["status"] == "+1"
    finally:
        session.close()


def test_buckets_representative_and_aggregate():
    session = SessionLocal()
    try:
        reset_db(session)
        # Root bucket with two members
        session.add_all(
            [
                IndicatorRegistry(
                    indicator_id="root_a",
                    name="Root A",
                    category="core_plumbing",
                    series_json=["X1"],
                    cadence="daily",
                    directionality="higher_is_supportive",
                    trigger_default="z20 >= +1",
                    scoring="z",
                    z_cutoff=1.0,
                ),
                IndicatorRegistry(
                    indicator_id="a1",
                    name="A1",
                    category="core_plumbing",
                    series_json=["X1"],
                    cadence="daily",
                    directionality="higher_is_supportive",
                    trigger_default="z20 >= +1",
                    scoring="z",
                    z_cutoff=1.0,
                    duplicates_of="root_a",
                ),
                IndicatorRegistry(
                    indicator_id="a2",
                    name="A2",
                    category="core_plumbing",
                    series_json=["X2"],
                    cadence="daily",
                    directionality="higher_is_supportive",
                    trigger_default="z20 >= +1",
                    scoring="z",
                    z_cutoff=1.0,
                    duplicates_of="root_a",
                ),
            ]
        )
        session.commit()

        # Make X1 flat so z is None/0; make X2 with a clear last-point deviation to have |z| > 0
        seed_series(session, "X1", [1.0] * 20)
        seed_series(session, "X2", [0.0] * 19 + [1.0])

        r = client.get("/snapshot?horizon=1w&k=5")
        assert r.status_code == 200
        js = r.json()

        # Only one representative per bucket should appear
        ids = {row["id"] for row in js["indicators"]}
        assert "a2" in ids  # highest |z|
        # root_a and a1 should be suppressed from indicators list
        assert "root_a" not in ids
        assert "a1" not in ids

        # Buckets must include the aggregate with all members
        b = next((b for b in js["buckets"] if b["bucket"].endswith("/root_a")), None)
        assert b is not None
        assert set(b["members"]) == {"root_a", "a1", "a2"}
        # Aggregate status should be +1 (all positive contributions)
        assert b["aggregate_status"] == "+1"
    finally:
        session.close()


