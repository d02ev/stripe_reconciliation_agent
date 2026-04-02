# AGENTS.md — Stripe Reconciliation Engine

> Guide for agentic coding agents operating in this repository.

---

## 1. Project Overview

**Stripe Reconciliation Engine** is a V1 deterministic CLI tool that reconciles Stripe payouts with bank statements. V1 is purely mathematical — no AI/LLM — focused on exact equation balancing.

- **Language:** Python 3.14.2
- **Package Manager:** uv
- **Framework:** Click CLI, FastAPI (future), Pydantic v2

---

## 2. Build & Test Commands

### Install Dependencies
```bash
uv sync
```

### Run All Tests
```bash
uv run pytest
# or with coverage
uv run pytest --cov=stripe_recon --cov-report=term-missing
```

### Run Single Test
```bash
# By file
uv run pytest tests/test_reconciler.py

# By class
uv run pytest tests/test_reconciler.py::TestPayoutModel

# By function
uv run pytest tests/test_reconciler.py::TestPayoutModel::test_gross_charges_calculation

# By keyword
uv run pytest -k "test_balanced"
```

### Run CLI Commands
```bash
uv run stripe-recon --help
uv run stripe-recon check
uv run stripe-recon reconcile --csv path/to/bank.csv --month 2026-03
uv run stripe-recon report po_xxx
```

### Run with Custom API Key
```bash
uv run stripe-recon check --api-key sk_test_xxx
```

---

## 3. Code Style Guidelines

### 3.1 Imports

**Order (top of file, grouping):**
1. Standard library (`datetime`, `typing`, `collections`)
2. Third-party (`stripe`, `pydantic`, `click`, `rich`)
3. Local (`stripe_recon.models`, `stripe_recon.config`)

```python
# Correct
import sys
from datetime import datetime, timedelta
from typing import Optional, Callable

import stripe
from stripe._error import StripeError
from pydantic import BaseModel, Field

from stripe_recon.models import Payout, BalanceTransaction
from stripe_recon.config import config, settings

# Never use relative imports like "from .models import"
```

### 3.2 Formatting

- **Line length:** 100 characters max
- **Indentation:** 4 spaces (no tabs)
- **Blank lines:** 2 between top-level definitions, 1 between methods
- **Trailing commas:** Always in multi-line imports and function calls

### 3.3 Type Hints

- Use Python 3.14+ typing (no `typing.Optional`, use `X | None`)
- Use Pydantic for data models instead of manual typing
- Return types required for all functions

```python
# Correct
def verify_payout_math(payout: Payout) -> tuple[bool, str]:
    ...

def get_payouts(
    created_after: datetime | None = None,
    status: str | None = None,
) -> list[Payout]:
    ...
```

### 3.4 Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Modules | snake_case | `bank_parser.py` |
| Classes | PascalCase | `class StripeClient` |
| Functions | snake_case | `def verify_payout_math()` |
| Variables | snake_case | `payout_amount_cents` |
| Constants | UPPER_SNAKE | `DATE_TOLERANCE_DAYS` |
| Enum values | UPPER_SNAKE | `RECONCILED = "reconciled"` |

### 3.5 Pydantic Models

- Use `Field` with descriptions for all model attributes
- Always set `default_factory` for mutable defaults (list, dict)
- Use `Enum` for fixed-choice fields
- Computed properties for derived values

```python
class Payout(BaseModel):
    id: str
    amount: int = Field(description="Payout amount in cents")
    transactions: list[BalanceTransaction] = Field(default_factory=list)
    
    @property
    def gross_charges(self) -> int:
        return sum(t.amount for t in self.transactions)
```

### 3.6 Error Handling

- Use specific exceptions from `stripe._error`
- Never catch bare `Exception`
- Always provide context in error messages

```python
# Correct
try:
    stripe_client = StripeClient(api_key)
except ValueError as e:
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)

# Never
try:
    ...
except Exception:
    pass
```

### 3.7 Docstrings

- Use Google-style docstrings
- Include: Description, Args, Returns, Raises

```python
def match_to_bank(payout: Payout, bank_entries: list[BankEntry]) -> ReconciliationResult:
    """Match a Stripe payout to a bank statement entry.
    
    Args:
        payout: The Stripe payout to match.
        bank_entries: List of parsed bank statement entries.
    
    Returns:
        ReconciliationResult with confidence score and status.
    
    Raises:
        ValueError: If payout amount is invalid.
    """
    ...
```

### 3.8 Enum Usage

```python
class TransactionType(str, Enum):
    CHARGE = "charge"
    REFUND = "refund"
    DISPUTE = "dispute"
    DISPUTE_REVERSAL = "dispute_reversal"
    PAYOUT = "payout"
```

---

## 4. Project Structure

```
stripe_reconciliation_engine/
├── src/stripe_recon/
│   ├── __init__.py          # Package init (empty)
│   ├── models.py            # Pydantic data models
│   ├── config.py            # Configuration & settings
│   ├── stripe_client.py     # Stripe API integration
│   ├── bank_parser.py       # CSV parsing
│   ├── reconciler.py        # Core matching logic
│   ├── exceptions.py        # Exception detection
│   ├── reporter.py          # Report generation
│   └── main.py              # CLI entry point
├── tests/
│   ├── __init__.py
│   ├── fixtures/            # Test data
│   ├── test_reconciler.py
│   ├── test_exceptions.py
│   └── test_bank_parser.py
├── pyproject.toml
├── README.md
└── .env.example
```

---

## 5. Key Principles

1. **V1 is deterministic** — No AI/LLM calls. All logic is mathematically verifiable.
2. **Balance to zero** — Core equation: `gross - fees - refunds - disputes = payout`
3. **Exact amounts in cents** — Always use integers to avoid floating-point errors
4. **Confidence scoring** — Exact = 1.0, Timing (±2 days) = 0.9, No match = 0.0
5. **Tests first** — Write tests before fixing bugs

---

## 6. Common Tasks

### Add a new exception type
1. Add to `ExceptionType` enum in `models.py`
2. Add detection logic in `exceptions.py`
3. Add test in `test_exceptions.py`

### Add a new CLI command
1. Add `@cli.command()` in `main.py`
2. Add tests for the command

### Add a new bank statement format
1. Update `DATE_FORMATS` in `bank_parser.py`
2. Update column detection in `_identify_columns()`
3. Add test case in `test_bank_parser.py`

---

## 7. Configuration

Settings are loaded from environment variables via `pydantic-settings`:

- `STRIPE_API_KEY` — Stripe API key (required)
- `.env` file for local development (see `.env.example`)

Reconciliation thresholds in `config.py`:
- `DATE_TOLERANCE_DAYS = 2`
- `ROUNDING_THRESHOLD_CENTS = 10`
- `DUPLICATE_TIME_WINDOW_HOURS = 24`

---

This file should be updated as the project evolves. Last updated: April 2026.