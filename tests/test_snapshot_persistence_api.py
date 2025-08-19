from datetime import date, datetime, timezone, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from app.db import SessionLocal
from app.ingest import upsert_series_vintages
from app.models import IndicatorRegistry


client = TestClient(app)


def reset_db(session):
    # Order matters due to FKs
    session.execute(text("DELETE FROM snapshot_indicators"))
    session.execute(text("DELETE FROM snapshots"))
    session.execute(text("DELETE FROM frozen_inputs"))
    session.execute(text("DELETE FROM series_vintages"))
    session.execute(text("DELETE FROM indicator_registry"))
    session.commit()


def seed_series(session, sid: str, values: list[float]):
    base = datetime(2025, 8, 25, tzinfo=timezone.utc)
    days = [date(2025, 8, 1 + i) for i in range(len(values))]
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


def test_events_recompute_and_history_endpoints():
    session = SessionLocal()
    try:
        reset_db(session)
        # Minimal registry: reserves_w (z-based)
        session.add(
            IndicatorRegistry(
                indicator_id="reserves_w",
                name="Reserve Balances 1w Δ",
                category="core_plumbing",
                series_json=["RESPPLLOPNWW"],
                cadence="weekly",
                directionality="higher_is_supportive",
                trigger_default="+25e9/w => supportive",
                scoring="z",
                z_cutoff=1.0,
                persistence=1,
            )
        )
        session.commit()
        seed_series(session, "RESPPLLOPNWW", [1.0, 1.1, 1.2, 1.0, 0.9])

        # Persist one snapshot via API
        r_post = client.post("/events/recompute")
        assert r_post.status_code == 200
        js_post = r_post.json()
        snap = js_post.get("snapshot", {})
        assert isinstance(snap.get("frozen_inputs_id"), str)
        assert snap.get("frozen_inputs_id") != "temp"

        # History should include at least one item
        r_hist = client.get("/snapshot/history?horizon=1w&days=7&slim=true")
        assert r_hist.status_code == 200
        js_hist = r_hist.json()
        items = js_hist.get("items", [])
        assert len(items) >= 1
        assert "as_of" in items[-1] and "regime" in items[-1]

        # Backfill last 3 days and ensure count grows
        r_bf = client.post("/events/backfill_history?horizon=1w&days=3")
        assert r_bf.status_code == 200
        js_bf = r_bf.json()
        assert js_bf.get("persisted") >= 4  # includes day 0
        r_hist2 = client.get("/snapshot/history?horizon=1w&days=7&slim=true")
        assert r_hist2.status_code == 200
        js_hist2 = r_hist2.json()
        assert len(js_hist2.get("items", [])) >= len(items)
    finally:
        session.close()


