import pytest
import respx
from httpx import Response

from app.sources.treasury import TREASURY_AUCTIONS_URL, fetch_auction_schedules, parse_auction_rows


@pytest.mark.asyncio
@respx.mock
async def test_fetch_auctions_basic_filters_and_fields():
    # Mock one page response with minimal fields
    payload = {
        "data": [
            {
                "auction_date": "2025-08-10",
                "issue_date": "2025-08-13",
                "security_type": "Bill",
                "security_term": "13-Week",
                "offering_amt": "50,000",
                "maturity_date": "2025-11-14",
            },
        ]
    }

    route = respx.get(TREASURY_AUCTIONS_URL).mock(return_value=Response(200, json=payload))

    data = await fetch_auction_schedules(limit=10, pages=1, start_date="2025-08-01", end_date="2025-08-31")

    assert route.called
    # Ensure our function returns combined data list
    assert "data" in data and len(data["data"]) == 1


def test_parse_auction_rows_normalizes_fields():
    payload = {
        "data": [
            {
                "auction_date": "2025-08-10",
                "issue_date": "2025-08-13",
                "security_type": "Bill",
                "security_term": "13-Week",
                "offering_amt": "50,000",
                "maturity_date": "2025-11-14",
            },
            {
                "auction_date": "2025-08-12",
                "security_type": "Bond",
                "offering_amt": "",
            },
        ]
    }

    rows = parse_auction_rows(payload)
    # second row skipped due to missing amounts
    assert len(rows) == 1
    r = rows[0]
    assert r["auction_date"].isoformat() == "2025-08-10"
    assert r["is_bill"] is True
    assert r["is_coupon"] is False
    assert r["offering_amount"] == 50000.0
    assert r["issue_date"].isoformat() == "2025-08-13"


def test_parse_auction_rows_classifies_types_and_bills_coupons():
    payload = {
        "data": [
            {  # Regular Bill
                "auction_date": "2025-08-10",
                "issue_date": "2025-08-13",
                "security_type": "Bill",
                "offering_amt": "10,000",
            },
            {  # Cash Management Bill variant
                "auction_date": "2025-08-10",
                "issue_date": "2025-08-13",
                "security_type": "Cash Management Bill",
                "offering_amt": "5,000",
            },
            {  # Note (coupon)
                "auction_date": "2025-08-10",
                "issue_date": "2025-08-15",
                "security_type": "Note",
                "offering_amt": "20,000",
            },
            {  # Bond (coupon)
                "auction_date": "2025-08-11",
                "issue_date": "2025-08-31",
                "security_type": "Bond",
                "offering_amt": "30,000",
            },
            {  # TIPS (coupon)
                "auction_date": "2025-08-11",
                "issue_date": "2025-09-30",
                "security_type": "TIPS",
                "offering_amt": "8,000",
            },
            {  # FRN (coupon)
                "auction_date": "2025-08-12",
                "issue_date": "2025-08-15",
                "security_type": "FRN",
                "offering_amt": "7,000",
            },
        ]
    }

    rows = parse_auction_rows(payload)
    # Verify bill classification
    bills = [r for r in rows if r["is_bill"]]
    coupons = [r for r in rows if r["is_coupon"]]

    assert len(bills) == 2  # Bill + CMB
    assert all(r["security_type"].lower().find("bill") >= 0 for r in bills)

    assert len(coupons) == 4  # Note, Bond, TIPS, FRN
    for sec in ("note", "bond", "tips", "frn"):
        assert any(sec in r["security_type"].lower() for r in coupons)
