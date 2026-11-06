import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value: str) -> Decimal:
    number = Decimal(value)
    if not number.is_finite() or abs(number) >= Decimal("1000000000000"):
        raise ValueError("amount must be finite and less than one trillion")
    if number != number.quantize(CENT):
        raise ValueError("amount must have at most two decimal places")
    return number.quantize(CENT)


def rounded(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def reference(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


@dataclass(frozen=True)
class Account:
    id: str
    currency: str
    balance_date: date
    bank_opening: Decimal
    ledger_opening: Decimal


@dataclass(frozen=True)
class Entry:
    id: str
    account: str
    date: date
    amount: Decimal
    reference: str


@dataclass(frozen=True)
class Flow:
    id: str
    account: str
    due: date
    amount: Decimal
    description: str
    settled_bank_id: str = ""


@dataclass(frozen=True)
class Rate:
    currency: str
    date: date
    cad_per_unit: Decimal


@dataclass(frozen=True)
class Dataset:
    id: str
    accounts: tuple[Account, ...]
    bank: tuple[Entry, ...]
    ledger: tuple[Entry, ...]
    flows: tuple[Flow, ...]
    rates: tuple[Rate, ...]
