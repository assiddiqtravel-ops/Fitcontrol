"""Attendance endpoints."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_trainer
from app.db.session import get_db
from app.models import Visit
from app.schemas import VisitCreate, VisitEligibilityOut, VisitOut
from app.services import visits as visit_svc

router = APIRouter()


@router.get(
    "/clients/{client_id}/visit-eligibility",
    response_model=VisitEligibilityOut,
    tags=["visits"],
)
async def eligibility(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
) -> VisitEligibilityOut:
    elig = await visit_svc.check_eligibility(
        db, club_id=ctx.club_id, client_id=client_id
    )
    return VisitEligibilityOut(
        allowed=elig.allowed,
        reason=elig.reason,
        subscription_id=elig.subscription_id,
        status=elig.status,
        visits_left=elig.visits_left,
    )


@router.post("/visits", response_model=VisitOut, status_code=201, tags=["visits"])
async def register_visit(
    payload: VisitCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
) -> VisitOut:
    visit = await visit_svc.register_visit(
        db,
        club_id=ctx.club_id,
        client_id=payload.client_id,
        actor_user_id=ctx.user.id,
        note=payload.note,
        override_reason=payload.override_reason,
    )
    await db.commit()
    return VisitOut.model_validate(visit)


@router.get("/visits", response_model=list[VisitOut], tags=["visits"])
async def list_visits(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    client_id: int | None = Query(default=None),
    day: date | None = Query(default=None, description="Filter by a single date (UTC)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[VisitOut]:
    conditions = [Visit.club_id == ctx.club_id]
    if client_id is not None:
        conditions.append(Visit.client_id == client_id)
    if day is not None:
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        conditions.append(Visit.created_at >= start)
        conditions.append(Visit.created_at <= end)
    rows = (
        await db.execute(
            select(Visit)
            .where(*conditions)
            .order_by(Visit.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [VisitOut.model_validate(v) for v in rows]
