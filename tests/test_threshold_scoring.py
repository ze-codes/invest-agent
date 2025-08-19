from datetime import date, datetime, timezone, timedelta

from sqlalchemy import text
from fastapi.testclient import TestClient

from api.main import app
from app.db import SessionLocal
from app.models import IndicatorRegistry
from app.ingest import upsert_series_vintages
from app.models import QTCap


client = TestClient(app)


def reset_db(session):
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
            units="percent",
            scale=1.0,
            source="TEST",
        )


def test_sofr_iorb_threshold_persistence():
    session = SessionLocal()
    try:
        reset_db(session)
        # persistence=3 -> need 3 consecutive days with SOFR > IORB
        session.add(
            IndicatorRegistry(
                indicator_id="sofr_iorb",
                name="SOFR - IORB",
                category="floor",
                series_json=["SOFR", "IORB"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 0 bps persistent",
                scoring="threshold",
                persistence=3,
            )
        )
        session.commit()

        # Case A: only 2 consecutive days > 0 -> should not flip (status 0)
        seed_series(session, "SOFR", [5.0, 5.0, 5.0, 5.1, 5.1])
        seed_series(session, "IORB", [5.0, 5.0, 5.0, 5.0, 5.0])
        r = client.get("/snapshot?horizon=1w&k=10")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "sofr_iorb")
        assert row["status"] == "0"

        # Case B: 3 consecutive days > 0 -> should flip to -1 (draining)
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="sofr_iorb",
                name="SOFR - IORB",
                category="floor",
                series_json=["SOFR", "IORB"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 0 bps persistent",
                scoring="threshold",
                persistence=3,
            )
        )
        session.commit()
        seed_series(session, "SOFR", [5.0, 5.0, 5.1, 5.1, 5.1])
        seed_series(session, "IORB", [5.0, 5.0, 5.0, 5.0, 5.0])
        r2 = client.get("/snapshot?horizon=1w&k=10")
        js2 = r2.json()
        row2 = next(it for it in js2["indicators"] if it["id"] == "sofr_iorb")
        assert row2["status"] == "-1"  # higher_is_draining -> negative contribution
    finally:
        session.close()



def test_bill_rrp_threshold_persistence():
    session = SessionLocal()
    try:
        reset_db(session)
        # persistence=2; threshold > +25 bps => supportive (+1)
        session.add(
            IndicatorRegistry(
                indicator_id="bill_rrp",
                name="1–3m bill - RRP (bps)",
                category="floor",
                series_json=["BILL_RRP_BPS"],
                cadence="daily",
                directionality="higher_is_supportive",
                trigger_default="> +25 bps => RRP drain likely",
                scoring="threshold",
                persistence=2,
            )
        )
        session.commit()
        # Case A: last 2 observations above 25 -> flips to +1
        seed_series(session, "BILL_RRP_BPS", [10, 15, 20, 30, 35])
        r = client.get("/snapshot?horizon=1w&k=10")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "bill_rrp")
        assert row["status"] == "+1"

        # Case B: not enough consecutive obs above threshold -> stays 0
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="bill_rrp",
                name="1–3m bill - RRP (bps)",
                category="floor",
                series_json=["BILL_RRP_BPS"],
                cadence="daily",
                directionality="higher_is_supportive",
                trigger_default="> +25 bps => RRP drain likely",
                scoring="threshold",
                persistence=2,
            )
        )
        session.commit()
        seed_series(session, "BILL_RRP_BPS", [10, 26, 24, 25, 26])  # only last 1 > 25
        r2 = client.get("/snapshot?horizon=1w&k=10")
        js2 = r2.json()
        row2 = next(it for it in js2["indicators"] if it["id"] == "bill_rrp")
        assert row2["status"] == "0"
    finally:
        session.close()


