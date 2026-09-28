from app.services.invoice_generation import ticket_period_key


def test_ticket_period_key_matches_ledger_grouping_rule():
    class Row:
        source_file = "source.xlsx"
        detail_name = "detail.xlsx"
        period_text = "period"
        check_date_text = "date"

    assert ticket_period_key(Row()) == "source.xlsx"

