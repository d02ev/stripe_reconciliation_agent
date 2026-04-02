import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from stripe_recon.models import BankEntry


class BankParser:
    DATE_FORMATS = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    STRIPE_KEYWORDS = ["stripe", "stripe payout", "stripe transfer"]

    @classmethod
    def normalize_date(cls, date_str: str) -> Optional[datetime]:
        date_str = date_str.strip()
        for fmt in cls.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def is_stripe_entry(cls, description: str) -> bool:
        desc_lower = description.lower().strip()
        return any(keyword in desc_lower for keyword in cls.STRIPE_KEYWORDS)

    @classmethod
    def parse_amount(cls, amount_str: str) -> Decimal:
        amount_str = amount_str.strip()
        amount_str = amount_str.replace("$", "").replace(",", "")

        if amount_str.startswith("(") and amount_str.endswith(")"):
            amount_str = "-" + amount_str[1:-1]

        return Decimal(amount_str)

    @classmethod
    def parse_csv(cls, file_path: str) -> list[BankEntry]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Bank statement file not found: {file_path}")

        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            field_names = [name.lower().strip() for name in reader.fieldnames or []]

            date_col, desc_col, amount_col, balance_col = cls._identify_columns(
                field_names
            )

            entries = []
            for row in reader:
                try:
                    date_str = row.get(date_col, "").strip()
                    description = row.get(desc_col, "").strip()
                    amount_str = row.get(amount_col, "").strip()
                    balance_str = (
                        row.get(balance_col, "").strip() if balance_col else None
                    )

                    if not date_str or not description or not amount_str:
                        continue

                    date = cls.normalize_date(date_str)
                    if not date:
                        continue

                    amount = cls.parse_amount(amount_str)
                    balance = cls.parse_amount(balance_str) if balance_str else None

                    entry = BankEntry(
                        date=date,
                        description=description,
                        amount=amount,
                        balance=balance,
                    )
                    entries.append(entry)

                except ValueError, KeyError:
                    continue

        return entries

    @classmethod
    def _identify_columns(
        cls, field_names: list[str]
    ) -> tuple[str, str, str, Optional[str]]:
        date_col = desc_col = amount_col = balance_col = None

        date_patterns = ["date", "transaction date", "posted date", "trans date"]
        desc_patterns = ["description", "memo", "details", "narrative", "transaction"]
        amount_patterns = ["amount", "debit", "credit", "value", "transaction amount"]
        balance_patterns = ["balance", "running balance", "available"]

        for name in field_names:
            name_lower = name.lower()
            if not date_col and any(p in name_lower for p in date_patterns):
                date_col = name
            elif not desc_col and any(p in name_lower for p in desc_patterns):
                desc_col = name
            elif not amount_col and any(p in name_lower for p in amount_patterns):
                amount_col = name
            elif not balance_col and any(p in name_lower for p in balance_patterns):
                balance_col = name

        if not date_col:
            date_col = field_names[0] if field_names else "date"
        if not desc_col:
            desc_col = field_names[1] if len(field_names) > 1 else "description"
        if not amount_col:
            amount_col = field_names[2] if len(field_names) > 2 else "amount"

        return date_col, desc_col, amount_col, balance_col

    @classmethod
    def extract_stripe_entries(cls, entries: list[BankEntry]) -> list[BankEntry]:
        return [entry for entry in entries if cls.is_stripe_entry(entry.description)]

    @classmethod
    def filter_by_date_range(
        cls,
        entries: list[BankEntry],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[BankEntry]:
        filtered = entries
        if start_date:
            filtered = [e for e in filtered if e.date >= start_date]
        if end_date:
            filtered = [e for e in filtered if e.date <= end_date]
        return filtered
