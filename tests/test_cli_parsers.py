from datetime import date

from app.cli_fetch import _parse_fred_observations, _parse_tga_rows as parse_tga_rows


def test_parse_fred_observations_skips_missing_and_parses_values():
    payload = {
        "realtime_end": "2025-08-11",
        "observations": [
            {"date": "2025-08-10", "value": "123.4"},
            {"date": "2025-08-09", "value": "."},
            {"date": "2025-08-08", "value": "not-a-number"},
        ],
    }
    rows = _parse_fred_observations(payload)
    assert len(rows) == 1
    r = rows[0]
    assert r["observation_date"].isoformat() == "2025-08-10"
    assert r["value_numeric"] == 123.4


def test_parse_tga_rows_filters_account_type_and_uses_fallback():
    payload = {
        "data": [
            {"record_date": "2025-08-10", "account_type": "Something else", "close_today_bal": "100", "open_today_bal": "90"},
            {"record_date": "2025-08-11", "account_type": "Treasury General Account (TGA)", "close_today_bal": None, "open_today_bal": "95"},
            {"record_date": "2025-08-12", "account_type": "Treasury General Account", "close_today_bal": "", "open_today_bal": "null"},
        ]
    }
    rows = parse_tga_rows(payload)
    assert len(rows) == 1
    r = rows[0]
    assert r["observation_date"].isoformat() == "2025-08-11"
    assert r["value_numeric"] == 95.0


