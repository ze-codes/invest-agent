import pytest
import respx
from httpx import Response

from app.sources.treasury import DTS_TGA_URL, fetch_tga_latest


@pytest.mark.asyncio
@respx.mock
async def test_fetch_tga_latest_paginates_and_stops():
    # First page returns full page; second returns less -> stop
    page1 = {
        "data": [
            {"record_date": "2025-08-11", "account_type": "Treasury General Account (TGA)", "close_today_bal": "850", "open_today_bal": "840"},
        ]
    }
    page2 = {"data": []}

    respx.get(DTS_TGA_URL).mock(side_effect=[Response(200, json=page1), Response(200, json=page2)])

    data = await fetch_tga_latest(limit=1, pages=2)
    assert len(data["data"]) == 1


