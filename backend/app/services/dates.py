"""Date arithmetic for subscription periods.

CALENDAR RULES (documented for predictability):

* ``duration_unit == days``: the period covers ``duration_value`` calendar days
  **inclusive** of the start date. A 30-day subscription starting on the 1st
  ends on the 30th (start + 29 days). ``visit``/expiry checks treat ``end_date``
  as the last valid day (inclusive).

* ``duration_unit == months``: we add whole calendar months using
  :func:`dateutil.relativedelta`, then subtract one day so the period is
  inclusive. A 1-month subscription starting Jan 15 ends Feb 14. Month-end is
  clamped by relativedelta: starting Jan 31 + 1 month = Feb 28/29, minus one day
  = Feb 27/28. This clamping is intentional and documented.

Freezing: a freeze pauses the clock. When a freeze ends, the subscription's
``end_date`` is extended by the number of frozen days so the client does not
lose paid time.
"""
from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app.core.enums import DurationUnit
from app.core.errors import ValidationErrorApp


def compute_end_date(start: date, unit: str, value: int) -> date:
    """Return the inclusive end date for a period beginning on ``start``."""
    if value <= 0:
        raise ValidationErrorApp("Duration must be a positive number")
    if unit == DurationUnit.days.value:
        return start + timedelta(days=value - 1)
    if unit == DurationUnit.months.value:
        return start + relativedelta(months=value) - timedelta(days=1)
    raise ValidationErrorApp(f"Unknown duration unit: {unit}")


def days_inclusive(start: date, end: date) -> int:
    """Number of calendar days in an inclusive [start, end] range."""
    if end < start:
        raise ValidationErrorApp("end date is before start date")
    return (end - start).days + 1


def extend_end_date(end: date, by_days: int) -> date:
    if by_days < 0:
        raise ValidationErrorApp("Cannot extend by a negative number of days")
    return end + timedelta(days=by_days)
