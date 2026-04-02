import pytest
from datetime import datetime
from decimal import Decimal

from stripe_recon.models import (
    BalanceTransaction,
    TransactionType,
    ReportingCategory,
    ExceptionType,
)
from stripe_recon.exceptions import ExceptionDetector


class TestExceptionDetectorDuplicates:
    def test_detect_no_duplicates(self):
        transactions = [
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

        exceptions = ExceptionDetector.detect_duplicates(transactions)
        assert len(exceptions) == 0

    def test_detect_duplicate_charges_same_amount_same_customer(self):
        transactions = [
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
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709103600,
                source="ch_001",
                payout="po_123",
            ),
        ]

        exceptions = ExceptionDetector.detect_duplicates(transactions)
        assert len(exceptions) == 1
        assert exceptions[0].type == ExceptionType.DUPLICATE_CHARGE

    def test_no_duplicate_when_different_amount(self):
        transactions = [
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
                amount=20000,
                fee=620,
                net=19380,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709103600,
                source="ch_002",
                payout="po_123",
            ),
        ]

        exceptions = ExceptionDetector.detect_duplicates(transactions)
        assert len(exceptions) == 0


class TestExceptionDetectorOrphanedRefunds:
    def test_no_orphaned_refund(self):
        all_transactions = [
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

        exceptions = ExceptionDetector.detect_orphaned_refunds(
            all_transactions, all_transactions
        )
        assert len(exceptions) == 0

    def test_detect_orphaned_refund(self):
        all_transactions = [
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
                source="ch_002",
                payout="po_123",
            ),
        ]

        exceptions = ExceptionDetector.detect_orphaned_refunds(
            all_transactions, all_transactions
        )
        assert len(exceptions) == 1
        assert exceptions[0].type == ExceptionType.REFUND_ORPHAN


class TestExceptionDetectorDisputes:
    def test_detect_dispute_lost(self):
        transactions = [
            BalanceTransaction(
                id="txn_dispute",
                amount=-20000,
                fee=1500,
                net=-21500,
                currency="usd",
                type=TransactionType.DISPUTE,
                reporting_category=ReportingCategory.DISPUTE,
                created=1709200000,
                source="ch_001",
                payout="po_123",
            ),
        ]

        exceptions = ExceptionDetector.detect_disputes(transactions)
        assert len(exceptions) == 1
        assert exceptions[0].type == ExceptionType.DISPUTE_LOST

    def test_detect_dispute_won(self):
        transactions = [
            BalanceTransaction(
                id="txn_dispute_rev",
                amount=20000,
                fee=-1500,
                net=18500,
                currency="usd",
                type=TransactionType.DISPUTE_REVERSAL,
                reporting_category=ReportingCategory.DISPUTE_REVERSAL,
                created=1709250000,
                source="ch_001",
                payout="po_123",
            ),
        ]

        exceptions = ExceptionDetector.detect_disputes(transactions)
        assert len(exceptions) == 1
        assert exceptions[0].type == ExceptionType.DISPUTE_WON

    def test_no_disputes(self):
        transactions = [
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

        exceptions = ExceptionDetector.detect_disputes(transactions)
        assert len(exceptions) == 0


class TestExceptionDetectorAllExceptions:
    def test_detect_all_exception_types(self):
        from stripe_recon.models import (
            Payout,
            PayoutStatus,
            ReconciliationResult,
            ReconciliationStatus,
            MatchConfidence,
            BankEntry,
        )

        transactions = [
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
                amount=10000,
                fee=320,
                net=9680,
                currency="usd",
                type=TransactionType.CHARGE,
                reporting_category=ReportingCategory.CHARGE,
                created=1709103600,
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
        ]

        payouts = [
            Payout(
                id="po_123",
                amount=9680,
                currency="usd",
                status=PayoutStatus.PAID,
                arrival_date=1709304000,
                created=1709200000,
                transactions=transactions,
            ),
            Payout(
                id="po_456",
                amount=5000,
                currency="usd",
                status=PayoutStatus.PAID,
                arrival_date=1709400000,
                created=1709300000,
                transactions=[],
            ),
        ]

        reconciliation_results = [
            ReconciliationResult(
                payout_id="po_123",
                payout_amount=9680,
                confidence=MatchConfidence.EXACT,
                status=ReconciliationStatus.RECONCILED,
            ),
            ReconciliationResult(
                payout_id="po_456",
                payout_amount=5000,
                confidence=MatchConfidence.NO_MATCH,
                status=ReconciliationStatus.UNMATCHED,
            ),
        ]

        bank_entries = [
            BankEntry(
                date=datetime(2026, 3, 1),
                description="Stripe payout",
                amount=Decimal("96.80"),
            ),
        ]

        exceptions = ExceptionDetector.detect_all_exceptions(
            payouts, reconciliation_results, bank_entries
        )

        exception_types = {e.type for e in exceptions}

        assert ExceptionType.DUPLICATE_CHARGE in exception_types
        assert ExceptionType.DISPUTE_LOST in exception_types
        assert ExceptionType.UNMATCHED_PAYOUT in exception_types
