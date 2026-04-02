from datetime import datetime
from decimal import Decimal
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from stripe_recon.models import (
    BankEntry,
    Payout,
    ReconciliationException,
    ReconciliationReport,
    ReconciliationResult,
    ReconciliationStatus,
)


class Reporter:
    def __init__(self):
        self.console = Console()

    def generate_summary(
        self,
        reconciliation_results: list[ReconciliationResult],
        exceptions: list[ReconciliationException],
        payouts: list[Payout],
    ) -> dict:
        total_payouts = len(payouts)

        total_gross = sum(p.gross_charges for p in payouts)
        total_fees = sum(p.total_fees for p in payouts)
        total_refunds = sum(p.total_refunds for p in payouts)
        total_dispute_losses = sum(p.dispute_losses for p in payouts)
        total_dispute_reversals = sum(p.dispute_reversals for p in payouts)

        net_deposited = sum(p.amount for p in payouts)

        reconciled = [
            r
            for r in reconciliation_results
            if r.status == ReconciliationStatus.RECONCILED
        ]
        timing_match = [
            r
            for r in reconciliation_results
            if r.status == ReconciliationStatus.TIMING_DIFFERENCE
        ]
        unmatched = [
            r
            for r in reconciliation_results
            if r.status == ReconciliationStatus.UNMATCHED
        ]

        reconciled_payouts = len(reconciled) + len(timing_match)
        reconciled_amount = sum(r.payout_amount for r in reconciled) + sum(
            r.payout_amount for r in timing_match
        )
        unmatched_payouts = len(unmatched)
        unmatched_amount = sum(r.payout_amount for r in unmatched)

        effective_fee_rate = (
            Decimal(total_fees) / Decimal(total_gross)
            if total_gross > 0
            else Decimal("0")
        )

        return {
            "total_payouts": total_payouts,
            "total_gross_revenue": total_gross,
            "total_fees": total_fees,
            "total_refunds": total_refunds,
            "total_dispute_losses": total_dispute_losses,
            "total_dispute_reversals": total_dispute_reversals,
            "net_deposited": net_deposited,
            "reconciled_payouts": reconciled_payouts,
            "reconciled_amount": reconciled_amount,
            "unmatched_payouts": unmatched_payouts,
            "unmatched_amount": unmatched_amount,
            "effective_fee_rate": effective_fee_rate,
            "exception_count": len(exceptions),
        }

    def format_payout_decomposition(self, payout: Payout) -> Table:
        table = Table(title=f"Payout Decomposition: {payout.id}", show_lines=True)

        table.add_column("Component", style="cyan")
        table.add_column("Amount", justify="right", style="green")

        components = Reconciler.get_payout_components(payout)

        table.add_row("Gross Charges", f"${components['gross_charges'] / 100:,.2f}")
        table.add_row("  Transaction Count", str(components["transaction_count"]))
        table.add_row("Stripe Fees", f"-${components['total_fees'] / 100:,.2f}")

        if components["total_refunds"] > 0:
            table.add_row("Refunds", f"-${components['total_refunds'] / 100:,.2f}")
            table.add_row("  Refund Count", str(components["refund_count"]))

        if components["dispute_losses"] > 0:
            table.add_row(
                "Dispute Losses", f"-${components['dispute_losses'] / 100:,.2f}"
            )

        if components["dispute_won"] > 0:
            table.add_row(
                "Dispute Reversals", f"+${components['dispute_won'] / 100:,.2f}"
            )

        table.add_row("", "")
        table.add_row("Net Payout", f"${payout.amount / 100:,.2f}", style="bold green")

        balanced = payout.is_balanced
        balance_note = "✓ BALANCED" if balanced else "✗ UNBALANCED"
        table.add_row("", balance_note)

        return table

    def format_reconciliation_results(
        self,
        results: list[ReconciliationResult],
    ) -> Table:
        table = Table(title="Reconciliation Results", show_lines=True)

        table.add_column("Payout ID", style="cyan")
        table.add_column("Amount", justify="right", style="green")
        table.add_column("Bank Date", style="yellow")
        table.add_column("Confidence", justify="center")
        table.add_column("Status", style="magenta")

        for result in results:
            amount_str = f"${result.payout_amount / 100:,.2f}"
            bank_date = (
                result.bank_entry.date.strftime("%Y-%m-%d")
                if result.bank_entry
                else "—"
            )
            confidence_str = f"{result.confidence.value * 100:.0f}%"

            if result.status == ReconciliationStatus.RECONCILED:
                status_str = "✓ RECONCILED"
                status_style = "green"
            elif result.status == ReconciliationStatus.TIMING_DIFFERENCE:
                status_str = f"✓ TIMING ({result.notes})"
                status_style = "yellow"
            else:
                status_str = "✗ UNMATCHED"
                status_style = "red"

            table.add_row(
                result.payout_id[:20] + "..."
                if len(result.payout_id) > 20
                else result.payout_id,
                amount_str,
                bank_date,
                confidence_str,
                status_str,
            )

        return table

    def format_exception_report(
        self,
        exceptions: list[ReconciliationException],
    ) -> Table:
        if not exceptions:
            table = Table(title="Exceptions", show_lines=True)
            table.add_column("Status", justify="center")
            table.add_row("✓ No exceptions found")
            return table

        table = Table(title=f"Exceptions ({len(exceptions)} found)", show_lines=True)

        table.add_column("#", justify="right", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Action", style="yellow")

        for i, exc in enumerate(exceptions, 1):
            table.add_row(
                str(i),
                exc.type.value,
                exc.description[:50] + "..."
                if len(exc.description) > 50
                else exc.description,
                exc.suggested_action[:40] + "..."
                if len(exc.suggested_action) > 40
                else exc.suggested_action,
            )

        return table

    def format_summary_panel(self, summary: dict) -> Panel:
        content = []

        content.append(f"Total Payouts:        {summary['total_payouts']}")
        content.append(
            f"Total Gross Revenue:   ${summary['total_gross_revenue'] / 100:,.2f}"
        )
        content.append(f"Total Fees:           -${summary['total_fees'] / 100:,.2f}")
        content.append(f"Total Refunds:        -${summary['total_refunds'] / 100:,.2f}")
        content.append(
            f"Total Dispute Losses: -${summary['total_dispute_losses'] / 100:,.2f}"
        )
        content.append(f"Net Deposited:         ${summary['net_deposited'] / 100:,.2f}")
        content.append("")
        content.append(
            f"Reconciled:           {summary['reconciled_payouts']} payouts (${summary['reconciled_amount'] / 100:,.2f})"
        )
        content.append(
            f"Unmatched:            {summary['unmatched_payouts']} payouts (${summary['unmatched_amount'] / 100:,.2f})"
        )
        content.append("")
        content.append(
            f"Effective Fee Rate:   {summary['effective_fee_rate'] * 100:.2f}%"
        )
        content.append(f"Exceptions:            {summary['exception_count']}")

        return Panel(
            "\n".join(content),
            title="[bold]Reconciliation Summary[/bold]",
            border_style="blue",
        )

    def format_terminal(
        self,
        payouts: list[Payout],
        reconciliation_results: list[ReconciliationResult],
        exceptions: list[ReconciliationException],
    ):
        summary = self.generate_summary(reconciliation_results, exceptions, payouts)

        self.console.print("\n")
        self.console.print(
            Panel.fit(
                "[bold cyan]STRIPE RECONCILIATION REPORT[/bold cyan]",
                border_style="cyan",
            )
        )

        self.console.print(self.format_summary_panel(summary))

        self.console.print("\n")
        self.console.print(self.format_reconciliation_results(reconciliation_results))

        if exceptions:
            self.console.print("\n")
            self.console.print(self.format_exception_report(exceptions))

        for payout in payouts[:3]:
            self.console.print("\n")
            self.console.print(self.format_payout_decomposition(payout))

    def format_json(
        self,
        payouts: list[Payout],
        reconciliation_results: list[ReconciliationResult],
        exceptions: list[ReconciliationException],
    ) -> dict:
        summary = self.generate_summary(reconciliation_results, exceptions, payouts)

        return {
            "generated_at": datetime.now().isoformat(),
            "summary": summary,
            "reconciliation_results": [
                {
                    "payout_id": r.payout_id,
                    "payout_amount": r.payout_amount,
                    "bank_entry": {
                        "date": r.bank_entry.date.isoformat() if r.bank_entry else None,
                        "amount": float(r.bank_entry.amount) if r.bank_entry else None,
                    }
                    if r.bank_entry
                    else None,
                    "confidence": r.confidence.value,
                    "status": r.status.value,
                    "notes": r.notes,
                }
                for r in reconciliation_results
            ],
            "exceptions": [
                {
                    "type": e.type.value,
                    "description": e.description,
                    "related_ids": e.related_ids,
                    "suggested_action": e.suggested_action,
                }
                for e in exceptions
            ],
            "payouts": [
                {
                    "id": p.id,
                    "amount": p.amount,
                    "arrival_date": p.arrival_date,
                    "status": p.status.value,
                    "gross_charges": p.gross_charges,
                    "total_fees": p.total_fees,
                    "total_refunds": p.total_refunds,
                    "dispute_losses": p.dispute_losses,
                    "is_balanced": p.is_balanced,
                }
                for p in payouts
            ],
        }

    def format_csv(
        self,
        payouts: list[Payout],
        reconciliation_results: list[ReconciliationResult],
    ) -> str:
        lines = [
            "payout_id,amount,arrival_date,status,confidence,reconciliation_status"
        ]

        for result in reconciliation_results:
            lines.append(
                f"{result.payout_id},"
                f"{result.payout_amount},"
                f"{result.payout_id},"
                f"{result.confidence.value},"
                f"{result.status.value}"
            )

        return "\n".join(lines)


from stripe_recon.reconciler import Reconciler
