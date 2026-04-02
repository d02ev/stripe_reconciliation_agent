# Technical Documentation — Stripe Reconciliation Engine

> Deep technical walkthrough of the project architecture, mathematics, and implementation details.

---

## 1. Overview

The Stripe Reconciliation Engine is a deterministic CLI tool that mathematically proves that Stripe payouts match bank statement entries. It does this without AI — pure equation balancing.

### What Problem It Solves

When a customer pays $100 via Stripe:
1. Stripe deducts its fee ($2.90 + $0.30 = $3.20)
2. The remaining $96.80 sits in Stripe balance
3. After 2 business days, Stripe batches all transactions into one payout
4. Bank shows: `$96.80 — Stripe`

The original $100 charge is completely invisible in the bank statement. This tool reverse-engineers that transformation.

---

## 2. The Mathematics

### 2.1 Core Reconciliation Equation

For every payout, this equation must balance to exactly zero:

```
Σ(net) - payout_amount = 0
```

Where for each balance transaction:
```
net = amount - fee
```

### 2.2 Transaction Types & Their Math

| Type | amount | fee | net |
|------|--------|-----|-----|
| Charge | +10000 (+$100.00) | +320 (+$3.20) | +9680 (+$96.80) |
| Refund | -5000 (-$50.00) | 0 | -5000 (-$50.00) |
| Dispute (lost) | -20000 (-$200.00) | +1500 (+$15.00) | -21500 (-$215.00) |
| Dispute (won) | +20000 (+$200.00) | -1500 (-$15.00) | +18500 (+$185.00) |

**Important:** Refunds do NOT return the original fee. The $3.20 fee from a $100 charge is kept by Stripe even if refunded.

### 2.3 Payout Verification

```python
def verify_payout_math(payout: Payout) -> tuple[bool, str]:
    calculated_net = sum(t.net for t in payout.transactions)
    difference = abs(calculated_net - payout.amount)
    
    if difference == 0:
        return True, "Balanced"
    
    if difference <= 10:  # cents threshold
        return True, f"Rounding: {difference} cents"
    
    return False, f"Math error: {difference} cents"
```

### 2.4 Component Breakdown

For each payout, we calculate:

```
Gross Charges    = Σ(amount) for all CHARGE transactions
Total Fees       = Σ(fee) for all CHARGE transactions  
Total Refunds    = Σ(|amount|) for all REFUND transactions
Dispute Losses   = Σ(|net|) for all DISPUTE transactions
Dispute Reversals= Σ(net) for all DISPUTE_REVERSAL transactions

Net Payout       = Gross Charges - Total Fees - Total Refunds - Dispute Losses + Dispute Reversals
```

---

## 3. Architecture

### 3.1 Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Stripe API  │────▶│ StripeClient│────▶│   Payout    │
│             │     │             │     │ (model)     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Bank CSV   │────▶│BankParser   │────▶│  BankEntry   │
│             │     │             │     │  (model)     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐            │
                    │Reconciler   │◀───────────┘
                    │             │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
    ┌────────────┐  ┌───────────┐  ┌────────────┐
    │ Exception  │  │Reconciliation│ │  Reporter  │
    │ Detector   │  │  Results   │  │             │
    └────────────┘  └────────────┘  └────────────┘
```

### 3.2 Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `models.py` | Pydantic models with computed properties |
| `config.py` | Thresholds, settings (env variables) |
| `stripe_client.py` | Stripe API calls, pagination, type mapping |
| `bank_parser.py` | CSV parsing, date normalization, column detection |
| `reconciler.py` | Math verification, bank matching, confidence scoring |
| `exceptions.py` | 8 exception type detectors |
| `reporter.py` | Terminal/JSON/CSV output |
| `main.py` | Click CLI commands |

---

## 4. Bank Matching Algorithm

### 4.1 Three-Tier Confidence Scoring

**Tier 1 — Exact Match** (confidence: 1.0)
- Amount matches exactly
- Date matches exactly

**Tier 2 — Timing Match** (confidence: 0.9)
- Amount matches exactly
- Date within ±2 business days (weekend/holiday delay)

**Tier 3 — No Match** (confidence: 0.0)
- Amount not found in bank statement

### 4.2 Matching Logic

```python
def match_to_bank(payout: Payout, bank_entries: list[BankEntry]) -> ReconciliationResult:
    payout_amount_cents = payout.amount
    payout_arrival = datetime.fromtimestamp(payout.arrival_date)
    
    for bank_entry in bank_entries:
        if bank_entry.amount_cents != payout_amount_cents:
            continue
        
        date_diff = abs((bank_entry.date - payout_arrival).days)
        
        if date_diff == 0:
            return ReconciliationResult(
                confidence=MatchConfidence.EXACT,
                status=ReconciliationStatus.RECONCILED
            )
        elif date_diff <= 2:
            return ReconciliationResult(
                confidence=MatchConfidence.TIMING_MATCH,
                status=ReconciliationStatus.TIMING_DIFFERENCE,
                notes=f"Date differs by {date_diff} day(s)"
            )
    
    return ReconciliationResult(
        confidence=MatchConfidence.NO_MATCH,
        status=ReconciliationStatus.UNMATCHED
    )
