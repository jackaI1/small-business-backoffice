"""Strict CSV contracts: source IDs are unique, amounts are signed account currency."""

import csv
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import Account, Dataset, Entry, Flow, Rate, money

HEADERS = {
    "accounts.csv": ["account", "currency", "balance_date", "bank_opening", "ledger_opening"],
    "bank.csv": ["id", "account", "date", "amount", "currency", "reference"],
    "ledger.csv": ["id", "account", "date", "amount", "currency", "reference"],
    "expected.csv": [
        "id",
        "account",
        "due",
        "amount",
        "currency",
        "description",
        "settled_bank_id",
    ],
    "fx.csv": ["currency", "date", "cad_per_unit"],
}


def load_csv(folder: Path) -> Dataset:
    digest = hashlib.sha256()
    tables = {}
    for name, header in HEADERS.items():
        raw = (folder / name).read_bytes()
        digest.update(name.encode() + b"\0" + raw + b"\0")
        reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
        if reader.fieldnames != header:
            raise ValueError(f"{name}: expected columns {','.join(header)}")
        rows = list(reader)
        for index, row in enumerate(rows, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"{name}:{index}: wrong number of fields")
            for key, value in row.items():
                if value != value.strip() or len(value) > 500:
                    raise ValueError(f"{name}:{index}: invalid whitespace or oversized {key}")
                if not value and key not in {"reference", "settled_bank_id"}:
                    raise ValueError(f"{name}:{index}: missing {key}")
        tables[name] = rows

    accounts = tuple(
        Account(
            r["account"],
            r["currency"],
            date.fromisoformat(r["balance_date"]),
            money(r["bank_opening"]),
            money(r["ledger_opening"]),
        )
        for r in tables["accounts.csv"]
    )
    if not accounts or len({a.id for a in accounts}) != len(accounts):
        raise ValueError("accounts must be nonempty and unique")
    by_account = {a.id: a for a in accounts}
    if any(a.currency not in {"CAD", "USD"} for a in accounts):
        raise ValueError("supported account currencies: CAD, USD")
    if len({a.balance_date for a in accounts}) != 1:
        raise ValueError("all opening balances must use the same closing date")

    def check_rows(name):
        seen = set()
        for r in tables[name]:
            if r["id"] in seen:
                raise ValueError(f"{name}: duplicate id {r['id']}")
            seen.add(r["id"])
            if r["account"] not in by_account:
                raise ValueError(f"{name}: unknown account {r['account']}")
            if r["currency"] != by_account[r["account"]].currency:
                raise ValueError(f"{name}: currency does not match account {r['account']}")
        return tables[name]

    def entries(name):
        result = tuple(
            Entry(
                r["id"],
                r["account"],
                date.fromisoformat(r["date"]),
                money(r["amount"]),
                r["reference"],
            )
            for r in check_rows(name)
        )
        if any(e.date <= by_account[e.account].balance_date for e in result):
            raise ValueError(f"{name}: entries must follow the opening balance date")
        return result

    bank, ledger = entries("bank.csv"), entries("ledger.csv")
    flows = tuple(
        Flow(
            r["id"],
            r["account"],
            date.fromisoformat(r["due"]),
            money(r["amount"]),
            r["description"],
            r["settled_bank_id"],
        )
        for r in check_rows("expected.csv")
    )
    bank_ids = {e.id: e for e in bank}
    linked = set()
    for flow in flows:
        if flow.settled_bank_id:
            entry = bank_ids.get(flow.settled_bank_id)
            if not entry or entry.account != flow.account or entry.amount != flow.amount:
                raise ValueError(
                    f"{flow.id}: settlement must link an equal bank amount and account"
                )
            if entry.id in linked:
                raise ValueError("a bank settlement cannot be assigned to two expected flows")
            linked.add(entry.id)
    rates = []
    seen = set()
    for r in tables["fx.csv"]:
        key = (r["currency"], date.fromisoformat(r["date"]))
        rate = Decimal(r["cad_per_unit"])
        if key in seen or key[0] not in {"CAD", "USD"}:
            raise ValueError("FX keys must be unique CAD/USD currency-date pairs")
        if not rate.is_finite() or not Decimal("0") < rate < Decimal("1000"):
            raise ValueError("FX rate must be finite, positive and below 1000")
        if rate != rate.quantize(Decimal("0.000001")) or (key[0] == "CAD" and rate != 1):
            raise ValueError("FX rates need at most six decimals; CAD must equal 1")
        seen.add(key)
        rates.append(Rate(*key, rate))
    return Dataset(digest.hexdigest(), accounts, bank, ledger, flows, tuple(rates))
