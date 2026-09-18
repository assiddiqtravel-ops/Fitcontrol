"""Account-recovery operations (performed by support / platform_admin).

Why this exists
---------------
Club data is keyed by ``club_id`` and never by a Telegram user, so losing a
Telegram account never deletes a club or its data. To restore *access*, support
performs one of two audited operations:

* :func:`grant_club_access` — attach a new Telegram account to an existing club
  with a role (typically club_owner), optionally disabling the lost membership.
  ``club_id`` and all data are preserved.
* :func:`change_telegram_id` — move an existing user record to a new Telegram
  ID. The user's ``id`` and every membership (hence every ``club_id``) stay the
  same; only the Telegram identifier changes.

Security
--------
These are exposed only to ``platform_admin`` and always require a ``reason``.
A Telegram ID is never the sole recovery factor: support is expected to verify
the club's out-of-band ``recovery_email``/``recovery_phone`` before acting.
Every operation is written to :class:`AuditLog`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Role
from app.core.errors import ConflictError, NotFoundError, ValidationErrorApp
from app.models import Club, ClubMembership, User
from app.services.audit import record_audit


async def _get_or_create_user(db: AsyncSession, telegram_id: int) -> User:
    user = (
        await db.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, first_name=f"User{telegram_id}")
        db.add(user)
        await db.flush()
    return user


async def grant_club_access(
    db: AsyncSession,
    *,
    actor_user_id: int | None,
    club_id: int,
    telegram_id: int,
    role: Role,
    reason: str,
    deactivate_membership_id: int | None = None,
) -> tuple[User, list[int]]:
    """Grant/restore access to a club for the given Telegram account.

    Returns (user, affected_club_ids). The club and all its data are untouched;
    only membership rows change.
    """
    if not reason.strip():
        raise ValidationErrorApp("A verification reason is required")

    club = (await db.execute(select(Club).where(Club.id == club_id))).scalar_one_or_none()
    if club is None:
        raise NotFoundError("Club not found")

    user = await _get_or_create_user(db, telegram_id)

    membership = (
        await db.execute(
            select(ClubMembership).where(
                ClubMembership.club_id == club_id, ClubMembership.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = ClubMembership(
            club_id=club_id, user_id=user.id, role=role.value, is_active=True
        )
        db.add(membership)
    else:
        membership.role = role.value
        membership.is_active = True
    await db.flush()

    if deactivate_membership_id is not None:
        old = (
            await db.execute(
                select(ClubMembership).where(
                    ClubMembership.id == deactivate_membership_id,
                    ClubMembership.club_id == club_id,
                )
            )
        ).scalar_one_or_none()
        if old is not None and old.id != membership.id:
            old.is_active = False
            await db.flush()

    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="recovery.grant_access",
        entity_type="club_membership",
        entity_id=membership.id,
        meta={
            "telegram_id": telegram_id,
            "role": role.value,
            "reason": reason.strip(),
            "deactivated_membership_id": deactivate_membership_id,
        },
    )
    return user, [club_id]


async def change_telegram_id(
    db: AsyncSession,
    *,
    actor_user_id: int | None,
    current_telegram_id: int,
    new_telegram_id: int,
    reason: str,
) -> tuple[User, list[int]]:
    """Rebind an existing user to a new Telegram ID, preserving all memberships.

    Returns (user, affected_club_ids). Fails if the new Telegram ID is already
    in use by another user.
    """
    if not reason.strip():
        raise ValidationErrorApp("A verification reason is required")
    if current_telegram_id == new_telegram_id:
        raise ValidationErrorApp("New Telegram ID must differ from the current one")

    user = (
        await db.execute(select(User).where(User.telegram_id == current_telegram_id))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User with the current Telegram ID not found")

    clash = (
        await db.execute(select(User).where(User.telegram_id == new_telegram_id))
    ).scalar_one_or_none()
    if clash is not None:
        raise ConflictError("The new Telegram ID is already in use")

    memberships = (
        await db.execute(
            select(ClubMembership).where(ClubMembership.user_id == user.id)
        )
    ).scalars().all()
    affected = [m.club_id for m in memberships]

    old_tg = user.telegram_id
    user.telegram_id = new_telegram_id
    # Reset stale profile fields; they refresh on next authenticated request.
    user.username = None
    await db.flush()

    # Audit under every club the user belongs to (keeps the trail club-scoped).
    for club_id in affected:
        await record_audit(
            db,
            club_id=club_id,
            actor_user_id=actor_user_id,
            action="recovery.change_telegram_id",
            entity_type="user",
            entity_id=user.id,
            meta={
                "old_telegram_id": old_tg,
                "new_telegram_id": new_telegram_id,
                "reason": reason.strip(),
            },
        )
    return user, affected
