"""Subscription lifecycle: create, freeze/unfreeze, extend, cancel, status."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SubscriptionStatus
from app.core.errors import ConflictError, NotFoundError, ValidationErrorApp
from app.models import Client, Plan, Subscription, SubscriptionFreeze
from app.services.audit import record_audit
from app.services.billing import create_charge
from app.services.dates import compute_end_date, days_inclusive, extend_end_date


def derive_status(sub: Subscription, today: date) -> str:
    """Pure status derivation used for read models (does not mutate)."""
    if sub.status in (SubscriptionStatus.cancelled.value, SubscriptionStatus.frozen.value):
        return sub.status
    if sub.start_date > today:
        return SubscriptionStatus.upcoming.value
    if sub.end_date < today:
        return SubscriptionStatus.expired.value
    return SubscriptionStatus.active.value


def is_usable(sub: Subscription, today: date) -> bool:
    """Whether a subscription currently permits a visit (before limit checks)."""
    status = derive_status(sub, today)
    if status not in (SubscriptionStatus.active.value, SubscriptionStatus.upcoming.value):
        return False
    if status == SubscriptionStatus.upcoming.value:
        return False
    if sub.visit_limit is not None and sub.visits_used >= sub.visit_limit:
        return False
    return True


async def create_subscription(
    db: AsyncSession,
    *,
    club_id: int,
    client_id: int,
    plan_id: int,
    start_date: date,
    actor_user_id: int | None,
    create_charge_row: bool = True,
) -> Subscription:
    client = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.club_id == club_id)
        )
    ).scalar_one_or_none()
    if client is None:
        raise NotFoundError("Client not found")

    plan = (
        await db.execute(select(Plan).where(Plan.id == plan_id, Plan.club_id == club_id))
    ).scalar_one_or_none()
    if plan is None:
        raise NotFoundError("Plan not found")
    if not plan.is_active:
        raise ValidationErrorApp("Plan is not active")

    end_date = compute_end_date(start_date, plan.duration_unit, plan.duration_value)

    today = date.today()
    status = (
        SubscriptionStatus.upcoming.value
        if start_date > today
        else SubscriptionStatus.active.value
    )

    sub = Subscription(
        club_id=club_id,
        client_id=client_id,
        plan_id=plan_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        visit_limit=plan.visit_limit,
        visits_used=0,
        price=plan.price,
    )
    db.add(sub)
    await db.flush()

    if create_charge_row and plan.price > 0:
        await create_charge(
            db,
            club_id=club_id,
            client_id=client_id,
            amount=plan.price,
            description=f"Subscription: {plan.name}",
            subscription_id=sub.id,
            actor_user_id=actor_user_id,
        )

    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="subscription.create",
        entity_type="subscription",
        entity_id=sub.id,
        meta={"client_id": client_id, "plan_id": plan_id, "price": plan.price},
    )
    return sub


async def freeze_subscription(
    db: AsyncSession,
    *,
    club_id: int,
    subscription_id: int,
    start_date: date,
    reason: str | None,
    actor_user_id: int | None,
) -> SubscriptionFreeze:
    sub = await _get_sub(db, club_id, subscription_id)
    if sub.status == SubscriptionStatus.cancelled.value:
        raise ConflictError("Cannot freeze a cancelled subscription")
    if sub.status == SubscriptionStatus.frozen.value:
        raise ConflictError("Subscription is already frozen")

    open_freeze = await _open_freeze(db, subscription_id)
    if open_freeze is not None:
        raise ConflictError("An open freeze already exists")

    freeze = SubscriptionFreeze(
        club_id=club_id,
        subscription_id=subscription_id,
        start_date=start_date,
        end_date=None,
        reason=reason,
        created_by=actor_user_id,
    )
    db.add(freeze)
    sub.status = SubscriptionStatus.frozen.value
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="subscription.freeze",
        entity_type="subscription",
        entity_id=sub.id,
        meta={"start_date": start_date.isoformat(), "reason": reason},
    )
    return freeze


async def unfreeze_subscription(
    db: AsyncSession,
    *,
    club_id: int,
    subscription_id: int,
    end_date: date,
    actor_user_id: int | None,
) -> Subscription:
    sub = await _get_sub(db, club_id, subscription_id)
    freeze = await _open_freeze(db, subscription_id)
    if freeze is None:
        raise ConflictError("Subscription is not frozen")
    if end_date < freeze.start_date:
        raise ValidationErrorApp("Freeze end date is before its start date")

    frozen_days = days_inclusive(freeze.start_date, end_date)
    freeze.end_date = end_date
    sub.frozen_days += frozen_days
    # Extend the paid period by the number of frozen days.
    sub.end_date = extend_end_date(sub.end_date, frozen_days)
    sub.status = derive_status(sub, date.today())
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="subscription.unfreeze",
        entity_type="subscription",
        entity_id=sub.id,
        meta={"frozen_days": frozen_days, "new_end_date": sub.end_date.isoformat()},
    )
    return sub


async def cancel_subscription(
    db: AsyncSession,
    *,
    club_id: int,
    subscription_id: int,
    reason: str | None,
    actor_user_id: int | None,
) -> Subscription:
    sub = await _get_sub(db, club_id, subscription_id)
    if sub.status == SubscriptionStatus.cancelled.value:
        raise ConflictError("Subscription is already cancelled")
    sub.status = SubscriptionStatus.cancelled.value
    sub.cancelled_reason = reason
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="subscription.cancel",
        entity_type="subscription",
        entity_id=sub.id,
        meta={"reason": reason},
    )
    return sub


async def _get_sub(db: AsyncSession, club_id: int, subscription_id: int) -> Subscription:
    sub = (
        await db.execute(
            select(Subscription).where(
                Subscription.id == subscription_id, Subscription.club_id == club_id
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


async def _open_freeze(db: AsyncSession, subscription_id: int) -> SubscriptionFreeze | None:
    return (
        await db.execute(
            select(SubscriptionFreeze).where(
                SubscriptionFreeze.subscription_id == subscription_id,
                SubscriptionFreeze.end_date.is_(None),
            )
        )
    ).scalar_one_or_none()
