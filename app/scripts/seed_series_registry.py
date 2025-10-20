from __future__ import annotations

from typing import Dict

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import SeriesRegistry


def upsert_series_registry(db: Session, entries: Dict[str, Dict]) -> int:
    count = 0
    for sid, meta in entries.items():
        rec = db.get(SeriesRegistry, sid)
        payload = {
            "series_id": sid,
            "cadence": meta.get("cadence"),
            "units": meta.get("units"),
            "scale": meta.get("scale"),
            "source": meta.get("source"),
            "notes": meta.get("notes"),
        }
        if rec:
            for k, v in payload.items():
                setattr(rec, k, v)
        else:
            rec = SeriesRegistry(**payload)
            db.add(rec)
        count += 1
    db.commit()
    return count


def main() -> None:
    # Initial seed derived from docs/indicator-registry.md (Series glossary)
    SEED: Dict[str, Dict] = {
        # Core plumbing / Fed balance sheet
        "WALCL": {"cadence": "weekly", "units": "USD", "scale": 1e6, "source": "FRED/H.4.1", "notes": "Fed total assets"},
        "RESPPLLOPNWW": {"cadence": "weekly", "units": "USD", "scale": 1e6, "source": "H.4.1", "notes": "Reserve balances"},
        # Money market floor / daily series
        "RRPONTSYD": {"cadence": "daily", "units": "USD", "scale": 1e6, "source": "FRED/ON RRP", "notes": "ON RRP outstanding"},
        "TGA": {"cadence": "daily", "units": "USD", "scale": 1e6, "source": "DTS", "notes": "Treasury General Account"},
        "SOFR": {"cadence": "daily", "units": "percent", "scale": 1.0, "source": "SOFR", "notes": "repo benchmark"},
        "IORB": {"cadence": "daily", "units": "percent", "scale": 1.0, "source": "Fed admin", "notes": "stepwise"},
        "RRP_RATE": {"cadence": "daily", "units": "percent", "scale": 1.0, "source": "Fed admin", "notes": "stepwise"},
        "DTB3": {"cadence": "daily", "units": "percent", "scale": 1.0, "source": "Treasury", "notes": "3m bill"},
        "DTB4WK": {"cadence": "daily", "units": "percent", "scale": 1.0, "source": "Treasury", "notes": "4w bill"},
        # QE/QT holdings
        "WSHOSHO": {"cadence": "weekly", "units": "USD", "scale": 1e6, "source": "H.4.1", "notes": "UST holdings"},
        "WSHOMCB": {"cadence": "weekly", "units": "USD", "scale": 1e6, "source": "H.4.1", "notes": "MBS holdings"},
        # Treasury supply (DTS)
        "UST_AUCTION_OFFERINGS": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "DTS", "notes": "sum by auction_date"},
        "UST_AUCTION_ISSUES": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "DTS", "notes": "sum by issue_date"},
        "UST_REDEMPTIONS": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "DTS", "notes": "marketable + savings only"},
        "UST_INTEREST": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "DTS", "notes": "interest/coupon outlays"},
        "UST_NET_SETTLE_W": {"cadence": "weekly", "units": "USD", "scale": 1.0, "source": "DERIVED", "notes": "issues - redemptions - interest"},
        # # Banking (H.8)
        # "H8_DEPOSITS": {"cadence": "weekly", "units": "USD", "scale": 1.0, "source": "H.8", "notes": "bank deposits"},
        # "H8_SECURITIES": {"cadence": "weekly", "units": "USD", "scale": 1.0, "source": "H.8", "notes": "bank securities"},
        # Stress / facilities
        # "SRF_USAGE": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "Fed SRF", "notes": "standing repo"},
        # "FIMA_REPO": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "Fed FIMA", "notes": "FIMA repo"},
        # "DISCOUNT_WINDOW": {"cadence": "weekly", "units": "USD", "scale": 1.0, "source": "Fed H.4.1", "notes": "primary credit outstanding"},
        "OFR_LIQ_IDX": {"cadence": "daily", "units": "index", "scale": 1.0, "source": "OFR", "notes": "UST liquidity stress"},
        # Global / deferred
        # "ECB_ASSETS": {"cadence": "weekly", "units": "local", "scale": 1.0, "source": "ECB", "notes": "ECB balance sheet"},
        # "BOJ_ASSETS": {"cadence": "weekly", "units": "local", "scale": 1.0, "source": "BoJ", "notes": "BoJ balance sheet"},
        # "MOVE": {"cadence": "daily", "units": "index", "scale": 1.0, "source": "ICE BofA", "notes": "rates vol index"},
        # "DEFI_LLAMA_STABLES": {"cadence": "daily", "units": "USD", "scale": 1.0, "source": "DefiLlama", "notes": "stablecoin supply"},
    }

    session = SessionLocal()
    try:
        n = upsert_series_registry(session, SEED)
        print(f"seeded {n} series into series_registry")
    finally:
        session.close()


if __name__ == "__main__":
    main()


