from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from stripe_recon.config import config
from stripe_recon.models import (
    BalanceTransaction,
    ExceptionType,
    Payout,
    ReconciliationException,
    TransactionType,
)


class ExceptionDetector:
    @staticmethod
    def detect_duplicates(
        transactions: list[BalanceTransaction],
    ) -> list[ReconciliationException]:
        exceptions = []

        charges = [t for t in transactions if t.type == TransactionType.CHARGE]

        amount_customer_map: dict[tuple, list[BalanceTransaction]] = defaultdict(list)

        for charge in charges:
            key = (charge.amount, charge.source)
            amount_customer_map[key].append(charge)

        for (amount, _), charge_group in amount_customer_map.items():
            if len(charge_group) > 1:
                charge_times = [datetime.fromtimestamp(c.created) for c in charge_group]
                time_span = max(charge_times) - min(charge_times)

                if time_span <= timedelta(hours=config.DUPLICATE_TIME_WINDOW_HOURS):
                    charge_ids = [c.id for c in charge_group]
                    exceptions.append(
                        ReconciliationException(
                            type=ExceptionType.DUPLICATE_CHARGE,
                            description=f"Multiple charges of {amount / 100:.2f} detected within {config.DUPLICATE_TIME_WINDOW_HOURS} hours",
                            related_ids=charge_ids,
                            suggested_action="Check if this was an intentional duplicate charge or a system error",
                        )
                    )

        return exceptions

    @staticmethod
    def detect_orphaned_refunds(
        transactions: list[BalanceTransaction],
        all_transactions: Optional[list[BalanceTransaction]] = None,
    ) -> list[ReconciliationException]:
        exceptions = []

        refunds = [t for t in transactions if t.type == TransactionType.REFUND]

        if not all_transactions:
            all_transactions = transactions

        charge_ids = {
            t.source for t in all_transactions if t.type == TransactionType.CHARGE
        }

        for refund in refunds:
            if refund.source and refund.source not in charge_ids:
                exceptions.append(
                    ReconciliationException(
                        type=ExceptionType.REFUND_ORPHAN,
                        description=f"Orphaned refund of {abs(refund.amount) / 100:.2f} — no matching charge found in period",
                        related_ids=[refund.id, refund.source or "unknown"],
                        suggested_action="This refund likely relates to a charge from a previous period. Verify in Stripe dashboard.",
                    )
                )

        return exceptions

    @staticmethod
    def detect_disputes(
        transactions: list[BalanceTransaction],
    ) -> list[ReconciliationException]:
        exceptions = []

        for tx in transactions:
            if tx.type == TransactionType.DISPUTE:
                dispute_amount = abs(tx.net) / 100
                fee_amount = tx.fee / 100

                exceptions.append(
                    ReconciliationException(
                        type=ExceptionType.DISPUTE_LOST,
                        description=f"Lost dispute — {dispute_amount:.2f} plus {fee_amount:.2f} fee",
                        related_ids=[tx.id, tx.source or "unknown"],
                        suggested_action="Dispute was lost. Ensure proper documentation for future disputes.",
                    )
                )

            elif tx.type == TransactionType.DISPUTE_REVERSAL:
                dispute_amount = tx.net / 100
                fee_amount = abs(tx.fee) / 100

                exceptions.append(
                    ReconciliationException(
                        type=ExceptionType.DISPUTE_WON,
                        description=f"Dispute won — {dispute_amount:.2f} returned minus {fee_amount:.2f} fee",
                        related_ids=[tx.id, tx.source or "unknown"],
                        suggested_action="Dispute was won and funds returned. Verify correct accounting entry.",
                    )
                )

        return exceptions

    @staticmethod
    def detect_unmatched_payouts(
        payouts: list[Payout],
        reconciliation_results: list,
    ) -> list[ReconciliationException]:
        exceptions = []

        for result in reconciliation_results:
            if result.status.value == "unmatched":
                amount_dollars = result.payout_amount / 100
                exceptions.append(
                    ReconciliationException(
                        type=ExceptionType.UNMATCHED_PAYOUT,
                        description=f"Payout {result.payout_id} of {amount_dollars:.2f} has no matching bank entry",
                        related_ids=[result.payout_id],
                        suggested_action="Check if bank statement covers the payout date, or if payout is still pending.",
                    )
                )

        return exceptions

    @staticmethod
    def detect_unmatched_bank_entries(
        bank_entries: list,
        reconciliation_results: list,
    ) -> list[ReconciliationException]:
        exceptions = []

        matched_entry_ids = {
            id(result.bank_entry)
            for result in reconciliation_results
            if result.bank_entry
        }

        unmatched_entries = [
            entry for entry in bank_entries if id(entry) not in matched_entry_ids
        ]

        for entry in unmatched_entries:
            if "stripe" in entry.description.lower():
                amount_dollars = entry.amount
                exceptions.append(
                    ReconciliationException(
                        type=ExceptionType.UNMATCHED_BANK_ENTRY,
                        description=f"Bank entry of {amount_dollars:.2f} labeled as Stripe has no matching payout",
                        related_ids=[entry.description],
                        suggested_action="Check if this is a manual Stripe transfer or if payout is missing from Stripe data.",
                    )
                )

        return exceptions

    @staticmethod
    def detect_rounding_differences(
        reconciliation_results: list,
    ) -> list[ReconciliationException]:
        exceptions = []

        for result in reconciliation_results:
            if result.status.value == "timing_difference" and result.bank_entry:
                payout_cents = result.payout_amount
                bank_cents = result.bank_entry.amount_cents
                diff = abs(payout_cents - bank_cents)

                if diff <= config.ROUNDING_THRESHOLD_CENTS and diff > 0:
                    exceptions.append(
                        ReconciliationException(
                            type=ExceptionType.ROUNDING_DIFFERENCE,
                            description=f"Rounding difference of {diff} cents between payout and bank entry",
                            related_ids=[result.payout_id],
                            suggested_action="This is likely a rounding error. No action required.",
                        )
                    )

        return exceptions

    @staticmethod
    def detect_all_exceptions(
        payouts: list[Payout],
        reconciliation_results: list,
        bank_entries: list,
        all_transactions: Optional[list[BalanceTransaction]] = None,
    ) -> list[ReconciliationException]:
        all_exceptions = []

        all_tx = all_transactions or []
        for payout in payouts:
            all_tx.extend(payout.transactions)

        all_exceptions.extend(ExceptionDetector.detect_duplicates(all_tx))
        all_exceptions.extend(ExceptionDetector.detect_orphaned_refunds(all_tx, all_tx))
        all_exceptions.extend(ExceptionDetector.detect_disputes(all_tx))
        all_exceptions.extend(
            ExceptionDetector.detect_unmatched_payouts(payouts, reconciliation_results)
        )
        all_exceptions.extend(
            ExceptionDetector.detect_unmatched_bank_entries(
                bank_entries, reconciliation_results
            )
        )
        all_exceptions.extend(
            ExceptionDetector.detect_rounding_differences(reconciliation_results)
        )

        return all_exceptions
