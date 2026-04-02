# Stripe Reconciliation Agent

A deterministic CLI tool that automatically reconciles Stripe payouts with bank statements, detects common reconciliation failures, and generates human-readable reports.

## What It Does

- **Payout Decomposition** — Breaks down Stripe payouts into gross charges, fees, refunds, and disputes
- **Transaction-Level Fee Breakdown** — Shows exact fee per transaction with card type details
- **Reconciliation Matching** — Matches Stripe payouts to bank statement entries with confidence scoring
- **Exception Detection** — Identifies duplicates, orphaned refunds, disputes, and unmatched entries
- **Summary Reports** — Generates clear, actionable reports in terminal-friendly format

## Why This Project Matters

Stripe reconciliation is one of the most tedious and error-prone tasks in startup finance. By the time a payout hits your bank account, it has been transformed twice (fees deducted, transactions batched) — making it nearly impossible to trace back to original transactions.

This tool solves that problem deterministically, without AI, giving founders and bookkeepers their time back.

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Language | Python 3.14.2 | Industry standard for fintech data pipelines |
| Package Manager | uv | Fast, modern, Python-native |
| API Framework | FastAPI | Auto-generated docs, async support |
| Data Models | Pydantic v2 | Type safety, validation, serialization |
| Stripe SDK | stripe | Official Python library |
| CLI UI | Rich | Beautiful terminal output |
| Testing | pytest | Industry standard |

## Quick Start

```bash
# Install dependencies
uv sync

# Run reconciliation
uv run stripe-recon reconcile --csv path/to/bank_statement.csv

# Check Stripe connection
uv run stripe-recon check
```

## Requirements

- Python 3.14.2+
- Stripe test/production API key
- Bank statement CSV file

## Environment Variables

Create a `.env` file:

```bash
STRIPE_API_KEY=sk_test_xxxxxxxxxxxxxxxxxxxx
```

## Usage

### Reconcile a bank statement

```bash
uv run stripe-recon reconcile --csv bank.csv --month 2026-03
```

### Generate a report for a specific payout

```bash
uv run stripe-recon report po_xxxxxxxxxxxxx
```

## Architecture

```
src/stripe_recon/
├── models.py          # Pydantic data models
├── config.py          # Configuration & thresholds
├── stripe_client.py   # Stripe API integration
├── bank_parser.py     # CSV parsing
├── reconciler.py      # Core matching logic
├── exceptions.py      # Failure mode detection
├── reporter.py        # Report generation
└── main.py            # CLI entry point
```

## Roadmap

| Version | Features |
|---------|----------|
| V1 | CLI tool, deterministic reconciliation, exception detection |
| V2 | Fuzzy matching, plain-English explanations (LLM), QuickBooks/Xero |
| V3 | Scheduled runs, webhooks, multi-client support |

## License

MIT

## Target Companies

This project signals deep fintech domain understanding to companies like:
Ramp, Brex, Mercury, Pilot, Stripe, Plaid, Rippling, Monzo, Revolut, Wise