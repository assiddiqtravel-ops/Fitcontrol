"""Attendance registration with subscription checks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SubscriptionStatus, VisitResult
from app.core.errors import ConflictError, NotFoundError, ValidationErrorApp
from app.models import Client, Subscription, Visit
from app.services.audit import record_audit
from app.services.subscriptions import derive_status, is_usable


@dataclass
class VisitEligibility:
    allowed: bool
    reason: str  # machine code: ok | no_subscription | expired | not_started |
    #                             cancelled | limit_reached | frozen
    subscription_id: int | None
    status: str | None
    visits_left: int | None


async def _current_subscription(
    db: AsyncSession, club_id: int, client_id: int, today: date
) -> Subscription | None:
    """Pick the most relevant subscription for a visit today.

    Preference: an active (usable) subscription with the latest end date.
    Falls back to the most recently ending subscription for status reporting.
    """
    subs = (
        await db.execute(
            select(Subscription)
            .where(Subscription.club_id == club_id, Subscription.client_id == client_id)
            .order_by(Subscription.end_date.desc())
        )
    ).scalars().all()
    usable = [s for s in subs if is_usable(s, today)]
    if usable:
        usable.sort(key=lambda s: s.end_date, reverse=True)
        return usable[0]
    return subs[0] if subs else None


async def check_eligibility(
    db: AsyncSession, *, club_id: int, client_id: int, today: date | None = None
) -> VisitEligibility:
    today = today or date.today()
    client = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.club_id == club_id)
        )
    ).scalar_one_or_none()
    if client is None:
        raise NotFoundError("Client not found")

    sub = await _current_subscription(db, club_id, client_id, today)
    if sub is None:
        return VisitEligibility(False, "no_subscription", None, None, None)

    status = derive_status(sub, today)
    visits_left = None
    if sub.visit_limit is not None:
        visits_left = max(0, sub.visit_limit - sub.visits_used)

    if status == SubscriptionStatus.upcoming.value:
        return VisitEligibility(False, "not_started", sub.id, status, visits_left)
    if status == SubscriptionStatus.expired.value:
        return VisitEligibility(False, "expired", sub.id, status, visits_left)
    if status == SubscriptionStatus.cancelled.value:
        return VisitEligibility(False, "cancelled", sub.id, status, visits_left)
    if status == SubscriptionStatus.frozen.value:
        return VisitEligibility(False, "frozen", sub.id, status, visits_left)
    if sub.visit_limit is not None and sub.visits_used >= sub.visit_limit:
        return VisitEligibility(False, "limit_reached", sub.id, status, 0)

    return VisitEligibility(True, "ok", sub.id, status, visits_left)


async def register_visit(
    db: AsyncSession,
    *,
    club_id: int,
    client_id: int,
    actor_user_id: int | None,
    note: str | None = None,
    override_reason: str | None = None,
    today: date | None = None,
) -> Visit:
    """Register a visit. If not eligible, an authorized override with a written
    reason is required; otherwise the visit is rejected.
    """
    today = today or date.today()
    elig = await check_eligibility(db, club_id=club_id, client_id=client_id, today=today)

    if not elig.allowed:
        if not override_reason or not override_reason.strip():
            raise ConflictError(
                f"Visit not allowed: {elig.reason}", code=f"visit_{elig.reason}"
            )
        result = VisitResult.override.value
    else:
        result = VisitResult.allowed.value

    visit = Visit(
        club_id=club_id,
        client_id=client_id,
        subscription_id=elig.subscription_id,
        result=result,
        override_reason=override_reason.strip() if override_reason else None,
        note=note,
        recorded_by=actor_user_id,
    )
    db.add(visit)

    # Decrement the visit allowance when a limited subscription was used.
    if elig.subscription_id is not None:
        sub = (
            await db.execute(
                select(Subscription).where(Subscription.id == elig.subscription_id)
            )
        ).scalar_one()
        if sub.visit_limit is not None:
            sub.visits_used += 1

    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="visit.register",
        entity_type="visit",
        entity_id=visit.id,
        meta={"client_id": client_id, "result": result, "reason": override_reason},
    )
    return visit
