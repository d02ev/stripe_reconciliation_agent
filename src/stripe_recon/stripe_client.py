import os
from datetime import datetime
from typing import Optional

import stripe
from stripe._error import StripeError

from stripe_recon.config import settings
from stripe_recon.models import (
    BalanceTransaction,
    Payout,
    PayoutStatus,
    ReportingCategory,
    TransactionType,
)


class StripeClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.STRIPE_API_KEY
        if not self.api_key:
            raise ValueError("Stripe API key is required. Set STRIPE_API_KEY in .env")
        stripe.api_key = self.api_key

    def _parse_transaction_type(self, type_str: str) -> TransactionType:
        mapping = {
            "charge": TransactionType.CHARGE,
            "refund": TransactionType.REFUND,
            "dispute": TransactionType.DISPUTE,
            "payment_refund": TransactionType.REFUND,
            "payout": TransactionType.PAYOUT,
            "payout_cancel": TransactionType.PAYOUT,
            "payout_failure": TransactionType.PAYOUT,
            "stripe_fee": TransactionType.FEE,
            "stripe_fx_fee": TransactionType.FEE,
            "adjustment": TransactionType.ADJUSTMENT,
        }
        return mapping.get(type_str, TransactionType.OTHER)

    def _parse_reporting_category(self, category: str) -> ReportingCategory:
        mapping = {
            "charge": ReportingCategory.CHARGE,
            "refund": ReportingCategory.REFUND,
            "dispute": ReportingCategory.DISPUTE,
            "dispute_reversal": ReportingCategory.DISPUTE_REVERSAL,
            "payout": ReportingCategory.PAYOUT,
            "transfer": ReportingCategory.TRANSFER,
            "adjustment": ReportingCategory.ADJUSTMENT,
        }
        return mapping.get(category, ReportingCategory.OTHER)

    def _map_payout_status(self, status: str) -> PayoutStatus:
        mapping = {
            "pending": PayoutStatus.PENDING,
            "in_transit": PayoutStatus.IN_TRANSIT,
            "paid": PayoutStatus.PAID,
            "canceled": PayoutStatus.CANCELED,
            "failed": PayoutStatus.FAILED,
        }
        return mapping.get(status, PayoutStatus.PENDING)

    def _convert_balance_transaction(self, tx_data: dict) -> BalanceTransaction:
        return BalanceTransaction(
            id=tx_data.get("id", ""),
            amount=tx_data.get("amount", 0),
            fee=tx_data.get("fee", 0),
            net=tx_data.get("net", 0),
            currency=tx_data.get("currency", "usd"),
            type=self._parse_transaction_type(tx_data.get("type", "")),
            reporting_category=self._parse_reporting_category(
                tx_data.get("reporting_category", "")
            ),
            created=tx_data.get("created", 0),
            available_on=tx_data.get("available_on"),
            description=tx_data.get("description"),
            source=tx_data.get("source"),
            payout=tx_data.get("payout"),
        )

    def get_payouts(
        self,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> list[Payout]:
        params: dict = {"limit": 100, "created": {}}

        if created_after:
            params["created"]["gte"] = int(created_after.timestamp())
        if created_before:
            params["created"]["lte"] = int(created_before.timestamp())
        if status:
            params["status"] = status

        payouts = []
        while True:
            response = stripe.Payout.list(**params)
            for payout_data in response.data:
                transactions = self.get_balance_transactions(payout_data.id)
                payout = Payout(
                    id=payout_data.id,
                    amount=payout_data.amount,
                    currency=payout_data.currency,
                    status=self._map_payout_status(payout_data.status),
                    arrival_date=payout_data.arrival_date,
                    created=payout_data.created,
                    description=payout_data.description,
                    balance_transaction=str(payout_data.balance_transaction)
                    if payout_data.balance_transaction
                    else None,
                    transactions=transactions,
                )
                payouts.append(payout)

            if not response.has_more:
                break
            params["starting_after"] = response.data[-1].id

        return payouts

    def get_balance_transactions(self, payout_id: str) -> list[BalanceTransaction]:
        params = {"limit": 100, "payout": payout_id}

        transactions = []
        while True:
            response = stripe.BalanceTransaction.list(**params)
            for tx_data in response.data:
                tx = self._convert_balance_transaction(tx_data)
                transactions.append(tx)

            if not response.has_more:
                break
            params["starting_after"] = tx_data["id"]

        return transactions

    def get_payout(self, payout_id: str) -> Payout:
        payout_data = stripe.Payout.retrieve(payout_id)
        transactions = self.get_balance_transactions(payout_id)

        return Payout(
            id=payout_data.id,
            amount=payout_data.amount,
            currency=payout_data.currency,
            status=self._map_payout_status(payout_data.status),
            arrival_date=payout_data.arrival_date,
            created=payout_data.created,
            description=payout_data.description,
            balance_transaction=str(payout_data.balance_transaction)
            if payout_data.balance_transaction
            else None,
            transactions=transactions,
        )

    def verify_connection(self) -> bool:
        try:
            stripe.Balance.retrieve()
            return True
        except StripeError:
            return False
