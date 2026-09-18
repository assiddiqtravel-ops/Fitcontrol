"""Read helpers used by the bot (club binding, quick reports).

Every helper resolves the club from the caller's Telegram ID + membership, so a
bot user can never read another club's data.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ROLE_WEIGHT, Role
from app.models import Club, ClubMembership, User
from app.services import reports as reports_svc


async def resolve_admin_club(
    db: AsyncSession, telegram_id: int
) -> tuple[User, Club, str] | None:
    """Return (user, club, role) for the caller's highest-privilege active club.

    Only club_admin or above may use reporting commands. Returns None if the
    Telegram user is unknown or has no qualifying membership.
    """
    user = (
        await db.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if user is None:
        return None

    rows = (
        await db.execute(
            select(Club, ClubMembership.role)
            .join(ClubMembership, ClubMembership.club_id == Club.id)
            .where(ClubMembership.user_id == user.id, ClubMembership.is_active.is_(True))
        )
    ).all()
    qualifying = [
        (club, role)
        for club, role in rows
        if ROLE_WEIGHT.get(role, 0) >= ROLE_WEIGHT[Role.club_admin.value]
    ]
    if not qualifying:
        return None
    qualifying.sort(key=lambda cr: ROLE_WEIGHT.get(cr[1], 0), reverse=True)
    club, role = qualifying[0]
    return user, club, role


async def quick_report(db: AsyncSession, club_id: int) -> dict:
    today = date.today()
    return await reports_svc.dashboard(
        db, club_id=club_id, start=today.replace(day=1), end=today, today=today
    )


async def debtors(db: AsyncSession, club_id: int, limit: int = 10):
    rows = await reports_svc.clients_with_debt(db, club_id=club_id)
    return rows[:limit]


async def ending_soon(db: AsyncSession, club_id: int, within_days: int = 7):
    return await reports_svc.ending_soon_subscriptions(
        db, club_id=club_id, within_days=within_days
    )
