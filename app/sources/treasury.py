from __future__ import annotations

from typing import Dict, Any, List, Optional
import httpx


DTS_TGA_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
TREASURY_AUCTIONS_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
DTS_REDEMPTIONS_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/public_debt_transactions"
DTS_INTEREST_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/deposits_withdrawals_operating_cash"


async def fetch_tga_latest(limit: int = 1000, pages: int = 50) -> Dict[str, Any]:
    combined: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, pages + 1):
            params = {
                "sort": "-record_date",
                "page[number]": page,
                "page[size]": limit,
                "format": "json",
                # Request documented fields; we'll filter in code to capture naming variants
                "fields": "record_date,account_type,close_today_bal,open_today_bal",
            }
            r = await client.get(DTS_TGA_URL, params=params)
            r.raise_for_status()
            js = r.json()
            data = js.get("data", [])
            if not data:
                break
            combined.extend(data)
            if len(data) < limit:
                break
    return {"data": combined}


async def fetch_dts_cash_timeseries(url: str, limit: int = 1000, pages: int = 50, fields: Optional[str] = None, extra_params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Generic DTS fetcher for cash line items (e.g., redemptions, interest outlays).

    Keeps params minimal for compatibility across DTS endpoints.
    """
    combined: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, pages + 1):
            params: Dict[str, Any] = {
                "sort": "-record_date",
                "page[number]": page,
                "page[size]": limit,
                "format": "json",
            }
            if fields:
                params["fields"] = fields
            if extra_params:
                params.update(extra_params)
            r = await client.get(url, params=params)
            r.raise_for_status()
            js = r.json()
            data = js.get("data", [])
            if not data:
                break
            combined.extend(data)
            if len(data) < limit:
                break
    return {"data": combined}


async def fetch_redemptions(limit: int = 1000, pages: int = 50) -> Dict[str, Any]:
    # Public Debt Transactions (DTS): daily issues/redemptions by type; sum all redemptions per day
    return await fetch_dts_cash_timeseries(
        DTS_REDEMPTIONS_URL,
        limit=limit,
        pages=pages,
        fields="record_date,transaction_type,transaction_today_amt,security_market,security_type,security_type_desc",
    )


async def fetch_interest_outlays(limit: int = 1000, pages: int = 50) -> Dict[str, Any]:
    # Deposits and Withdrawals of Operating Cash (Table II): daily cash flows
    # We'll request minimal fields and filter in code for the Interest withdrawals line
    return await fetch_dts_cash_timeseries(
        DTS_INTEREST_URL,
        limit=limit,
        pages=pages,
        fields="record_date,transaction_type,transaction_catg,transaction_catg_desc,transaction_today_amt",
    )


def _parse_dts_numeric(val: Any) -> Optional[float]:
    if val in (None, "", "null"):
        return None
    try:
        return float(str(val).replace(",", ""))
    except Exception:
        return None


def parse_redemptions_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    from datetime import datetime, UTC
    totals_by_date: Dict[Any, float] = {}
    for r in payload.get("data", []):
        if (r.get("transaction_type") or "").lower() != "redemptions":
            continue
        num = _parse_dts_numeric(r.get("transaction_today_amt"))
        if num is None:
            continue
        odate = datetime.strptime(r["record_date"], "%Y-%m-%d").date()
        totals_by_date[odate] = totals_by_date.get(odate, 0.0) + num
    rows: List[Dict[str, Any]] = []
    now = datetime.now(UTC)
    for d, v in sorted(totals_by_date.items()):
        rows.append(
            {
                "observation_date": d,
                "vintage_date": None,
                "publication_date": None,
                "fetched_at": now,
                "value_numeric": v,
            }
        )
    return rows


def parse_interest_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    from datetime import datetime, UTC
    out_by_date: Dict[Any, float] = {}
    for r in payload.get("data", []):
        if (r.get("transaction_type") or "").lower() != "withdrawals":
            continue
        # Prefer description; fallback to category text
        cat_desc = (r.get("transaction_catg_desc") or "").strip()
        cat_raw = (r.get("transaction_catg") or "").strip()
        text = cat_desc or cat_raw
        lower_text = text.lower()
        # Broad match: handle "Interest on Treasury Securities"/"Interest on Treasury Debt Securities"
        is_interest = lower_text.startswith("interest on treasury")
        is_gross = "(Gross)" in cat_desc
        if not is_interest:
            continue
        num = _parse_dts_numeric(r.get("transaction_today_amt"))
        if num is None:
            continue
        odate = datetime.strptime(r["record_date"], "%Y-%m-%d").date()
        # If multiple lines present (e.g., gross and net), keep gross; else keep first seen
        if odate not in out_by_date or is_gross:
            out_by_date[odate] = num
    rows: List[Dict[str, Any]] = []
    now = datetime.now(UTC)
    for d, v in sorted(out_by_date.items()):
        rows.append(
            {
                "observation_date": d,
                "vintage_date": None,
                "publication_date": None,
                "fetched_at": now,
                "value_numeric": v,
            }
        )
    return rows


async def fetch_auction_schedules(limit: int = 1000, pages: int = 50, start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
    """Fetch Treasury auction schedules/results (basic fields for MVP).

    Dataset fields vary; we request a broad set and filter in code later.
    """
    combined: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, pages + 1):
            params = {
                "sort": "-auction_date",
                "page[number]": page,
                "page[size]": limit,
                "format": "json",
                # Fields available in auctions_query (no settlement_date/awarded_amount in this dataset)
                # We'll use issue_date as settlement proxy and offering_amt as size.
                "fields": "security_type,security_term,auction_date,issue_date,offering_amt,total_accepted,maturity_date",
            }
            if start_date:
                params["filter"] = f"auction_date:gte:{start_date}"
            if end_date:
                # FiscalData supports multiple filters with commas; keep simple for MVP
                params["filter"] = (params.get("filter", "") + ("," if params.get("filter") else "")) + f"auction_date:lte:{end_date}"
            r = await client.get(TREASURY_AUCTIONS_URL, params=params)
            r.raise_for_status()
            js = r.json()
            data = js.get("data", [])
            if not data:
                break
            combined.extend(data)
            if len(data) < limit:
                break
    return {"data": combined}


def parse_auction_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize Treasury auctions rows for downstream supply calculators.

    Output fields (per row):
    - auction_date (date)
    - issue_date (date|None)  # used as settlement proxy
    - security_type (str)
    - security_term (str|None)
    - offering_amount (float USD)
    - accepted_amount (float USD|None)
    - is_bill (bool)
    - is_coupon (bool)
    """
    data = payload.get("data", [])
    out: List[Dict[str, Any]] = []
    from datetime import datetime

    def to_date(s: Any) -> Any:
        if not s or s == "null":
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    def to_float(s: Any) -> float | None:
        if s is None or s == "null" or s == "":
            return None
        try:
            return float(str(s).replace(",", ""))
        except Exception:
            return None

    for row in data:
        stype = (row.get("security_type") or "").strip()
        term = (row.get("security_term") or row.get("security_term_week_year") or "").strip()
        offering = to_float(row.get("offering_amt"))
        accepted = to_float(row.get("total_accepted"))
        if offering is None and accepted is None:
            # Skip rows without amounts
            continue
        a_date = to_date(row.get("auction_date"))
        stype_norm = stype.lower()
        # Bills: match explicitly or by substring (covers CMB variants)
        is_bill = "bill" in stype_norm
        # Coupons: Notes/Bonds/TIPS/FRN treated as coupon-bearing
        is_coupon = any(x in stype_norm for x in ("note", "bond", "tips", "frn"))
        out.append(
            {
                "auction_date": a_date,
                "issue_date": to_date(row.get("issue_date")),
                "security_type": stype,
                "security_term": term,
                "offering_amount": offering,
                "accepted_amount": accepted,
                "is_bill": is_bill,
                "is_coupon": is_coupon,
            }
        )
    return out