def test_ofr_liq_idx_threshold_percentile_persistence():
    session = SessionLocal()
    try:
        reset_db(session)
        # persistence=2; threshold = 80th percentile of recent window -> higher_is_draining => -1 when met
        session.add(
            IndicatorRegistry(
                indicator_id="ofr_liq_idx",
                name="OFR UST Liquidity Stress Index",
                category="stress",
                series_json=["OFR_LIQ_IDX"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 80th pct => illiquid",
                scoring="threshold",
                persistence=2,
            )
        )
        session.commit()
        # Build 30 obs ascending; 80th percentile ~ value >= 23 for 0..29
        vals = list(range(0, 28)) + [24, 25]
        seed_series(session, "OFR_LIQ_IDX", vals)
        r = client.get("/snapshot?horizon=1w&k=20")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "ofr_liq_idx")
        assert row["status"] == "-1"

        # Not met: only last 1 above percentile
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="ofr_liq_idx",
                name="OFR UST Liquidity Stress Index",
                category="stress",
                series_json=["OFR_LIQ_IDX"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 80th pct => illiquid",
                scoring="threshold",
                persistence=2,
            )
        )
        session.commit()
        vals2 = list(range(0, 28)) + [22, 24]  # only last 1 clearly above ~23
        seed_series(session, "OFR_LIQ_IDX", vals2)
        r2 = client.get("/snapshot?horizon=1w&k=20")
        js2 = r2.json()
        row2 = next((it for it in js2["indicators"] if it["id"] == "ofr_liq_idx"), None)
        # Could be absent if not included in top-K; ensure present or force higher k above.
        assert row2 is not None
        assert row2["status"] == "0"
    finally:
        session.close()


def test_bill_share_threshold():
    session = SessionLocal()
    try:
        reset_db(session)
        # Add registry entry: >= 65% supportive, persistence=1
        session.add(
            IndicatorRegistry(
                indicator_id="bill_share",
                name="Bill share of issuance (%)",
                category="supply",
                series_json=["UST_AUCTION_OFFERINGS"],
                cadence="sched",
                directionality="higher_is_supportive",
                trigger_default=">= 65% => less drain",
                scoring="threshold",
                persistence=1,
            )
        )
        session.commit()

        # Seed offerings: two days, with bills dominating on the latest
        # Total offerings by auction date
        seed_series(session, "UST_AUCTION_OFFERINGS", [100.0, 200.0, 150.0])
        # Bill-only offerings by auction date
        seed_series(session, "UST_BILL_OFFERINGS", [30.0, 120.0, 110.0])  # latest = 110/150 ≈ 73.3%

        r = client.get("/snapshot?horizon=1w&k=20")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "bill_share")
        assert row["status"] == "+1"

        # Now set latest below 65%
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="bill_share",
                name="Bill share of issuance (%)",
                category="supply",
                series_json=["UST_AUCTION_OFFERINGS"],
                cadence="sched",
                directionality="higher_is_supportive",
                trigger_default=">= 65% => less drain",
                scoring="threshold",
                persistence=1,
            )
        )
        session.commit()
        seed_series(session, "UST_AUCTION_OFFERINGS", [100.0, 200.0, 150.0])
        seed_series(session, "UST_BILL_OFFERINGS", [30.0, 120.0, 80.0])  # latest = 80/150 ≈ 53.3%
        r2 = client.get("/snapshot?horizon=1w&k=20")
        js2 = r2.json()
        row2 = next(it for it in js2["indicators"] if it["id"] == "bill_share")
        assert row2["status"] == "0"
    finally:
        session.close()


