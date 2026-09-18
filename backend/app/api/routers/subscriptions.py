"""Subscription endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_admin, require_trainer
from app.db.session import get_db
from app.models import Subscription
from app.schemas import (
    SubscriptionCancelIn,
    SubscriptionCreate,
    SubscriptionFreezeIn,
    SubscriptionOut,
    SubscriptionUnfreezeIn,
)
from app.services import subscriptions as sub_svc

router = APIRouter()


@router.get("/subscriptions", response_model=list[SubscriptionOut], tags=["subscriptions"])
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    client_id: int | None = Query(default=None),
) -> list[SubscriptionOut]:
    conditions = [Subscription.club_id == ctx.club_id]
    if client_id is not None:
        conditions.append(Subscription.client_id == client_id)
    rows = (
        await db.execute(
            select(Subscription).where(*conditions).order_by(Subscription.created_at.desc())
        )
    ).scalars().all()
    # Derive display status without mutating stored rows.
    today = date.today()
    out = []
    for s in rows:
        model = SubscriptionOut.model_validate(s)
        model.status = sub_svc.derive_status(s, today)
        out.append(model)
    return out


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201, tags=["subscriptions"])
async def create_subscription(
    payload: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> SubscriptionOut:
    sub = await sub_svc.create_subscription(
        db,
        club_id=ctx.club_id,
        client_id=payload.client_id,
        plan_id=payload.plan_id,
        start_date=payload.start_date,
        actor_user_id=ctx.user.id,
        create_charge_row=payload.create_charge,
    )
    await db.commit()
    return SubscriptionOut.model_validate(sub)


@router.post(
    "/subscriptions/{subscription_id}/freeze",
    response_model=SubscriptionOut,
    tags=["subscriptions"],
)
async def freeze(
    subscription_id: int,
    payload: SubscriptionFreezeIn,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> SubscriptionOut:
    await sub_svc.freeze_subscription(
        db,
        club_id=ctx.club_id,
        subscription_id=subscription_id,
        start_date=payload.start_date,
        reason=None,
        actor_user_id=ctx.user.id,
    )
    await db.commit()
    sub = (
        await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    ).scalar_one()
    return SubscriptionOut.model_validate(sub)


@router.post(
    "/subscriptions/{subscription_id}/unfreeze",
    response_model=SubscriptionOut,
    tags=["subscriptions"],
)
async def unfreeze(
    subscription_id: int,
    payload: SubscriptionUnfreezeIn,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> SubscriptionOut:
    sub = await sub_svc.unfreeze_subscription(
        db,
        club_id=ctx.club_id,
        subscription_id=subscription_id,
        end_date=payload.end_date,
        actor_user_id=ctx.user.id,
    )
    await db.commit()
    return SubscriptionOut.model_validate(sub)


@router.post(
    "/subscriptions/{subscription_id}/cancel",
    response_model=SubscriptionOut,
    tags=["subscriptions"],
)
async def cancel(
    subscription_id: int,
    payload: SubscriptionCancelIn,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> SubscriptionOut:
    sub = await sub_svc.cancel_subscription(
        db,
        club_id=ctx.club_id,
        subscription_id=subscription_id,
        reason=payload.reason,
        actor_user_id=ctx.user.id,
    )
    await db.commit()
    return SubscriptionOut.model_validate(sub)
