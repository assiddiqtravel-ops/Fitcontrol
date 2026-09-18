"""Request-scoped authentication & authorization dependencies.

Auth flow (production):
  * The Mini App sends the raw Telegram ``initData`` in the ``X-Init-Data``
    header (or ``Authorization: tma <initData>``).
  * We validate the HMAC signature + freshness server-side and resolve/create
    the ``User`` by telegram_id. The client-supplied user id is NEVER trusted.
  * The active club is chosen with the ``X-Club-Id`` header; membership and role
    are verified against the DB on every request (tenant isolation).

DEV_AUTH_MODE (never in production): allows ``X-Dev-Telegram-Id`` to stand in
for a validated identity so the API can be exercised without a real Mini App.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ROLE_WEIGHT, Role
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.telegram_auth import InitDataError, TelegramUser, validate_init_data
from app.db.session import get_db
from app.models import Club, ClubMembership, User


@dataclass
class AuthContext:
    user: User
    # Populated once a club is selected; None for club-agnostic endpoints.
    club: Club | None = None
    membership: ClubMembership | None = None

    @property
    def role(self) -> str | None:
        return self.membership.role if self.membership else None

    @property
    def club_id(self) -> int | None:
        return self.club.id if self.club else None


async def _resolve_telegram_user(tg: TelegramUser, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.telegram_id == tg.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=tg.id,
            first_name=tg.first_name,
            last_name=tg.last_name,
            username=tg.username,
            language=(tg.language_code or "ru")[:2] if tg.language_code else "ru",
        )
        db.add(user)
        await db.flush()
    else:
        # Refresh mutable profile fields opportunistically.
        changed = False
        for attr, value in (
            ("first_name", tg.first_name),
            ("last_name", tg.last_name),
            ("username", tg.username),
        ):
            if value and getattr(user, attr) != value:
                setattr(user, attr, value)
                changed = True
        if changed:
            await db.flush()
    return user


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    authorization: str | None = Header(default=None),
    x_dev_telegram_id: str | None = Header(default=None, alias="X-Dev-Telegram-Id"),
) -> User:
    """Resolve the authenticated user from validated Telegram initData."""
    # --- DEV mode (never honored in production) ---
    if settings.effective_dev_auth() and x_dev_telegram_id:
        try:
            tg_id = int(x_dev_telegram_id)
        except ValueError as exc:
            raise UnauthorizedError("X-Dev-Telegram-Id must be an integer") from exc
        tg = TelegramUser(id=tg_id, first_name=f"Dev{tg_id}")
        user = await _resolve_telegram_user(tg, db)
        await db.commit()
        return user

    init_data = x_init_data
    if not init_data and authorization and authorization.lower().startswith("tma "):
        init_data = authorization[4:].strip()

    if not init_data:
        raise UnauthorizedError(
            "Missing Telegram initData", code="missing_init_data"
        )

    try:
        parsed = validate_init_data(
            init_data,
            settings.telegram_bot_token,
            max_age_seconds=settings.initdata_max_age_seconds,
        )
    except InitDataError as exc:
        raise UnauthorizedError(str(exc), code=exc.code) from exc

    user = await _resolve_telegram_user(parsed.user, db)
    await db.commit()
    return user


async def get_auth(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    x_club_id: str | None = Header(default=None, alias="X-Club-Id"),
) -> AuthContext:
    """Build an :class:`AuthContext`, resolving the active club membership.

    If ``X-Club-Id`` is absent, the context has no club (used by endpoints such
    as club creation and ``/clubs`` listing). If present, membership is verified.
    """
    ctx = AuthContext(user=user)
    if x_club_id is None:
        return ctx

    try:
        club_id = int(x_club_id)
    except ValueError as exc:
        raise ForbiddenError("Invalid X-Club-Id", code="invalid_club") from exc

    membership = (
        await db.execute(
            select(ClubMembership).where(
                ClubMembership.club_id == club_id,
                ClubMembership.user_id == user.id,
                ClubMembership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()

    if membership is None and not user.is_platform_admin:
        # Do not leak whether the club exists — same error for both.
        raise ForbiddenError("No access to this club", code="club_access_denied")

    club = (await db.execute(select(Club).where(Club.id == club_id))).scalar_one_or_none()
    if club is None:
        raise ForbiddenError("No access to this club", code="club_access_denied")

    ctx.club = club
    ctx.membership = membership
    return ctx


def require_club(ctx: AuthContext) -> AuthContext:
    if ctx.club is None:
        raise ForbiddenError("A club must be selected (X-Club-Id)", code="club_required")
    return ctx


class RequireRole:
    """Dependency factory enforcing a minimum role within the active club."""

    def __init__(self, minimum: Role) -> None:
        self.minimum = minimum

    def __call__(self, ctx: AuthContext = Depends(get_auth)) -> AuthContext:
        require_club(ctx)
        if ctx.user.is_platform_admin:
            return ctx
        if ctx.role is None:
            raise ForbiddenError("No role in this club", code="forbidden")
        if ROLE_WEIGHT.get(ctx.role, 0) < ROLE_WEIGHT[self.minimum.value]:
            raise ForbiddenError(
                f"Requires at least role '{self.minimum.value}'", code="insufficient_role"
            )
        return ctx


# Convenience singletons
require_trainer = RequireRole(Role.trainer)
require_admin = RequireRole(Role.club_admin)
require_owner = RequireRole(Role.club_owner)
