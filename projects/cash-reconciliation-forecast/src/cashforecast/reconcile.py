"""Conservative one-to-one matching with a separately balanced exception bridge."""

from datetime import date
from decimal import Decimal

from .models import Account, Entry, reference


def age_band(days: int) -> str:
    if days <= 7:
        return "0-7"
    if days <= 30:
        return "8-30"
    if days <= 60:
        return "31-60"
    return "61+"


def reconcile(
    accounts: tuple[Account, ...],
    bank: tuple[Entry, ...],
    ledger: tuple[Entry, ...],
    as_of: date,
    window: int = 3,
) -> dict:
    if window < 0 or window > 31:
        raise ValueError("date window must be between 0 and 31 days")
    if any(as_of <= a.balance_date for a in accounts):
        raise ValueError("as-of must follow opening balance date")
    future_bank_count = sum(e.date > as_of for e in bank)
    future_ledger_count = sum(e.date > as_of for e in ledger)
    bank = tuple(e for e in bank if e.date <= as_of)
    ledger = tuple(e for e in ledger if e.date <= as_of)
    remaining_b = {e.id: e for e in bank}
    remaining_l = {e.id: e for e in ledger}
    pairs = []

    def eligible(b, book):
        return b.account == book.account and abs((b.date - book.date).days) <= window

    def same_ref(b, book):
        return bool(reference(b.reference)) and reference(b.reference) == reference(book.reference)

    def stage(rule, predicate):
        # Only mutual unique candidates. Never arbitrarily consume one duplicate.
        edges = {
            b.id: [
                book.id for book in remaining_l.values() if eligible(b, book) and predicate(b, book)
            ]
            for b in remaining_b.values()
        }
        counts = {}
        for ids in edges.values():
            for lid in ids:
                counts[lid] = counts.get(lid, 0) + 1
        for bid, lids in sorted(edges.items()):
            if len(lids) != 1 or counts[lids[0]] != 1:
                continue
            b, book = remaining_b.pop(bid), remaining_l.pop(lids[0])
            delta = b.amount - book.amount
            pairs.append(
                {
                    "account": b.account,
                    "bank_id": b.id,
                    "ledger_id": book.id,
                    "rule": rule,
                    "variance": delta,
                    "bank_amount": b.amount,
                    "ledger_amount": book.amount,
                    "date_gap": abs((b.date - book.date).days),
                    "age_days": (as_of - min(b.date, book.date)).days,
                    "age_band": age_band((as_of - min(b.date, book.date)).days),
                }
            )

    stage("reference_amount", lambda b, book: same_ref(b, book) and b.amount == book.amount)
    # Amount-only is allowed when either reference is missing; conflicting refs remain open.
    stage(
        "amount_date",
        lambda b, book: (
            b.amount == book.amount
            and (not reference(b.reference) or not reference(book.reference))
        ),
    )
    # An amount difference is a review item, never an automatic cleared match.
    stage("variance_review", lambda b, book: same_ref(b, book) and b.amount != book.amount)
    unmatched = []
    for source, entries, other in (
        ("bank", remaining_b, remaining_l),
        ("ledger", remaining_l, remaining_b),
    ):
        for e in sorted(entries.values(), key=lambda e: (e.date, e.id)):
            candidates = [
                o.id
                for o in other.values()
                if eligible(e, o) and (e.amount == o.amount or same_ref(e, o))
            ]
            days = (as_of - e.date).days
            unmatched.append(
                {
                    "source": source,
                    "id": e.id,
                    "account": e.account,
                    "date": e.date,
                    "amount": e.amount,
                    "reference": e.reference,
                    "reason": "ambiguous_or_conflicting" if candidates else "no_candidate",
                    "candidates": sorted(candidates),
                    "age_days": days,
                    "age_band": age_band(days),
                }
            )
    controls = []
    for a in accounts:
        b_close = a.bank_opening + sum((e.amount for e in bank if e.account == a.id), Decimal(0))
        l_close = a.ledger_opening + sum(
            (e.amount for e in ledger if e.account == a.id), Decimal(0)
        )
        bank_open = sum((e.amount for e in remaining_b.values() if e.account == a.id), Decimal(0))
        ledger_open = sum((e.amount for e in remaining_l.values() if e.account == a.id), Decimal(0))
        variance = sum((p["variance"] for p in pairs if p["account"] == a.id), Decimal(0))
        opening_difference = a.bank_opening - a.ledger_opening
        explained = opening_difference + bank_open - ledger_open + variance
        controls.append(
            {
                "account": a.id,
                "currency": a.currency,
                "bank_closing": b_close,
                "ledger_closing": l_close,
                "difference": b_close - l_close,
                "opening_difference": opening_difference,
                "bank_unmatched": bank_open,
                "ledger_unmatched": ledger_open,
                "paired_variance": variance,
                "unexplained": b_close - l_close - explained,
            }
        )
    return {
        "pairs": pairs,
        "unmatched": unmatched,
        "controls": controls,
        "bank_count": len(bank),
        "ledger_count": len(ledger),
        "future_bank_count": future_bank_count,
        "future_ledger_count": future_ledger_count,
    }
