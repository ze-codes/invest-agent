from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, UTC
from typing import List, Dict, Any

from app.settings import settings
from app.sources.fred import fetch_series
from app.sources.treasury import (
    fetch_tga_latest,
    fetch_auction_schedules,
    parse_auction_rows,
    fetch_redemptions,
    fetch_interest_outlays,
    parse_redemptions_rows,
    parse_interest_rows,
)
from app.sources.ofr import fetch_liquidity_stress_csv, parse_liquidity_stress_csv
from app.ingest import upsert_series_vintages
from app.db import SessionLocal
from app.supply import upsert_weekly_net_settlements
from app.floor import upsert_bill_rrp_spread


def _parse_fred_observations(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    # Note: FRED's top-level realtime_start/end describe the requested vintage window,
    # not the per-observation publication date. For MVP, omit publication_date here.
    pub_dt = None
    for obs in payload.get("observations", []):
        value_str = obs.get("value")
        if value_str in (None, "."):
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        out.append(
            {
                "observation_date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                "vintage_date": None,
                "publication_date": pub_dt,
                "fetched_at": datetime.now(UTC),
                # Store raw numeric; apply scaling via the 'scale' column in DB metadata
                "value_numeric": value,
            }
        )
    return out


def _parse_tga_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data", [])
    out: List[Dict[str, Any]] = []
    for row in data:
        # Filter to TGA account type if account_type provided (accept variants)
        acct = (row.get("account_type") or "").lower()
        if not ("treasury general" in acct and "account" in acct):
            continue
        # Per dataset notes, close_today_bal can be null; use open_today_bal as fallback
        val = row.get("close_today_bal")
        if val in (None, "null", ""):
            val = row.get("open_today_bal")
        if val in (None, "null", ""):
            continue
        try:
            num = float(val)
        except ValueError:
            continue
        out.append(
            {
                "observation_date": datetime.strptime(row["record_date"], "%Y-%m-%d").date(),
                "vintage_date": None,
                "publication_date": None,
                "fetched_at": datetime.now(UTC),
                "value_numeric": num,
            }
        )
    return out


async def fetch_core_series() -> None:
    t0 = time.time()
    pages_env = os.getenv("FETCH_PAGES")
    limit_env = os.getenv("FETCH_LIMIT")
    pages = int(pages_env) if pages_env and pages_env.isdigit() else 50
    limit = int(limit_env) if limit_env and limit_env.isdigit() else 1000

    async def fetch_and_ingest(series_id: str, units: str = "USD", scale: float = 1.0, observation_start: str | None = None):
        payload = await fetch_series(series_id, observation_start=observation_start)
        rows = _parse_fred_observations(payload)
        with SessionLocal() as s:
            upsert_series_vintages(s, series_id, rows, units=units, scale=scale, source="FRED", source_url="https://fred.stlouisfed.org")

    # FRED/ALFRED core
    print(f"[fetch-core] FRED core series…", flush=True)
    await asyncio.gather(
        fetch_and_ingest("WALCL", units="USD", scale=1e6, observation_start="2010-01-01"),
        fetch_and_ingest("RESPPLLOPNWW", units="USD", scale=1e6, observation_start="2010-01-01"),
        fetch_and_ingest("RRPONTSYD", units="USD", scale=1e6, observation_start="2014-01-01"),
        fetch_and_ingest("SOFR", units="percent", scale=1.0, observation_start="2018-01-01"),
        fetch_and_ingest("IORB", units="percent", scale=1.0, observation_start="2008-01-01"),
        fetch_and_ingest("DTB3", units="percent", scale=1.0, observation_start="2000-01-01"),
        fetch_and_ingest("DTB4WK", units="percent", scale=1.0, observation_start="2001-01-01"),
        # QT/QE components (FRED weekly, units typically millions)
        fetch_and_ingest("WSHOSHO", units="USD", scale=1e6, observation_start="2010-01-01"),
        fetch_and_ingest("WSHOMCB", units="USD", scale=1e6, observation_start="2010-01-01"),
    )
    print(f"[fetch-core] FRED done in {time.time()-t0:0.1f}s", flush=True)

    # RRP admin rate (FRED award rate) → store under canonical id RRP_RATE
    try:
        t = time.time()
        payload = await fetch_series("RRPONTSYAWARD", observation_start="2014-01-01")
        rows = _parse_fred_observations(payload)
        if rows:
            with SessionLocal() as s:
                upsert_series_vintages(s, "RRP_RATE", rows, units="percent", scale=1.0, source="FRED", source_url="https://fred.stlouisfed.org")
        print(f"[fetch-core] RRP_RATE done in {time.time()-t:0.1f}s", flush=True)
    except Exception as e:
        print(f"RRP admin rate fetch failed: {e}")

    # TGA via DTS
    try:
        t = time.time()
        print(f"[fetch-core] DTS TGA (pages={pages}, limit={limit})…", flush=True)
        payload = await fetch_tga_latest(limit=limit, pages=pages)
        rows = _parse_tga_rows(payload)
        if rows:
            with SessionLocal() as s:
                # DTS values are rounded to millions; store scale=1e6
                upsert_series_vintages(s, "TGA", rows, units="USD", scale=1e6, source="DTS", source_url="https://api.fiscaldata.treasury.gov")
        print(f"[fetch-core] DTS TGA done ({len(rows)} rows) in {time.time()-t:0.1f}s", flush=True)
    except Exception as e:
        print(f"TGA fetch failed: {e}")

    # DTS cash inflows: Redemptions and Interest (daily)
    try:
        t = time.time()
        print(f"[fetch-core] DTS redemptions (pages={pages}, limit={limit})…", flush=True)
        red_payload = await fetch_redemptions(limit=limit, pages=pages)
        red_rows = parse_redemptions_rows(red_payload)
        if red_rows:
            with SessionLocal() as s:
                upsert_series_vintages(
                    s,
                    "UST_REDEMPTIONS",
                    red_rows,
                    units="USD",
                    scale=1e6,
                    source="DTS",
                    source_url="https://api.fiscaldata.treasury.gov",
                )
        print(f"[fetch-core] DTS redemptions done ({len(red_rows)} rows) in {time.time()-t:0.1f}s", flush=True)
    except Exception as e:
        print(f"UST_REDEMPTIONS fetch failed: {e}")

    try:
        t = time.time()
        print(f"[fetch-core] DTS interest outlays (pages={pages}, limit={limit})…", flush=True)
        int_payload = await fetch_interest_outlays(limit=limit, pages=pages)
        int_rows = parse_interest_rows(int_payload)
        if int_rows:
            with SessionLocal() as s:
                upsert_series_vintages(
                    s,
                    "UST_INTEREST",
                    int_rows,
                    units="USD",
                    scale=1e6,
                    source="DTS",
                    source_url="https://api.fiscaldata.treasury.gov",
                )
        print(f"[fetch-core] DTS interest outlays done ({len(int_rows)} rows) in {time.time()-t:0.1f}s", flush=True)
    except Exception as e:
        print(f"UST_INTEREST fetch failed: {e}")

    # OFR Liquidity Stress Index (optional; CSV/JSON public feed)
    if settings.ofr_liquidity_stress_url:
        try:
            t = time.time()
            print("[fetch-core] OFR liquidity stress…", flush=True)
            csv_text = await fetch_liquidity_stress_csv(settings.ofr_liquidity_stress_url)
            rows = parse_liquidity_stress_csv(csv_text)
            if rows:
                with SessionLocal() as s:
                    upsert_series_vintages(
                        s,
                        "OFR_LIQ_IDX",
                        rows,
                        units="index",
                        scale=1.0,
                        source="OFR",
                        source_url=settings.ofr_liquidity_stress_url,
                    )
            print(f"[fetch-core] OFR liquidity stress done ({len(rows)} rows) in {time.time()-t:0.1f}s", flush=True)
        except Exception as e:
            print(f"OFR liquidity stress fetch failed: {e}")

    # Treasury Auctions (aggregate basic series for downstream calculators)
    try:
        from datetime import date, timedelta

        start = (date.today() - timedelta(days=365)).isoformat()
        t = time.time()
        print(f"[fetch-core] Treasury auctions (pages={min(pages,20)}, limit={limit})…", flush=True)
        payload = await fetch_auction_schedules(limit=limit, pages=min(pages, 20), start_date=start)
        rows = parse_auction_rows(payload)
        if rows:
            # Aggregate totals
            offering_by_auction: Dict[Any, float] = {}
            bill_offering_by_auction: Dict[Any, float] = {}
            accepted_by_issue: Dict[Any, float] = {}
            for r in rows:
                a_dt = r.get("auction_date")
                i_dt = r.get("issue_date")
                if r.get("offering_amount") is not None and a_dt is not None:
                    amt = float(r["offering_amount"])
                    offering_by_auction[a_dt] = offering_by_auction.get(a_dt, 0.0) + amt
                    if r.get("is_bill"):
                        bill_offering_by_auction[a_dt] = bill_offering_by_auction.get(a_dt, 0.0) + amt
                accepted_amt = r.get("accepted_amount")
                # Use accepted if available; otherwise fallback to offering
                value_for_issue = accepted_amt if accepted_amt is not None else r.get("offering_amount")
                if value_for_issue is not None and i_dt is not None:
                    accepted_by_issue[i_dt] = accepted_by_issue.get(i_dt, 0.0) + float(value_for_issue)

            def rows_from_map(m: Dict[Any, float]) -> List[Dict[str, Any]]:
                now = datetime.now(UTC)
                return [
                    {
                        "observation_date": dt,
                        "vintage_date": None,
                        "publication_date": None,
                        "fetched_at": now,
                        "value_numeric": total,
                    }
                    for dt, total in sorted(m.items())
                ]

            offering_rows = rows_from_map(offering_by_auction)
            bill_offering_rows = rows_from_map(bill_offering_by_auction)
            settlement_rows = rows_from_map(accepted_by_issue)

            with SessionLocal() as s:
                if offering_rows:
                    upsert_series_vintages(
                        s,
                        "UST_AUCTION_OFFERINGS",
                        offering_rows,
                        units="USD",
                        scale=1.0,
                        source="DTS",
                        source_url="https://api.fiscaldata.treasury.gov",
                    )
                if bill_offering_rows:
                    upsert_series_vintages(
                        s,
                        "UST_BILL_OFFERINGS",
                        bill_offering_rows,
                        units="USD",
                        scale=1.0,
                        source="DTS",
                        source_url="https://api.fiscaldata.treasury.gov",
                    )
                if settlement_rows:
                    upsert_series_vintages(
                        s,
                        "UST_AUCTION_ISSUES",
                        settlement_rows,
                        units="USD",
                        scale=1.0,
                        source="DTS",
                        source_url="https://api.fiscaldata.treasury.gov",
                    )
            print(
                f"[fetch-core] Treasury auctions done (offerings={len(offering_rows)}, settlements={len(settlement_rows)}) in {time.time()-t:0.1f}s",
                flush=True,
            )
    except Exception as e:
        print(f"Treasury auctions fetch failed: {e}")

    # Compute and persist derived weekly net settlements
    try:
        t = time.time()
        print("[fetch-core] Derived: weekly net settlements…", flush=True)
        with SessionLocal() as s:
            upsert_weekly_net_settlements(s, series_id="UST_NET_SETTLE_W", weeks_back=26)
        print(f"[fetch-core] Derived: weekly net settlements done in {time.time()-t:0.1f}s", flush=True)
    except Exception as e:
        print(f"Weekly net settlements upsert failed: {e}")

    # Compute and persist derived bill_rrp spread (bps)
    try:
        t = time.time()
        print("[fetch-core] Derived: bill_rrp spread…", flush=True)
        with SessionLocal() as s:
            upsert_bill_rrp_spread(s, series_id="BILL_RRP_BPS", days_back=180)
        print(f"[fetch-core] Derived: bill_rrp spread done in {time.time()-t:0.1f}s", flush=True)
    except Exception as e:
        print(f"bill_rrp derived spread upsert failed: {e}")

    print(f"[fetch-core] All done in {time.time()-t0:0.1f}s", flush=True)


def main() -> None:
    asyncio.run(fetch_core_series())


if __name__ == "__main__":
    main()


