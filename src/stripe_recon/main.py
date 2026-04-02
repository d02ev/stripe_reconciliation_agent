import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from stripe_recon.bank_parser import BankParser
from stripe_recon.config import config, settings
from stripe_recon.exceptions import ExceptionDetector
from stripe_recon.models import ReconciliationStatus
from stripe_recon.reconciler import Reconciler
from stripe_recon.reporter import Reporter
from stripe_recon.stripe_client import StripeClient


load_dotenv()


@click.group()
def cli():
    """Stripe Reconciliation Agent - Automatically reconcile Stripe payouts with bank statements."""
    pass


@cli.command()
@click.option("--csv", required=True, help="Path to bank statement CSV file")
@click.option(
    "--month",
    default=None,
    help="Month to reconcile (format: YYYY-MM, defaults to current month)",
)
@click.option(
    "--api-key",
    default=None,
    help="Stripe API key (defaults to STRIPE_API_KEY env variable)",
)
@click.option(
    "--output",
    type=click.Choice(["terminal", "json", "csv"]),
    default="terminal",
    help="Output format",
)
def reconcile(csv: str, month: Optional[str], api_key: Optional[str], output: str):
    """Reconcile Stripe payouts with a bank statement."""
    try:
        if not Path(csv).exists():
            click.echo(f"Error: Bank statement file not found: {csv}", err=True)
            sys.exit(1)

        api_key = api_key or settings.STRIPE_API_KEY
        if not api_key:
            click.echo(
                "Error: Stripe API key required. Set STRIPE_API_KEY env or use --api-key",
                err=True,
            )
            sys.exit(1)

        click.echo("Initializing Stripe client...")
        stripe_client = StripeClient(api_key)

        click.echo("Fetching payouts from Stripe...")

        now = datetime.now()
        if month:
            year, month_num = map(int, month.split("-"))
            start_date = datetime(year, month_num, 1)
            if month_num == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month_num + 1, 1)
        else:
            start_date = datetime(now.year, now.month, 1)
            end_date = now

        payouts = stripe_client.get_payouts(
            created_after=start_date,
            created_before=end_date,
            status="paid",
        )

        if not payouts:
            click.echo("No payouts found for the specified period.")
            sys.exit(0)

        click.echo(f"Found {len(payouts)} payouts. Verifying internal math...")

        for payout in payouts:
            is_balanced, note = Reconciler.verify_payout_math(payout)
            if not is_balanced:
                click.echo(
                    f"Warning: Payout {payout.id} is not balanced: {note}", err=True
                )

        click.echo("Parsing bank statement...")
        bank_entries = BankParser.parse_csv(csv)
        stripe_entries = BankParser.extract_stripe_entries(bank_entries)

        click.echo(f"Found {len(stripe_entries)} Stripe entries in bank statement.")

        click.echo("Running reconciliation...")
        reconciliation_results = Reconciler.reconcile_payouts(payouts, stripe_entries)

        click.echo("Detecting exceptions...")
        exceptions = ExceptionDetector.detect_all_exceptions(
            payouts, reconciliation_results, stripe_entries
        )

        click.echo("Generating report...")
        reporter = Reporter()

        if output == "terminal":
            reporter.format_terminal(payouts, reconciliation_results, exceptions)
        elif output == "json":
            import json

            result = reporter.format_json(payouts, reconciliation_results, exceptions)
            click.echo(json.dumps(result, indent=2))
        elif output == "csv":
            result = reporter.format_csv(payouts, reconciliation_results)
            click.echo(result)

        reconciled = sum(
            1
            for r in reconciliation_results
            if r.status
            in [ReconciliationStatus.RECONCILED, ReconciliationStatus.TIMING_DIFFERENCE]
        )
        total = len(reconciliation_results)

        click.echo(f"\nReconciliation complete: {reconciled}/{total} payouts matched")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--api-key",
    default=None,
    help="Stripe API key (defaults to STRIPE_API_KEY env variable)",
)
def check(api_key: Optional[str]):
    """Check Stripe API connection."""
    try:
        api_key = api_key or settings.STRIPE_API_KEY
        if not api_key:
            click.echo(
                "Error: Stripe API key required. Set STRIPE_API_KEY env or use --api-key",
                err=True,
            )
            sys.exit(1)

        stripe_client = StripeClient(api_key)

        if stripe_client.verify_connection():
            click.echo("✓ Stripe connection successful!")
        else:
            click.echo("✗ Stripe connection failed", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("payout_id")
@click.option(
    "--api-key",
    default=None,
    help="Stripe API key (defaults to STRIPE_API_KEY env variable)",
)
def report(payout_id: str, api_key: Optional[str]):
    """Generate detailed report for a specific payout."""
    try:
        api_key = api_key or settings.STRIPE_API_KEY
        if not api_key:
            click.echo(
                "Error: Stripe API key required. Set STRIPE_API_KEY env or use --api-key",
                err=True,
            )
            sys.exit(1)

        stripe_client = StripeClient(api_key)

        click.echo(f"Fetching payout {payout_id}...")
        payout = stripe_client.get_payout(payout_id)

        is_balanced, note = Reconciler.verify_payout_math(payout)
        components = Reconciler.get_payout_components(payout)

        reporter = Reporter()

        click.echo("\n" + "=" * 60)
        click.echo(f"PAYOUT REPORT: {payout.id}")
        click.echo("=" * 60)

        click.echo(f"\nAmount:      ${payout.amount / 100:,.2f}")
        click.echo(
            f"Arrival:     {datetime.fromtimestamp(payout.arrival_date).strftime('%Y-%m-%d')}"
        )
        click.echo(f"Status:      {payout.status.value}")
        click.echo(f"Balanced:    {'✓ Yes' if is_balanced else '✗ No'} - {note}")

        click.echo(f"\nComponents:")
        click.echo(f"  Gross Charges:      ${components['gross_charges'] / 100:,.2f}")
        click.echo(f"  Stripe Fees:        -${components['total_fees'] / 100:,.2f}")
        click.echo(f"  Refunds:            -${components['total_refunds'] / 100:,.2f}")
        click.echo(f"  Dispute Losses:     -${components['dispute_losses'] / 100:,.2f}")
        click.echo(f"  Dispute Reversals: +${components['dispute_won'] / 100:,.2f}")
        click.echo(f"  ─────────────────────")
        click.echo(f"  Net Payout:         ${payout.amount / 100:,.2f}")

        click.echo(f"\nTransaction Counts:")
        click.echo(f"  Charges:    {components['transaction_count']}")
        click.echo(f"  Refunds:    {components['refund_count']}")
        click.echo(f"  Disputes:   {components['dispute_count']}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
