"""Dashboard aggregates and financial reports.

Income is recognized from actual, non-reversed payments whose ``paid_at`` falls
inside the period — future/unpaid sales are never counted as received revenue.
Debt is reported separately from received income.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AdjustmentType, ClientStatus, SubscriptionStatus
from app.models import (
    Client,
    FinancialAdjustment,
    Payment,
    Subscription,
    Visit,
)
from app.services.billing import compute_ledger


def _day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d, time.max, tzinfo=timezone.utc)
    return start, end


async def income_in_period(
    db: AsyncSession, *, club_id: int, start: date, end: date
) -> int:
    start_dt, _ = _day_bounds_utc(start)
    _, end_dt = _day_bounds_utc(end)
    total = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.club_id == club_id,
                Payment.is_reversed.is_(False),
                Payment.paid_at >= start_dt,
                Payment.paid_at <= end_dt,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def refunds_in_period(
    db: AsyncSession, *, club_id: int, start: date, end: date
) -> int:
    start_dt, _ = _day_bounds_utc(start)
    _, end_dt = _day_bounds_utc(end)
    total = (
        await db.execute(
            select(func.coalesce(func.sum(FinancialAdjustment.amount), 0)).where(
                FinancialAdjustment.club_id == club_id,
                FinancialAdjustment.type == AdjustmentType.reversal.value,
                FinancialAdjustment.created_at >= start_dt,
                FinancialAdjustment.created_at <= end_dt,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def income_by_method(
    db: AsyncSession, *, club_id: int, start: date, end: date
) -> list[tuple[str, int, int]]:
    start_dt, _ = _day_bounds_utc(start)
    _, end_dt = _day_bounds_utc(end)
    rows = (
        await db.execute(
            select(
                Payment.method,
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
            )
            .where(
                Payment.club_id == club_id,
                Payment.is_reversed.is_(False),
                Payment.paid_at >= start_dt,
                Payment.paid_at <= end_dt,
            )
            .group_by(Payment.method)
        )
    ).all()
    return [(m, int(total or 0), int(count)) for m, total, count in rows]


async def clients_with_debt(
    db: AsyncSession, *, club_id: int
) -> list[tuple[int, str, int]]:
    """Return (client_id, name, debt) for every active client with debt > 0."""
    clients = (
        await db.execute(
            select(Client).where(
                Client.club_id == club_id, Client.status == ClientStatus.active.value
            )
        )
    ).scalars().all()
    out: list[tuple[int, str, int]] = []
    for c in clients:
        ledger = await compute_ledger(db, club_id=club_id, client_id=c.id)
        if ledger.debt > 0:
            name = f"{c.first_name} {c.last_name or ''}".strip()
            out.append((c.id, name, ledger.debt))
    out.sort(key=lambda r: r[2], reverse=True)
    return out


async def dashboard(
    db: AsyncSession, *, club_id: int, start: date, end: date, today: date | None = None
) -> dict:
    today = today or date.today()

    active_clients = (
        await db.execute(
            select(func.count(Client.id)).where(
                Client.club_id == club_id, Client.status == ClientStatus.active.value
            )
        )
    ).scalar_one()

    t_start, t_end = _day_bounds_utc(today)
    visits_today = (
        await db.execute(
            select(func.count(Visit.id)).where(
                Visit.club_id == club_id,
                Visit.created_at >= t_start,
                Visit.created_at <= t_end,
            )
        )
    ).scalar_one()

    soon = today + timedelta(days=7)
    ending_soon = (
        await db.execute(
            select(func.count(Subscription.id)).where(
                Subscription.club_id == club_id,
                Subscription.status == SubscriptionStatus.active.value,
                Subscription.end_date >= today,
                Subscription.end_date <= soon,
            )
        )
    ).scalar_one()

    debtors = await clients_with_debt(db, club_id=club_id)
    total_debt = sum(d[2] for d in debtors)

    income = await income_in_period(db, club_id=club_id, start=start, end=end)

    return {
        "active_clients": int(active_clients),
        "visits_today": int(visits_today),
        "subscriptions_ending_soon": int(ending_soon),
        "clients_with_debt": len(debtors),
        "total_debt": total_debt,
        "income_in_period": income,
        "period_start": start,
        "period_end": end,
    }


async def ending_soon_subscriptions(
    db: AsyncSession, *, club_id: int, within_days: int, today: date | None = None
):
    today = today or date.today()
    limit_date = today + timedelta(days=within_days)
    return (
        await db.execute(
            select(Subscription).where(
                Subscription.club_id == club_id,
                Subscription.status == SubscriptionStatus.active.value,
                Subscription.end_date >= today,
                Subscription.end_date <= limit_date,
            )
        )
    ).scalars().all()
