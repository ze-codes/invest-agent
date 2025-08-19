from datetime import date, datetime, UTC, timedelta, timezone

from sqlalchemy import text

from app.db import SessionLocal
from app.ingest import upsert_series_vintages
from app.floor import compute_bill_rrp_points


def test_compute_bill_rrp_points_min_bill_minus_rrp_in_bps():
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM series_vintages"))
        s.commit()
        now = datetime.now(UTC)
        # Seed 2 days
        days = [date(2025, 8, 20), date(2025, 8, 21)]
        for i, d in enumerate(days):
            upsert_series_vintages(
                s,
                "DTB3",
                [{"observation_date": d, "value_numeric": 5.30 + i * 0.01, "fetched_at": now + timedelta(minutes=i)}],
                units="percent",
                scale=1.0,
                source="TEST",
            )
            upsert_series_vintages(
                s,
                "DTB4WK",
                [{"observation_date": d, "value_numeric": 5.20 + i * 0.01, "fetched_at": now + timedelta(minutes=i)}],
                units="percent",
                scale=1.0,
                source="TEST",
            )
            upsert_series_vintages(
                s,
                "RRP_RATE",
                [{"observation_date": d, "value_numeric": 5.05, "fetched_at": now + timedelta(minutes=i)}],
                units="percent",
                scale=1.0,
                source="TEST",
            )

        rows = compute_bill_rrp_points(s, days_back=10)
        # Expect two rows; spread = min(5.30,5.20) - 5.05 = 0.15 -> 15 bps (day 1)
        assert len(rows) == 2
        by_date = {str(r["observation_date"]): float(r["value_numeric"]) for r in rows}
        assert abs(by_date["2025-08-20"] - 15.0) < 1e-6
        # Day 2: min(5.31,5.21) - 5.05 = 0.16 -> 16 bps
        assert abs(by_date["2025-08-21"] - 16.0) < 1e-6
    finally:
        s.close()


