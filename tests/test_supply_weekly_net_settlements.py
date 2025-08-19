from datetime import date, datetime, UTC

from sqlalchemy import text

from app.db import SessionLocal
from app.ingest import upsert_series_vintages
from app.supply import compute_weekly_net_settlements


def test_compute_weekly_net_settlements_issues_minus_redemptions_minus_interest():
    s = SessionLocal()
    try:
        # Clean
        s.execute(text("DELETE FROM series_vintages"))
        s.commit()

        now = datetime.now(UTC)
        # Seed one week
        week_monday = date(2025, 8, 11)  # Monday
        # Issues on Wed and Fri
        upsert_series_vintages(
            s,
            "UST_AUCTION_ISSUES",
            [
                {"observation_date": date(2025, 8, 13), "value_numeric": 100.0, "fetched_at": now},
                {"observation_date": date(2025, 8, 15), "value_numeric": 50.0, "fetched_at": now},
            ],
            units="USD",
            scale=1.0,
            source="DTS",
            source_url=None,
        )
        # Redemptions Tues and Thu (DTS in millions; simulate with scale=1e6 and values in millions)
        upsert_series_vintages(
            s,
            "UST_REDEMPTIONS",
            [
                {"observation_date": date(2025, 8, 12), "value_numeric": 20.0, "fetched_at": now},
                {"observation_date": date(2025, 8, 14), "value_numeric": 10.0, "fetched_at": now},
            ],
            units="USD",
            scale=1e6,
            source="DTS",
            source_url=None,
        )
        # Interest Mon (also in millions)
        upsert_series_vintages(
            s,
            "UST_INTEREST",
            [
                {"observation_date": date(2025, 8, 11), "value_numeric": 5.0, "fetched_at": now},
            ],
            units="USD",
            scale=1e6,
            source="DTS",
            source_url=None,
        )

        rows = compute_weekly_net_settlements(s, weeks_back=4)
        # One week returned
        assert len(rows) == 1
        r = rows[0]
        assert r["observation_date"] == week_monday
        # Net = (100+50) - (20e6+10e6) - (5e6)
        assert abs(float(r["value_numeric"]) - (150.0 - 20e6 - 10e6 - 5e6)) < 1e-6
    finally:
        s.close()


