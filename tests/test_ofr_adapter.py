import pytest
import respx
from httpx import Response

from app.sources.ofr import fetch_liquidity_stress_csv, parse_liquidity_stress_csv


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ofr_csv_basic():
    url = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
    csv_body = "Date,OFR FSI\n2025-08-10,1.23\n"
    route = respx.get(url).mock(return_value=Response(200, text=csv_body))

    text = await fetch_liquidity_stress_csv(url)
    assert route.called
    assert "OFR FSI" in text


def test_parse_liquidity_stress_csv_extracts_ofr_fsi_only():
    csv_body = (
        "Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,United States,Other advanced economies,Emerging markets\n"
        "2000-01-03,2.14,0.54,-0.051,0.67,0.472,0.509,1.769,0.521,-0.15\n"
        "2000-01-04,2.421,0.604,0.079,0.627,0.55,0.561,2.084,0.474,-0.137\n"
    )
    rows = parse_liquidity_stress_csv(csv_body)
    assert len(rows) == 2
    assert rows[0]["observation_date"].isoformat() == "2000-01-03"
    assert rows[0]["value_numeric"] == pytest.approx(2.14)


def test_parse_liquidity_stress_csv_skips_missing_values():
    csv_body = (
        "Date,OFR FSI,Credit\n"
        "2025-08-10,1.00,0.5\n"
        "2025-08-11,,0.6\n"  # missing composite
    )
    rows = parse_liquidity_stress_csv(csv_body)
    assert len(rows) == 1
    assert rows[0]["observation_date"].isoformat() == "2025-08-10"
    assert rows[0]["value_numeric"] == pytest.approx(1.00)


