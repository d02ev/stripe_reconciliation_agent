import pytest
from datetime import datetime
from decimal import Decimal

from stripe_recon.models import (
    BalanceTransaction,
    Payout,
    PayoutStatus,
    BankEntry,
    TransactionType,
    ReportingCategory,
    ReconciliationStatus,
    MatchConfidence,
)
from stripe_recon.reconciler import Reconciler
from stripe_recon.config import config


class TestPayoutModel:
    def test_gross_charges_calculation(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_2",
                amount=25000,
                fee=905,
                net=24095,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709120000,
                source="ch_002",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=33775,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        assert payout.gross_charges == 35000

    def test_total_fees_calculation(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_2",
                amount=25000,
                fee=905,
                net=24095,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709120000,
                source="ch_002",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=33775,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        assert payout.total_fees == 1225

    def test_calculated_net_matches_payout(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_2",
                amount=25000,
                fee=905,
                net=24095,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709120000,
                source="ch_002",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=33775,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        assert payout.calculated_net == 33775
        assert payout.is_balanced is True

    def test_payout_with_refunds(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_refund",
                amount=-5000,
                fee=0,
                net=-5000,
                currency="usd",
                type=TransactionType.REFUND,
                reporting_category=ReportingCategory.REFUND,
                created=1709150000,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=4680,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        assert payout.gross_charges == 10000
        assert payout.total_refunds == 5000
        assert payout.is_balanced is True


class TestReconcilerVerifyPayoutMath:
    def test_balanced_payout(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=9680,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        is_balanced, note = Reconciler.verify_payout_math(payout)
        assert is_balanced is True
        assert note == "Balanced"

    def test_unbalanced_payout(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=9000,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        is_balanced, note = Reconciler.verify_payout_math(payout)
        assert is_balanced is False
        assert "Math error" in note

    def test_rounding_difference_within_threshold(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=9685,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )
        is_balanced, note = Reconciler.verify_payout_math(payout)
        assert is_balanced is True
        assert "Rounding difference" in note


class TestReconcilerMatchToBank:
    def test_exact_match(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1772323200,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=9680,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1772323200,
            created=1772323200,
            transactions=txns,
        )

        bank_entries = [
            BankEntry(
                date=datetime(2026, 3, 1),
                description="Stripe payout",
                amount=Decimal("96.80"),
                balance=Decimal("1000.00"),
            ),
        ]

        result = Reconciler.match_to_bank(payout, bank_entries)
        assert result.status == ReconciliationStatus.RECONCILED
        assert result.confidence == MatchConfidence.EXACT

    def test_timing_match_within_tolerance(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1772323200,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=9680,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1772323200,
            created=1772323200,
            transactions=txns,
        )

        bank_entries = [
            BankEntry(
                date=datetime(2026, 3, 3),
                description="Stripe payout",
                amount=Decimal("96.80"),
                balance=Decimal("1000.00"),
            ),
        ]

        result = Reconciler.match_to_bank(payout, bank_entries)
        assert result.status == ReconciliationStatus.TIMING_DIFFERENCE
        assert result.confidence == MatchConfidence.TIMING_MATCH

    def test_no_match(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1772323200,
                source="ch_001",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=9680,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1772323200,
            created=1772323200,
            transactions=txns,
        )

        bank_entries = [
            BankEntry(
                date=datetime(2026, 3, 10),
                description="Stripe payout",
                amount=Decimal("50.00"),
                balance=Decimal("1000.00"),
            ),
        ]

        result = Reconciler.match_to_bank(payout, bank_entries)
        assert result.status == ReconciliationStatus.UNMATCHED
        assert result.confidence == MatchConfidence.NO_MATCH


class TestGetPayoutComponents:
    def test_get_components_with_all_types(self):
        txns = [
            BalanceTransaction(
                id="txn_1",
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709100000,
                source="ch_001",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_refund",
                amount=-5000,
                fee=0,
                net=-5000,
                currency="usd",
                type=TransactionType.REFUND,
                reporting_category=ReportingCategory.REFUND,
                created=1709150000,
                source="ch_001",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_dispute",
                amount=-20000,
                fee=1500,
                net=-21500,
                currency="usd",
                type=TransactionType.DISPUTE,
                reporting_category=ReportingCategory.DISPUTE,
                created=1709200000,
                source="ch_002",
                payout="po_123",
            ),
            BalanceTransaction(
                id="txn_dispute_rev",
                amount=20000,
                fee=-1500,
                net=18500,
                currency="usd",
                type=TransactionType.DISPUTE_REVERSAL,
                reporting_category=ReportingCategory.DISPUTE_REVERSAL,
                created=1709250000,
                source="ch_002",
                payout="po_123",
            ),
        ]
        payout = Payout(
            id="po_123",
            amount=1680,
            currency="usd",
            status=PayoutStatus.PAID,
            arrival_date=1709304000,
            created=1709200000,
            transactions=txns,
        )

        components = Reconciler.get_payout_components(payout)

        assert components["gross_charges"] == 10000
        assert components["total_fees"] == 320
        assert components["total_refunds"] == 5000
        assert components["dispute_losses"] == 21500
        assert components["dispute_won"] == 18500
        assert components["transaction_count"] == 1
        assert components["refund_count"] == 1
        assert components["dispute_count"] == 1
