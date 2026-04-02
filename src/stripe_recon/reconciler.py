from datetime import datetime, timedelta
from typing import Optional

from stripe_recon.config import config
from stripe_recon.models import (
    BankEntry,
    MatchConfidence,
    Payout,
    ReconciliationResult,
    ReconciliationStatus,
)


class Reconciler:
    @staticmethod
    def verify_payout_math(payout: Payout) -> tuple[bool, str]:
        calculated_net = sum(t.net for t in payout.transactions)
        difference = abs(calculated_net - payout.amount)

        if difference == 0:
            return True, "Balanced"

        if difference <= config.ROUNDING_THRESHOLD_CENTS:
            return True, f"Rounding difference: {difference} cents"

        return (
            False,
            f"Math error: calculated {calculated_net}, expected {payout.amount}, diff {difference}",
        )

    @staticmethod
    def get_payout_components(payout: Payout) -> dict:
        charges = [t for t in payout.transactions if t.type.value == "charge"]
        refunds = [t for t in payout.transactions if t.type.value == "refund"]
        disputes = [t for t in payout.transactions if t.type.value == "dispute"]
        dispute_reversals = [
            t for t in payout.transactions if t.type.value == "dispute_reversal"
        ]

        gross_charges = sum(t.amount for t in charges)
        total_fees = sum(t.fee for t in charges)
        total_refunds = sum(abs(t.amount) for t in refunds)
        dispute_losses = sum(abs(t.net) for t in disputes)
        dispute_won = sum(t.net for t in dispute_reversals)

        return {
            "gross_charges": gross_charges,
            "total_fees": total_fees,
            "total_refunds": total_refunds,
            "dispute_losses": dispute_losses,
            "dispute_won": dispute_won,
            "transaction_count": len(charges),
            "refund_count": len(refunds),
            "dispute_count": len(disputes),
        }

    @staticmethod
    def match_to_bank(
        payout: Payout,
        bank_entries: list[BankEntry],
    ) -> ReconciliationResult:
        payout_amount_cents = payout.amount
        payout_arrival = datetime.fromtimestamp(payout.arrival_date)

        best_match: Optional[ReconciliationResult] = None

        for bank_entry in bank_entries:
            bank_amount_cents = bank_entry.amount_cents

            if bank_amount_cents != payout_amount_cents:
                continue

            date_diff = abs((bank_entry.date - payout_arrival).days)

            if date_diff == 0:
                result = ReconciliationResult(
                    payout_id=payout.id,
                    payout_amount=payout_amount_cents,
                    bank_entry=bank_entry,
                    confidence=MatchConfidence.EXACT,
                    status=ReconciliationStatus.RECONCILED,
                )
                return result

            elif date_diff <= config.DATE_TOLERANCE_DAYS:
                result = ReconciliationResult(
                    payout_id=payout.id,
                    payout_amount=payout_amount_cents,
                    bank_entry=bank_entry,
                    confidence=MatchConfidence.TIMING_MATCH,
                    status=ReconciliationStatus.TIMING_DIFFERENCE,
                    notes=f"Date differs by {date_diff} day(s) - likely weekend/holiday delay",
                )
                if not best_match or best_match.confidence != MatchConfidence.EXACT:
                    best_match = result

        if best_match:
            return best_match

        return ReconciliationResult(
            payout_id=payout.id,
            payout_amount=payout_amount_cents,
            confidence=MatchConfidence.NO_MATCH,
            status=ReconciliationStatus.UNMATCHED,
            notes="No matching bank entry found",
        )

    @staticmethod
    def check_rounding_difference(
        payout: Payout,
        bank_entry: BankEntry,
    ) -> bool:
        payout_cents = payout.amount
        bank_cents = bank_entry.amount_cents
        difference = abs(payout_cents - bank_cents)
        return difference <= config.ROUNDING_THRESHOLD_CENTS and difference > 0

    @staticmethod
    def reconcile_payouts(
        payouts: list[Payout],
        bank_entries: list[BankEntry],
    ) -> list[ReconciliationResult]:
        results = []
        matched_bank_ids = set()

        for payout in payouts:
            result = Reconciler.match_to_bank(payout, bank_entries)
            results.append(result)

            if result.bank_entry:
                matched_bank_ids.add(id(result.bank_entry))

        unmatched_bank_entries = [
            entry for entry in bank_entries if id(entry) not in matched_bank_ids
        ]

        return results

    @staticmethod
    def get_unmatched_bank_entries(
        payouts: list[Payout],
        bank_entries: list[BankEntry],
    ) -> list[BankEntry]:
        matched_payout_ids = {
            r.payout_id for r in Reconciler.reconcile_payouts(payouts, bank_entries)
        }

        return [
            entry
            for entry in bank_entries
            if entry.description.lower().strip()
            not in ["stripe payout", "stripe transfer", "stripe"]
            or (
                entry.description.lower().strip()
                in ["stripe payout", "stripe transfer", "stripe"]
                and not any(p.id == entry.description for p in payouts)
            )
        ]
