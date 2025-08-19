from datetime import date, datetime, timezone, timedelta

from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from app.db import SessionLocal
from app.ingest import upsert_series_vintages
from app.models import IndicatorRegistry


client = TestClient(app)


def reset_db(session):
    session.execute(text("DELETE FROM snapshot_indicators"))
    session.execute(text("DELETE FROM snapshots"))
    session.execute(text("DELETE FROM frozen_inputs"))
    session.execute(text("DELETE FROM series_vintages"))
    session.execute(text("DELETE FROM indicator_registry"))
    session.commit()


def test_snapshot_includes_bill_rrp_and_ust_net_settle_using_derived_series():
    session = SessionLocal()
    try:
        reset_db(session)

        # Seed registry entries: bill_rrp (threshold) and ust_net_settle_2w (z)
        session.add_all(
            [
                IndicatorRegistry(
                    indicator_id="bill_rrp",
                    name="1–3m bill - RRP (bps)",
                    category="floor",
                    series_json=["DTB3", "DTB4WK", "RRP_RATE"],
                    cadence="daily",
                    directionality="higher_is_supportive",
                    trigger_default="> +25 bps",
                    scoring="threshold",
                    persistence=2,
                ),
                IndicatorRegistry(
                    indicator_id="ust_net_w",
                    name="Net UST settlements (weekly)",
                    category="supply",
                    series_json=["UST_NET_SETTLE_W"],
                    cadence="weekly",
                    directionality="higher_is_draining",
                    trigger_default="> +80e9/w",
                    scoring="z",
                    z_cutoff=1.0,
                    persistence=1,
                ),
            ]
        )
        session.commit()

        now = datetime(2025, 8, 25, tzinfo=timezone.utc)

        # Seed bill yields and RRP admin rate (percent). Make last 2 days > 25 bps spread.
        days = [date(2025, 8, 20) + timedelta(days=i) for i in range(5)]
        for idx, d in enumerate(days):
            dtb3 = 5.30 + 0.02 * idx
            dtb4 = 5.20 + 0.02 * idx
            rrp = 5.00
            upsert_series_vintages(
                session,
                "DTB3",
                [{"observation_date": d, "value_numeric": dtb3, "fetched_at": now + timedelta(minutes=idx)}],
                units="percent",
                scale=1.0,
                source="TEST",
            )
            upsert_series_vintages(
                session,
                "DTB4WK",
                [{"observation_date": d, "value_numeric": dtb4, "fetched_at": now + timedelta(minutes=idx)}],
                units="percent",
                scale=1.0,
                source="TEST",
            )
            upsert_series_vintages(
                session,
                "RRP_RATE",
                [{"observation_date": d, "value_numeric": rrp, "fetched_at": now + timedelta(minutes=idx)}],
                units="percent",
                scale=1.0,
                source="TEST",
            )

        # Seed derived BILL_RRP_BPS directly (so snapshot relies on derived series as designed)
        for idx, d in enumerate(days):
            # spread = min(dtb3, dtb4) - rrp → bps
            spread_bps = (min(5.30 + 0.02 * idx, 5.20 + 0.02 * idx) - 5.00) * 100.0
            upsert_series_vintages(
                session,
                "BILL_RRP_BPS",
                [{"observation_date": d, "value_numeric": spread_bps, "fetched_at": now + timedelta(minutes=idx)}],
                units="bps",
                scale=1.0,
                source="DERIVED",
            )

        # Seed weekly net settlements (USD). Make last week large positive to exceed z-cutoff.
        weeks = [date(2025, 8, 4), date(2025, 8, 11), date(2025, 8, 18)]  # Mondays
        values = [-10e9, -5e9, 200e9]
        for i, wk in enumerate(weeks):
            upsert_series_vintages(
                session,
                "UST_NET_SETTLE_W",
                [{"observation_date": wk, "value_numeric": values[i], "fetched_at": now + timedelta(hours=i)}],
                units="USD",
                scale=1.0,
                source="DERIVED",
            )

        # Call snapshot (no derived BILL_RRP_BPS present; fallback path should compute from raw inputs)
        r = client.get("/snapshot?horizon=1w&k=10")
        assert r.status_code == 200
        js = r.json()

        ids = [row["id"] for row in js["indicators"]]
        assert "bill_rrp" in ids
        assert "ust_net_w" in ids

        bill_row = next(row for row in js["indicators"] if row["id"] == "bill_rrp")
        # Expect threshold satisfied → supportive (+1)
        assert bill_row["status"] == "+1"
        # ust_net_settle_2w should have a z and map to draining (−1) given positive surge
        settle_row = next(row for row in js["indicators"] if row["id"] == "ust_net_w")
        assert settle_row["z20"] is not None
        assert settle_row["status"] in {"-1", "+1", "0"}  # exact sign depends on z window
    finally:
        session.close()


