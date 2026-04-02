# Stripe Reconciliation Agent

[![Tests](https://img.shields.io/badge/tests-35%20passing-green)](https://github.com/vikramadityaprsingh/stripe_reconciliation_engine)
[![Python](https://img.shields.io/badge/python-3.14.2-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

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

### The Core Equation

```
Gross charges - Stripe fees - Refunds - Dispute losses + Dispute reversals = Payout amount
```

This equation must balance to **exactly zero** — not approximately.

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Language | Python 3.14.2 | Industry standard for fintech data pipelines |
| Package Manager | uv | Fast, modern, Python-native |
| CLI Framework | Click | Simple, composable command-line interface |
| Data Models | Pydantic v2 | Type safety, validation, serialization |
| Stripe SDK | stripe | Official Python library |
| CLI UI | Rich | Beautiful terminal output |
| Testing | pytest | Industry standard |

## Quick Start

```bash
# Install dependencies
uv sync

# Check Stripe connection
uv run stripe-recon check --api-key sk_test_xxx

# Run reconciliation
uv run stripe-recon reconcile --csv path/to/bank_statement.csv --month 2026-03
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

### Check Stripe connection

```bash
uv run stripe-recon check
# or with API key
uv run stripe-recon check --api-key sk_test_xxx
```

### Reconcile a bank statement

```bash
uv run stripe-recon reconcile --csv bank.csv --month 2026-03

# Output formats: terminal (default), json, csv
uv run stripe-recon reconcile --csv bank.csv --output json
```

### Generate a report for a specific payout

```bash
uv run stripe-recon report po_xxxxxxxxxxxxx --api-key sk_test_xxx
```

## Project Structure

```
stripe_reconciliation_engine/
├── src/stripe_recon/
│   ├── models.py            # Pydantic data models
│   ├── config.py            # Configuration & thresholds
│   ├── stripe_client.py     # Stripe API integration
│   ├── bank_parser.py       # CSV parsing
│   ├── reconciler.py        # Core matching logic
│   ├── exceptions.py        # Failure mode detection
│   ├── reporter.py          # Report generation
│   └── main.py              # CLI entry point
├── tests/
│   ├── test_reconciler.py   # Core matching tests
│   ├── test_exceptions.py    # Exception detection tests
│   ├── test_bank_parser.py  # CSV parsing tests
│   └── fixtures/            # Test data
├── pyproject.toml
├── README.md
└── .env.example
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=stripe_recon --cov-report=term-missing

# Run single test file
uv run pytest tests/test_reconciler.py

# Run single test
uv run pytest tests/test_reconciler.py::TestPayoutModel::test_gross_charges_calculation
```

## Exception Detection

The tool automatically detects these failure modes:

| Exception | Description |
|-----------|-------------|
| `DUPLICATE_CHARGE` | Same amount charged to same customer within 24 hours |
| `REFUND_ORPHAN` | Refund with no matching charge in the period |
| `DISPUTE_OPEN` | Open dispute requiring response |
| `DISPUTE_LOST` | Lost dispute with fee |
| `DISPUTE_WON` | Won dispute with funds returned |
| `UNMATCHED_PAYOUT` | Stripe payout with no bank entry |
| `UNMATCHED_BANK_ENTRY` | Bank entry with no Stripe payout |
| `ROUNDING_DIFFERENCE` | Difference < $0.10 (likely rounding) |

## Roadmap

| Version | Status | Features |
|---------|--------|----------|
| V1 | ✅ Complete | CLI tool, deterministic reconciliation, exception detection, 35 passing tests |
| V2 | Planned | Fuzzy matching, plain-English explanations (LLM), QuickBooks/Xero |
| V3 | Planned | Scheduled runs, webhooks, multi-client support |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass: `uv run pytest`
5. Submit a pull request

## License

MIT

## Target Companies

This project signals deep fintech domain understanding to companies like:
Ramp, Brex, Mercury, Pilot, Stripe, Plaid, Rippling, Monzo, Revolut, Wise