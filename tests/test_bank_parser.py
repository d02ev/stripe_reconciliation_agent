import pytest
from datetime import datetime
from decimal import Decimal

from stripe_recon.bank_parser import BankParser
from stripe_recon.models import BankEntry


class TestBankParserNormalizeDate:
    def test_normalize_date_iso_format(self):
        result = BankParser.normalize_date("2026-03-15")
        assert result == datetime(2026, 3, 15)

    def test_normalize_date_us_format(self):
        result = BankParser.normalize_date("03/15/2026")
        assert result == datetime(2026, 3, 15)

    def test_normalize_date_dmy_format(self):
        result = BankParser.normalize_date("15/03/2026")
        assert result == datetime(2026, 3, 15)

    def test_normalize_date_with_time(self):
        result = BankParser.normalize_date("2026-03-15")
        assert result is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 15


class TestBankParserIsStripeEntry:
    def test_is_stripe_entry_stripe_keyword(self):
        assert BankParser.is_stripe_entry("Stripe payout") is True
        assert BankParser.is_stripe_entry("STRIPE PAYOUT") is True
        assert BankParser.is_stripe_entry("stripe transfer") is True

    def test_is_stripe_entry_non_stripe(self):
        assert BankParser.is_stripe_entry("Rent payment") is False
        assert BankParser.is_stripe_entry("Office supplies") is False


class TestBankParserParseAmount:
    def test_parse_amount_positive(self):
        result = BankParser.parse_amount("1234.56")
        assert result == Decimal("1234.56")

    def test_parse_amount_with_dollar_sign(self):
        result = BankParser.parse_amount("$1234.56")
        assert result == Decimal("1234.56")

    def test_parse_amount_with_comma(self):
        result = BankParser.parse_amount("1,234.56")
        assert result == Decimal("1234.56")

    def test_parse_amount_negative(self):
        result = BankParser.parse_amount("-$1234.56")
        assert result == Decimal("-1234.56")

    def test_parse_amount_parentheses(self):
        result = BankParser.parse_amount("(1234.56)")
        assert result == Decimal("-1234.56")


class TestBankParserParseCSV:
    def test_parse_csv_basic(self, tmp_path):
        csv_content = """date,description,amount,balance
2026-03-01,Stripe payout,4847.23,12847.23
2026-03-08,Stripe payout,3102.17,15949.40
2026-03-15,Rent payment,-2500.00,13449.40"""

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        entries = BankParser.parse_csv(str(csv_file))

        assert len(entries) == 3
        assert entries[0].description == "Stripe payout"
        assert entries[0].amount == Decimal("4847.23")
        assert entries[1].amount == Decimal("3102.17")

    def test_parse_csv_different_column_names(self, tmp_path):
        csv_content = """transaction_date,memo,value,running_balance
2026-03-01,Stripe payout,4847.23,12847.23
2026-03-08,Stripe payout,3102.17,15949.40"""

        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        entries = BankParser.parse_csv(str(csv_file))

        assert len(entries) == 2


class TestBankParserExtractStripeEntries:
    def test_extract_stripe_entries(self):
        entries = [
            BankEntry(
                date=datetime(2026, 3, 1),
                description="Stripe payout",
                amount=Decimal("100.00"),
            ),
            BankEntry(
                date=datetime(2026, 3, 2),
                description="Rent payment",
                amount=Decimal("-500.00"),
            ),
            BankEntry(
                date=datetime(2026, 3, 3),
                description="Stripe transfer",
                amount=Decimal("200.00"),
            ),
        ]

        stripe_entries = BankParser.extract_stripe_entries(entries)

        assert len(stripe_entries) == 2
        assert stripe_entries[0].description == "Stripe payout"
        assert stripe_entries[1].description == "Stripe transfer"


class TestBankParserFilterByDateRange:
    def test_filter_by_date_range(self):
        entries = [
            BankEntry(
                date=datetime(2026, 3, 1),
                description="Entry 1",
                amount=Decimal("100.00"),
            ),
            BankEntry(
                date=datetime(2026, 3, 15),
                description="Entry 2",
                amount=Decimal("200.00"),
            ),
            BankEntry(
                date=datetime(2026, 3, 30),
                description="Entry 3",
                amount=Decimal("300.00"),
            ),
        ]

        filtered = BankParser.filter_by_date_range(
            entries, start_date=datetime(2026, 3, 10), end_date=datetime(2026, 3, 20)
        )

        assert len(filtered) == 1
        assert filtered[0].description == "Entry 2"