def test_facility_backstops_threshold_persistence():
    session = SessionLocal()
    try:
        reset_db(session)
        # SRF_USAGE: > 0 persistent => tight (draining)
        session.add(
            IndicatorRegistry(
                indicator_id="srf_usage",
                name="Standing Repo Facility usage (daily)",
                category="floor",
                series_json=["SRF_USAGE"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 0 persistent => tight",
                scoring="threshold",
                persistence=2,
            )
        )
        # FIMA_REPO similar
        session.add(
            IndicatorRegistry(
                indicator_id="fima_repo",
                name="FIMA repo usage (daily)",
                category="floor",
                series_json=["FIMA_REPO"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 0 persistent => tight",
                scoring="threshold",
                persistence=2,
            )
        )
        # DISCOUNT_WINDOW weekly
        session.add(
            IndicatorRegistry(
                indicator_id="discount_window",
                name="Discount window primary credit",
                category="floor",
                series_json=["DISCOUNT_WINDOW"],
                cadence="weekly",
                directionality="higher_is_draining",
                trigger_default="> 0 => stress",
                scoring="threshold",
                persistence=1,
            )
        )
        session.commit()

        # Seed SRF: last 2 > 0 → should flip -1
        seed_series(session, "SRF_USAGE", [0.0, 0.0, 1.0, 2.0])
        # Seed FIMA: only last 1 > 0 → should stay 0
        seed_series(session, "FIMA_REPO", [0.0, 0.0, 0.0, 1.0])
        # Seed Discount window weekly: > 0 → -1
        seed_series(session, "DISCOUNT_WINDOW", [0.0, 5.0])

        r = client.get("/snapshot?horizon=1w&k=20")
        js = r.json()
        srf = next(it for it in js["indicators"] if it["id"] == "srf_usage")
        fima = next(it for it in js["indicators"] if it["id"] == "fima_repo")
        dw = next(it for it in js["indicators"] if it["id"] == "discount_window")
        assert srf["status"] == "-1"
        assert fima["status"] == "0"
        assert dw["status"] == "-1"
    finally:
        session.close()


def test_qt_pace_vs_caps_threshold():
    session = SessionLocal()
    try:
        # Reset DB including qt_caps
        reset_db(session)
        session.execute(text("DELETE FROM qt_caps"))
        session.commit()

        # Add registry entry for qt_pace (threshold '@cap')
        session.add(
            IndicatorRegistry(
                indicator_id="qt_pace",
                name="UST/MBS runoff vs caps",
                category="qt_qe",
                series_json=["WSHOSHO", "WSHOMCB"],
                cadence="weekly",
                directionality="higher_is_draining",
                trigger_default="@cap => headwind",
                scoring="threshold",
                persistence=1,
            )
        )
        # Insert caps (weekly)
        session.add_all(
            [
                QTCap(effective_date=date(2025, 1, 1), ust_cap_usd_week=9.0, mbs_cap_usd_week=8.0),
            ]
        )
        session.commit()

        # Case A: holdings fall by >= cap → status -1
        # WSHOSHO: 100 -> 90 => runoff 10 (>= 9 cap)
        # WSHOMCB: 200 -> 195 => runoff 5 (< 8 cap)
        upsert_series_vintages(
            session,
            "WSHOSHO",
            [
                {"observation_date": date(2025, 8, 1), "value_numeric": 100.0, "vintage_date": None, "publication_date": None},
                {"observation_date": date(2025, 8, 8), "value_numeric": 90.0, "vintage_date": None, "publication_date": None},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )
        upsert_series_vintages(
            session,
            "WSHOMCB",
            [
                {"observation_date": date(2025, 8, 1), "value_numeric": 200.0, "vintage_date": None, "publication_date": None},
                {"observation_date": date(2025, 8, 8), "value_numeric": 195.0, "vintage_date": None, "publication_date": None},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )

        r = client.get("/snapshot?horizon=1w&k=20")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "qt_pace")
        assert row["status"] == "-1"

        # Case B: below caps → status 0
        reset_db(session)
        session.execute(text("DELETE FROM qt_caps"))
        session.commit()
        session.add(
            IndicatorRegistry(
                indicator_id="qt_pace",
                name="UST/MBS runoff vs caps",
                category="qt_qe",
                series_json=["WSHOSHO", "WSHOMCB"],
                cadence="weekly",
                directionality="higher_is_draining",
                trigger_default="@cap => headwind",
                scoring="threshold",
                persistence=1,
            )
        )
        session.add(QTCap(effective_date=date(2025, 1, 1), ust_cap_usd_week=15.0, mbs_cap_usd_week=12.0))
        session.commit()

        upsert_series_vintages(
            session,
            "WSHOSHO",
            [
                {"observation_date": date(2025, 8, 1), "value_numeric": 100.0, "vintage_date": None, "publication_date": None},
                {"observation_date": date(2025, 8, 8), "value_numeric": 95.0, "vintage_date": None, "publication_date": None},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )
        upsert_series_vintages(
            session,
            "WSHOMCB",
            [
                {"observation_date": date(2025, 8, 1), "value_numeric": 200.0, "vintage_date": None, "publication_date": None},
                {"observation_date": date(2025, 8, 8), "value_numeric": 197.0, "vintage_date": None, "publication_date": None},
            ],
            units="USD",
            scale=1.0,
            source="TEST",
        )

        r2 = client.get("/snapshot?horizon=1w&k=20")
        js2 = r2.json()
        row2 = next(it for it in js2["indicators"] if it["id"] == "qt_pace")
        assert row2["status"] == "0"
    finally:
        session.close()


def test_provenance_threshold_sofr_iorb_includes_threshold_and_streak():
    session = SessionLocal()
    try:
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="sofr_iorb",
                name="SOFR - IORB",
                category="floor",
                series_json=["SOFR", "IORB"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 0 bps persistent",
                scoring="threshold",
                persistence=2,
            )
        )
        session.commit()
        # two last days > 0 bps
        seed_series(session, "SOFR", [5.0, 5.0, 5.1, 5.2])
        seed_series(session, "IORB", [5.0, 5.0, 5.0, 5.0])
        r = client.get("/snapshot?horizon=1w&k=10")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "sofr_iorb")
        prov = row["provenance"]
        assert prov["series"] == ["SOFR", "IORB"]
        assert prov["threshold"]["op"] == ">"
        assert prov["threshold"]["value"] == 0.0
        assert "streak" in prov and prov["streak"]["required"] == 2
        assert prov["observation_date"] is not None
    finally:
        session.close()


def test_provenance_threshold_ofr_includes_percentile_and_streak():
    session = SessionLocal()
    try:
        reset_db(session)
        session.add(
            IndicatorRegistry(
                indicator_id="ofr_liq_idx",
                name="OFR UST Liquidity Stress Index",
                category="stress",
                series_json=["OFR_LIQ_IDX"],
                cadence="daily",
                directionality="higher_is_draining",
                trigger_default="> 80th pct => illiquid",
                scoring="threshold",
                persistence=1,
            )
        )
        session.commit()
        # Ascending values so last is above 80th pct
        vals = list(range(0, 30))
        seed_series(session, "OFR_LIQ_IDX", vals)
        r = client.get("/snapshot?horizon=1w&k=10")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "ofr_liq_idx")
        prov = row["provenance"]
        assert prov["series"] == ["OFR_LIQ_IDX"]
        assert prov["threshold"]["type"] == "percentile"
        assert prov["threshold"]["pct"] == 80.0
        assert prov["threshold"]["cutoff_value"] is not None
        assert "streak" in prov
        assert prov["observation_date"] is not None
    finally:
        session.close()


def test_provenance_z_based_includes_observation_and_source_fields():
    session = SessionLocal()
    try:
        reset_db(session)
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
        # Seed a handful of weekly points
        seed_series(session, "RESPPLLOPNWW", [1.0, 1.1, 1.2, 1.0, 0.9])
        r = client.get("/snapshot?horizon=1w&k=10")
        js = r.json()
        row = next(it for it in js["indicators"] if it["id"] == "reserves_w")
        prov = row["provenance"]
        assert prov["series"] == ["RESPPLLOPNWW"]
        assert "observation_date" in prov
        # optional fields may be null in tests, but keys should exist or not raise
        # fetched_at present from upsert
        assert "fetched_at" in prov
    finally:
        session.close()