```

---

## 5. Exception Detection

### 5.1 The Eight Failure Modes

1. **DUPLICATE_CHARGE** — Same amount + same source ID within 24 hours
2. **REFUND_ORPHAN** — Refund with no matching charge in the dataset
3. **DISPUTE_OPEN** — Open dispute requiring response
4. **DISPUTE_LOST** — Lost dispute with $15 fee
5. **DISPUTE_WON** — Won dispute with funds returned (minus fee)
6. **UNMATCHED_PAYOUT** — Stripe payout not found in bank statement
7. **UNMATCHED_BANK_ENTRY** — Bank entry with no Stripe payout
8. **ROUNDING_DIFFERENCE** — Difference < $0.10 (likely floating-point rounding)

### 5.2 Detection Logic Examples

**Duplicate Detection:**
```python
def detect_duplicates(transactions: list[BalanceTransaction]) -> list[ReconciliationException]:
    charges = [t for t in transactions if t.type == TransactionType.CHARGE]
    amount_source_map = defaultdict(list)
    
    for charge in charges:
        amount_source_map[(charge.amount, charge.source)].append(charge)
    
    for (amount, source), group in amount_source_map.items():
        if len(group) > 1:
            time_span = max(c.created for c in group) - min(c.created for c in group)
            if time_span <= 86400:  # 24 hours in seconds
                yield ReconciliationException(type=ExceptionType.DUPLICATE_CHARGE, ...)
```

---

## 6. Configuration Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DATE_TOLERANCE_DAYS` | 2 | Allow ±2 day matching for timing differences |
| `ROUNDING_THRESHOLD_CENTS` | 10 | Accept <$0.10 as rounding, not error |
| `DUPLICATE_TIME_WINDOW_HOURS` | 24 | Flag duplicates within 24 hours |
| `DEFAULT_CURRENCY` | usd | Only USD supported in V1 |

---

## 7. API Integration

### 7.1 Key Stripe Endpoints Used

```
GET /v1/payouts                    → List all payouts
GET /v1/payouts/{id}               → Single payout detail
GET /v1/balance_transactions?payout={id}  → Transactions in payout
GET /v1/balance_transactions/{id}  → Transaction detail
```

### 7.2 Pagination Handling

Stripe API returns max 100 items per page. The client handles auto-pagination:

```python
def get_payouts(self, ...) -> list[Payout]:
    params = {"limit": 100}
    payouts = []
    
    while True:
        response = stripe.Payout.list(**params)
        payouts.extend(response.data)
        
        if not response.has_more:
            break
        params["starting_after"] = response.data[-1].id
    
    return payouts
```

---

## 8. Data Models

### 8.1 Key Pydantic Models

**Payout** (with computed properties):
```python
class Payout(BaseModel):
    id: str
    amount: int  # in cents
    transactions: list[BalanceTransaction]
    
    @property
    def gross_charges(self) -> int:
        return sum(t.amount for t in self.transactions if t.type == TransactionType.CHARGE)
    
    @property
    def total_fees(self) -> int:
        return sum(t.fee for t in self.transactions if t.type == TransactionType.CHARGE)
    
    @property
    def is_balanced(self) -> bool:
        return sum(t.net for t in self.transactions) == self.amount
```

**BalanceTransaction**:
```python
class BalanceTransaction(BaseModel):
    id: str
    amount: int      # gross (cents)
    fee: int         # fees (cents)
    net: int         # amount - fee (cents)
    type: TransactionType
    source: str | None  # charge ID, refund ID, etc.
    payout: str | None  # associated payout ID
```

---

## 9. Output Formats

### 9.1 Terminal (Rich)

- Colored tables with alignment
- Summary panel with totals
- Progress indicators

### 9.2 JSON

```json
{
  "generated_at": "2026-04-02T12:00:00",
  "summary": {
    "total_payouts": 5,
    "total_gross_revenue": 1824000,
    "total_fees": -53144,
    ...
  },
  "reconciliation_results": [...],
  "exceptions": [...]
}
```

### 9.3 CSV

Export for spreadsheet analysis:
```csv
payout_id,amount,arrival_date,status,confidence,reconciliation_status
po_xxx,484723,2026-03-01,paid,1.0,reconciled
```

---

## 10. Error Handling

### 10.1 Stripe API Errors

```python
from stripe._error import StripeError

try:
    payout = stripe_client.get_payout(payout_id)
except StripeError as e:
    click.echo(f"Stripe API error: {e}", err=True)
    sys.exit(1)
```

### 10.2 Validation

All inputs validated via Pydantic:
- Required fields enforced
- Type constraints checked
- Custom validators for amounts, dates

---

## 11. Testing Strategy

### 11.1 Test Categories

| Category | Count | Coverage |
|----------|-------|----------|
| Payout Model | 4 | Gross, fees, net, balance verification |
| Reconciler | 6 | Math verification, exact/timing/no match |
| Exception Detector | 10 | All 8 exception types |
| Bank Parser | 15 | Date parsing, CSV, extraction |

### 11.2 Test Fixtures

- `sample_payouts.json` — Mock Stripe API responses
- `perfect_match.csv` — Exact date/amount matches
- `timing_difference.csv` — Weekend delays
- `missing_entry.csv` — Missing bank entry
- `with_exceptions.csv` — All exception types

---

## 12. Future Enhancements (V2+)

- Fuzzy matching for near-matches (0.0 < confidence < 1.0)
- Plain-English explanations via LLM
- QuickBooks/Xero integration
- Multi-currency support
- Scheduled runs (cron)
- Webhook listeners for real-time processing

---

*Last updated: April 2026*
*Version: 1.0.0*