import pytest

from app.sources.treasury import parse_interest_rows


def test_parse_interest_rows_prefers_withdrawals_interest_and_handles_desc_fallback():
    payload = {
        "data": [
            {
                "record_date": "2025-08-13",
                "account_type": "Treasury General Account (TGA)",
                "transaction_type": "Withdrawals",
                "transaction_catg": "Independent Agencies - misc",
                "transaction_catg_desc": None,
                "transaction_today_amt": "62",
            },
            {
                "record_date": "2025-08-13",
                "account_type": "Treasury General Account (TGA)",
                "transaction_type": "Withdrawals",
                "transaction_catg": "Interest on Treasury Securities",
                "transaction_catg_desc": None,
                "transaction_today_amt": "4",
            },
        ]
    }

    rows = parse_interest_rows(payload)
    # Expect a single row for the interest line
    assert len(rows) == 1
    r = rows[0]
    assert str(r["observation_date"]) == "2025-08-13"
    # Amount should be parsed as float 4
    assert float(r["value_numeric"]) == 4.0


