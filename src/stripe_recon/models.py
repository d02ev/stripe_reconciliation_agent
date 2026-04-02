from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    CHARGE = "charge"
    REFUND = "refund"
    DISPUTE = "dispute"
    DISPUTE_REVERSAL = "dispute_reversal"
    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"
    FEE = "stripe_fee"


class PayoutStatus(str, Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    PAID = "paid"
    CANCELED = "canceled"
    FAILED = "failed"


class ReportingCategory(str, Enum):
    CHARGE = "charge"
    REFUND = "refund"
    DISPUTE = "dispute"
    DISPUTE_REVERSAL = "dispute_reversal"
    PAYOUT = "payout"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    OTHER = "other"


class BalanceTransaction(BaseModel):
    id: str
    amount: int = Field(
        description="Gross amount in cents (positive for charges, negative for refunds)"
    )
    fee: int = Field(description="Fees in cents")
    net: int = Field(description="Net amount in cents (amount - fee)")
    currency: str = Field(default="usd")
    type: TransactionType
    reporting_category: ReportingCategory
    created: int = Field(description="Unix timestamp")
    available_on: Optional[int] = None
    description: Optional[str] = None
    source: Optional[str] = Field(
        description="ID of the related Stripe object (e.g., charge ID)"
    )
    payout: Optional[str] = Field(
        description="Payout ID if this transaction is part of a payout"
    )


class Payout(BaseModel):
    id: str
    amount: int = Field(description="Payout amount in cents")
    currency: str = Field(default="usd")
    status: PayoutStatus
    arrival_date: int = Field(description="Unix timestamp when payout arrives in bank")
    created: int = Field(description="Unix timestamp when payout was created")
    description: Optional[str] = None
    balance_transaction: Optional[str] = None
    transactions: list[BalanceTransaction] = Field(
        default_factory=list, description="Associated balance transactions"
    )

    @property
    def gross_charges(self) -> int:
        return sum(
            t.amount for t in self.transactions if t.type == TransactionType.CHARGE
        )

    @property
    def total_fees(self) -> int:
        return sum(t.fee for t in self.transactions if t.type == TransactionType.CHARGE)

    @property
    def total_refunds(self) -> int:
        return sum(
            abs(t.amount) for t in self.transactions if t.type == TransactionType.REFUND
        )

    @property
    def dispute_losses(self) -> int:
        return sum(
            abs(t.net) for t in self.transactions if t.type == TransactionType.DISPUTE
        )

    @property
    def dispute_reversals(self) -> int:
        return sum(
            t.net
            for t in self.transactions
            if t.type == TransactionType.DISPUTE_REVERSAL
        )

    @property
    def calculated_net(self) -> int:
        return sum(t.net for t in self.transactions)

    @property
    def is_balanced(self) -> bool:
        return self.calculated_net == self.amount


class BankEntry(BaseModel):
    date: datetime
    description: str
    amount: Decimal = Field(description="Amount in dollars")
    balance: Optional[Decimal] = None

    @property
    def amount_cents(self) -> int:
        return int(self.amount * 100)


class MatchConfidence(float, Enum):
    EXACT = 1.0
    TIMING_MATCH = 0.9
    NO_MATCH = 0.0


class ReconciliationStatus(str, Enum):
    RECONCILED = "reconciled"
    UNMATCHED = "unmatched"
    TIMING_DIFFERENCE = "timing_difference"
    ROUNDING_DIFFERENCE = "rounding_difference"


class ReconciliationResult(BaseModel):
    payout_id: str
    payout_amount: int
    bank_entry: Optional[BankEntry] = None
    confidence: MatchConfidence = MatchConfidence.NO_MATCH
    status: ReconciliationStatus = ReconciliationStatus.UNMATCHED
    notes: Optional[str] = None


class ExceptionType(str, Enum):
    DUPLICATE_CHARGE = "duplicate_charge"
    REFUND_ORPHAN = "refund_orphan"
    DISPUTE_OPEN = "dispute_open"
    DISPUTE_LOST = "dispute_lost"
    DISPUTE_WON = "dispute_won"
    UNMATCHED_PAYOUT = "unmatched_payout"
    UNMATCHED_BANK_ENTRY = "unmatched_bank_entry"
    ROUNDING_DIFFERENCE = "rounding_difference"


class ReconciliationException(BaseModel):
    type: ExceptionType
    description: str
    related_ids: list[str] = Field(default_factory=list)
    suggested_action: str


class ReconciliationReport(BaseModel):
    period_start: datetime
    period_end: datetime
    generated_at: datetime

    total_payouts: int
    total_gross_revenue: int
    total_fees: int
    total_refunds: int
    total_dispute_losses: int
    total_dispute_reversals: int
    net_deposited: int

    reconciled_payouts: int
    reconciled_amount: int
    unmatched_payouts: int
    unmatched_amount: int

    reconciliation_results: list[ReconciliationResult]
    exceptions: list[ReconciliationException]

    effective_fee_rate: Decimal = Field(description="Total fees / Total gross revenue")

    def to_dict(self) -> dict:
        return self.model_dump()
