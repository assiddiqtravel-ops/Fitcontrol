"""Money handling.

DECISION: money is stored as **integer UZS (сум)** — the whole-currency unit.

Rationale: the Uzbek so'm has effectively no sub-unit in circulation (the
tiyin is defunct in practice; prices, receipts and bank transfers are all in
whole so'm). Storing whole so'm as a Python/PostgreSQL integer keeps arithmetic
exact, avoids floating-point rounding entirely, and matches how clubs actually
price memberships. All amounts in the API are integers of UZS.

If a deployment ever needs sub-unit precision, switch the column type to a
scaled integer (e.g. tiyin = UZS * 100) in a single migration — the code never
uses floats, so only the scale constant changes.
"""
from __future__ import annotations

# Amounts are whole UZS. This constant documents the scale (1 = no sub-unit).
UZS_SCALE = 1


def format_uzs(amount: int, locale: str = "ru") -> str:
    """Format an integer UZS amount with thin-space thousands separators.

    Example: 1500000 -> "1 500 000 UZS"
    """
    sign = "-" if amount < 0 else ""
    grouped = f"{abs(int(amount)):,}".replace(",", " ")
    suffix = "so'm" if locale == "uz" else "UZS"
    return f"{sign}{grouped} {suffix}"
