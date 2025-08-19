from app.sources.treasury import parse_redemptions_rows


def test_parse_redemptions_rows_sums_all_types_per_day():
    payload = {
        "data": [
            {
                "record_date": "2025-08-13",
                "transaction_type": "Issues",
                "transaction_today_amt": "100",
            },
            {
                "record_date": "2025-08-13",
                "transaction_type": "Redemptions",
                "transaction_today_amt": "30",
            },
            {
                "record_date": "2025-08-13",
                "transaction_type": "Redemptions",
                "transaction_today_amt": "20",
            },
            {
                "record_date": "2025-08-14",
                "transaction_type": "Redemptions",
                "transaction_today_amt": "5",
            },
        ]
    }

    rows = parse_redemptions_rows(payload)
    assert len(rows) == 2
    by_date = {str(r["observation_date"]): float(r["value_numeric"]) for r in rows}
    assert by_date["2025-08-13"] == 50.0
    assert by_date["2025-08-14"] == 5.0


def test_parse_redemptions_rows_sums_across_security_types_same_day_notes_bonds_sample():
    payload = {
        "data": [
            {
                "record_date": "2025-08-14",
                "transaction_type": "Redemptions",
                "security_market": "Marketable",
                "security_type": "Notes",
                "security_type_desc": None,
                "transaction_today_amt": "857",
            },
            {
                "record_date": "2025-08-14",
                "transaction_type": "Redemptions",
                "security_market": "Marketable",
                "security_type": "Bonds",
                "security_type_desc": None,
                "transaction_today_amt": "0",
            },
        ]
    }

    rows = parse_redemptions_rows(payload)
    assert len(rows) == 1
    r = rows[0]
    assert str(r["observation_date"]) == "2025-08-14"
    assert float(r["value_numeric"]) == 857.0


