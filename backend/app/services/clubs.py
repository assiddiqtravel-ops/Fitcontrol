"""Club creation, membership and staff invites."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InviteStatus, Role
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationErrorApp
from app.models import Club, ClubMembership, StaffInvite, User
from app.services.audit import record_audit


async def create_club(
    db: AsyncSession,
    *,
    owner: User,
    name: str,
    timezone_name: str = "Asia/Tashkent",
    default_language: str = "ru",
) -> Club:
    if not name or not name.strip():
        raise ValidationErrorApp("Club name is required")
    club = Club(
        name=name.strip(),
        timezone=timezone_name,
        default_language=default_language,
    )
    db.add(club)
    await db.flush()

    membership = ClubMembership(
        club_id=club.id,
        user_id=owner.id,
        role=Role.club_owner.value,
        is_active=True,
    )
    db.add(membership)
    await db.flush()
    await record_audit(
        db,
        club_id=club.id,
        actor_user_id=owner.id,
        action="club.create",
        entity_type="club",
        entity_id=club.id,
        meta={"name": club.name},
    )
    return club


async def list_user_clubs(db: AsyncSession, user: User) -> list[tuple[Club, str]]:
    rows = (
        await db.execute(
            select(Club, ClubMembership.role)
            .join(ClubMembership, ClubMembership.club_id == Club.id)
            .where(ClubMembership.user_id == user.id, ClubMembership.is_active.is_(True))
            .order_by(Club.created_at.asc())
        )
    ).all()
    return [(club, role) for club, role in rows]


def _new_code() -> str:
    # Short, unambiguous, URL-safe uppercase code.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def create_invite(
    db: AsyncSession,
    *,
    club_id: int,
    role: str,
    telegram_id: int | None,
    ttl_hours: int,
    actor_user_id: int | None,
) -> StaffInvite:
    if role not in {Role.club_admin.value, Role.trainer.value, Role.club_owner.value}:
        raise ValidationErrorApp("Invalid role for invite")
    if ttl_hours <= 0 or ttl_hours > 24 * 30:
        raise ValidationErrorApp("ttl_hours must be between 1 and 720")

    # Ensure code uniqueness (retry a few times on the astronomically rare clash).
    code = _new_code()
    for _ in range(5):
        exists = (
            await db.execute(select(StaffInvite).where(StaffInvite.code == code))
        ).scalar_one_or_none()
        if exists is None:
            break
        code = _new_code()

    invite = StaffInvite(
        club_id=club_id,
        code=code,
        role=role,
        telegram_id=telegram_id,
        status=InviteStatus.pending.value,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        created_by=actor_user_id,
    )
    db.add(invite)
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="staff.invite.create",
        entity_type="staff_invite",
        entity_id=invite.id,
        meta={"role": role, "telegram_id": telegram_id},
    )
    return invite


async def accept_invite(db: AsyncSession, *, code: str, user: User) -> ClubMembership:
    invite = (
        await db.execute(select(StaffInvite).where(StaffInvite.code == code.strip().upper()))
    ).scalar_one_or_none()
    if invite is None:
        raise NotFoundError("Invite not found")
    if invite.status != InviteStatus.pending.value:
        raise ConflictError("Invite is not pending")
    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = InviteStatus.expired.value
        await db.flush()
        raise ConflictError("Invite has expired")
    if invite.telegram_id is not None and invite.telegram_id != user.telegram_id:
        raise ForbiddenError("This invite is bound to a different Telegram account")

    existing = (
        await db.execute(
            select(ClubMembership).where(
                ClubMembership.club_id == invite.club_id,
                ClubMembership.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.is_active = True
        existing.role = invite.role
        membership = existing
    else:
        membership = ClubMembership(
            club_id=invite.club_id,
            user_id=user.id,
            role=invite.role,
            is_active=True,
        )
        db.add(membership)

    invite.status = InviteStatus.accepted.value
    invite.accepted_by = user.id
    await db.flush()
    await record_audit(
        db,
        club_id=invite.club_id,
        actor_user_id=user.id,
        action="staff.invite.accept",
        entity_type="club_membership",
        entity_id=membership.id,
        meta={"role": invite.role},
    )
    return membership


async def set_membership_active(
    db: AsyncSession,
    *,
    club_id: int,
    membership_id: int,
    is_active: bool,
    actor_user_id: int | None,
) -> ClubMembership:
    membership = (
        await db.execute(
            select(ClubMembership).where(
                ClubMembership.id == membership_id, ClubMembership.club_id == club_id
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Staff member not found")

    # Guard: never disable the last active owner.
    if membership.role == Role.club_owner.value and not is_active:
        owners = (
            await db.execute(
                select(ClubMembership).where(
                    ClubMembership.club_id == club_id,
                    ClubMembership.role == Role.club_owner.value,
                    ClubMembership.is_active.is_(True),
                )
            )
        ).scalars().all()
        if len([o for o in owners if o.id != membership_id]) == 0:
            raise ConflictError("Cannot disable the last active owner")

    membership.is_active = is_active
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="staff.set_active",
        entity_type="club_membership",
        entity_id=membership.id,
        meta={"is_active": is_active},
    )
    return membership
