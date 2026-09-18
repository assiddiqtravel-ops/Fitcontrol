"""Support & account-recovery endpoints (platform_admin only).

These let support restore access after a lost Telegram account without ever
deleting a club or its data. Every action is audited. See app/services/recovery.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_admin
from app.db.session import get_db
from app.models import User
from app.schemas import ChangeTelegramIdIn, GrantAccessIn, RecoveryResultOut
from app.services import recovery as recovery_svc

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/clubs/{club_id}/grant-access", response_model=RecoveryResultOut)
async def grant_access(
    club_id: int,
    payload: GrantAccessIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> RecoveryResultOut:
    user, clubs = await recovery_svc.grant_club_access(
        db,
        actor_user_id=admin.id,
        club_id=club_id,
        telegram_id=payload.telegram_id,
        role=payload.role,
        reason=payload.reason,
        deactivate_membership_id=payload.deactivate_membership_id,
    )
    await db.commit()
    return RecoveryResultOut(
        ok=True,
        user_id=user.id,
        telegram_id=user.telegram_id,
        affected_club_ids=clubs,
        message="Access granted/restored; club data preserved.",
    )


@router.post("/recovery/change-telegram-id", response_model=RecoveryResultOut)
async def change_telegram_id(
    payload: ChangeTelegramIdIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> RecoveryResultOut:
    user, clubs = await recovery_svc.change_telegram_id(
        db,
        actor_user_id=admin.id,
        current_telegram_id=payload.current_telegram_id,
        new_telegram_id=payload.new_telegram_id,
        reason=payload.reason,
    )
    await db.commit()
    return RecoveryResultOut(
        ok=True,
        user_id=user.id,
        telegram_id=user.telegram_id,
        affected_club_ids=clubs,
        message="Telegram ID changed; memberships and club_ids preserved.",
    )
