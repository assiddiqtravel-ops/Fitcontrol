"""Auth, club creation/selection and staff endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth, get_current_user, require_admin, require_owner
from app.core.enums import Role
from app.db.session import get_db
from app.models import ClubMembership, User
from app.schemas import (
    AuthMe,
    ClubCreate,
    ClubMembershipOut,
    ClubOut,
    ClubSettingsUpdate,
    InviteAcceptIn,
    InviteCreate,
    InviteOut,
    StaffOut,
    StaffSetActiveIn,
    UserOut,
)
from app.services import clubs as clubs_svc

router = APIRouter()


@router.get("/auth/me", response_model=AuthMe, tags=["auth"])
async def auth_me(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AuthMe:
    """Return the authenticated user and the clubs they belong to."""
    pairs = await clubs_svc.list_user_clubs(db, user)
    return AuthMe(
        user=UserOut.model_validate(user),
        clubs=[
            ClubMembershipOut(club=ClubOut.model_validate(c), role=Role(r))
            for c, r in pairs
        ],
    )


@router.post("/clubs", response_model=ClubOut, status_code=201, tags=["clubs"])
async def create_club(
    payload: ClubCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClubOut:
    club = await clubs_svc.create_club(
        db,
        owner=user,
        name=payload.name,
        timezone_name=payload.timezone,
        default_language=payload.default_language,
    )
    await db.commit()
    return ClubOut.model_validate(club)


@router.get("/clubs", response_model=list[ClubMembershipOut], tags=["clubs"])
async def list_clubs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ClubMembershipOut]:
    pairs = await clubs_svc.list_user_clubs(db, user)
    return [
        ClubMembershipOut(club=ClubOut.model_validate(c), role=Role(r)) for c, r in pairs
    ]


@router.get("/clubs/current", response_model=ClubOut, tags=["clubs"])
async def current_club(ctx: AuthContext = Depends(require_admin)) -> ClubOut:
    return ClubOut.model_validate(ctx.club)


@router.patch("/settings", response_model=ClubOut, tags=["settings"])
async def update_settings(
    payload: ClubSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_owner),
) -> ClubOut:
    club = ctx.club
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(club, field, value)
    await db.commit()
    await db.refresh(club)
    return ClubOut.model_validate(club)


# --- Invitations & staff ---
@router.post("/staff/invites", response_model=InviteOut, status_code=201, tags=["staff"])
async def create_invite(
    payload: InviteCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> InviteOut:
    invite = await clubs_svc.create_invite(
        db,
        club_id=ctx.club_id,
        role=payload.role.value,
        telegram_id=payload.telegram_id,
        ttl_hours=payload.ttl_hours,
        actor_user_id=ctx.user.id,
    )
    await db.commit()
    return InviteOut.model_validate(invite)


@router.post("/staff/invites/accept", response_model=ClubMembershipOut, tags=["staff"])
async def accept_invite(
    payload: InviteAcceptIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClubMembershipOut:
    membership = await clubs_svc.accept_invite(db, code=payload.code, user=user)
    await db.commit()
    # Re-fetch the club for the response.
    from app.models import Club

    club_row = (
        await db.execute(select(Club).where(Club.id == membership.club_id))
    ).scalar_one()
    return ClubMembershipOut(
        club=ClubOut.model_validate(club_row), role=Role(membership.role)
    )


@router.get("/staff", response_model=list[StaffOut], tags=["staff"])
async def list_staff(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> list[StaffOut]:
    rows = (
        await db.execute(
            select(ClubMembership, User)
            .join(User, User.id == ClubMembership.user_id)
            .where(ClubMembership.club_id == ctx.club_id)
            .order_by(ClubMembership.created_at.asc())
        )
    ).all()
    return [
        StaffOut(
            membership_id=m.id,
            user=UserOut.model_validate(u),
            role=Role(m.role),
            is_active=m.is_active,
        )
        for m, u in rows
    ]


@router.patch("/staff/{membership_id}", response_model=StaffOut, tags=["staff"])
async def set_staff_active(
    membership_id: int,
    payload: StaffSetActiveIn,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_owner),
) -> StaffOut:
    membership = await clubs_svc.set_membership_active(
        db,
        club_id=ctx.club_id,
        membership_id=membership_id,
        is_active=payload.is_active,
        actor_user_id=ctx.user.id,
    )
    user = (
        await db.execute(select(User).where(User.id == membership.user_id))
    ).scalar_one()
    await db.commit()
    return StaffOut(
        membership_id=membership.id,
        user=UserOut.model_validate(user),
        role=Role(membership.role),
        is_active=membership.is_active,
    )
