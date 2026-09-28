from app.services.invoice_generation import hotel_period_key


def test_hotel_period_key_matches_ledger_grouping_rule():
    class Row:
        source_file = ""
        detail_name = ""
        period_text = "period"
        check_date_text = "date"

    assert hotel_period_key(Row()) == "period"

