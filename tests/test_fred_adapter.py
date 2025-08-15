import json
import pytest
import respx
from httpx import Response

from app.sources.fred import FRED_BASE, fetch_series


@pytest.mark.asyncio
@respx.mock
async def test_fetch_series_basic(monkeypatch):
    route = respx.get(FRED_BASE).mock(
        return_value=Response(200, json={
            "realtime_end": "2025-08-11",
            "observations": [
                {"date": "2025-08-10", "value": "123"},
                {"date": "2025-08-09", "value": "."},
            ],
        })
    )

    # No API key required in test; function should still call endpoint
    data = await fetch_series("WALCL", observation_start="2020-01-01")
    assert route.called
    assert "observations" in data


