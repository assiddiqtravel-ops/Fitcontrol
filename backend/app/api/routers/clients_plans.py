"""Clients and Plans CRUD (club-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_admin, require_trainer
from app.core.enums import ClientStatus
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import Client, Plan
from app.schemas import (
    ClientCreate,
    ClientOut,
    ClientUpdate,
    Page,
    PlanCreate,
    PlanOut,
    PlanUpdate,
)
from app.services.audit import record_audit

router = APIRouter()


# --------------------------- Clients --------------------------- #
async def _get_client(db: AsyncSession, club_id: int, client_id: int) -> Client:
    client = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.club_id == club_id)
        )
    ).scalar_one_or_none()
    if client is None:
        raise NotFoundError("Client not found")
    return client


@router.get("/clients", response_model=Page[ClientOut], tags=["clients"])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    q: str | None = Query(default=None, description="Search name or phone"),
    status: ClientStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[ClientOut]:
    conditions = [Client.club_id == ctx.club_id]
    if status is not None:
        conditions.append(Client.status == status.value)
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                Client.first_name.ilike(like),
                Client.last_name.ilike(like),
                Client.phone.ilike(like),
            )
        )
    total = (
        await db.execute(select(func.count(Client.id)).where(*conditions))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Client)
            .where(*conditions)
            .order_by(Client.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return Page(
        items=[ClientOut.model_validate(c) for c in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post("/clients", response_model=ClientOut, status_code=201, tags=["clients"])
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> ClientOut:
    client = Client(club_id=ctx.club_id, **payload.model_dump())
    db.add(client)
    await db.flush()
    await record_audit(
        db,
        club_id=ctx.club_id,
        actor_user_id=ctx.user.id,
        action="client.create",
        entity_type="client",
        entity_id=client.id,
    )
    await db.commit()
    return ClientOut.model_validate(client)


@router.get("/clients/{client_id}", response_model=ClientOut, tags=["clients"])
async def get_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
) -> ClientOut:
    return ClientOut.model_validate(await _get_client(db, ctx.club_id, client_id))


@router.patch("/clients/{client_id}", response_model=ClientOut, tags=["clients"])
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> ClientOut:
    client = await _get_client(db, ctx.club_id, client_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await record_audit(
        db,
        club_id=ctx.club_id,
        actor_user_id=ctx.user.id,
        action="client.update",
        entity_type="client",
        entity_id=client.id,
    )
    await db.commit()
    await db.refresh(client)
    return ClientOut.model_validate(client)


@router.post("/clients/{client_id}/archive", response_model=ClientOut, tags=["clients"])
async def archive_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> ClientOut:
    """Archive instead of physical delete (protects against accidental loss)."""
    client = await _get_client(db, ctx.club_id, client_id)
    client.status = ClientStatus.archived.value
    await record_audit(
        db,
        club_id=ctx.club_id,
        actor_user_id=ctx.user.id,
        action="client.archive",
        entity_type="client",
        entity_id=client.id,
    )
    await db.commit()
    await db.refresh(client)
    return ClientOut.model_validate(client)


@router.post("/clients/{client_id}/restore", response_model=ClientOut, tags=["clients"])
async def restore_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> ClientOut:
    client = await _get_client(db, ctx.club_id, client_id)
    client.status = ClientStatus.active.value
    await db.commit()
    await db.refresh(client)
    return ClientOut.model_validate(client)


# --------------------------- Plans --------------------------- #
async def _get_plan(db: AsyncSession, club_id: int, plan_id: int) -> Plan:
    plan = (
        await db.execute(select(Plan).where(Plan.id == plan_id, Plan.club_id == club_id))
    ).scalar_one_or_none()
    if plan is None:
        raise NotFoundError("Plan not found")
    return plan


@router.get("/plans", response_model=list[PlanOut], tags=["plans"])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    active_only: bool = Query(default=False),
) -> list[PlanOut]:
    conditions = [Plan.club_id == ctx.club_id]
    if active_only:
        conditions.append(Plan.is_active.is_(True))
    rows = (
        await db.execute(select(Plan).where(*conditions).order_by(Plan.created_at.desc()))
    ).scalars().all()
    return [PlanOut.model_validate(p) for p in rows]


@router.post("/plans", response_model=PlanOut, status_code=201, tags=["plans"])
async def create_plan(
    payload: PlanCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> PlanOut:
    data = payload.model_dump()
    data["duration_unit"] = data["duration_unit"].value
    plan = Plan(club_id=ctx.club_id, **data)
    db.add(plan)
    await db.flush()
    await record_audit(
        db,
        club_id=ctx.club_id,
        actor_user_id=ctx.user.id,
        action="plan.create",
        entity_type="plan",
        entity_id=plan.id,
    )
    await db.commit()
    return PlanOut.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanOut, tags=["plans"])
async def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> PlanOut:
    plan = await _get_plan(db, ctx.club_id, plan_id)
    data = payload.model_dump(exclude_unset=True)
    if "duration_unit" in data and data["duration_unit"] is not None:
        data["duration_unit"] = data["duration_unit"].value
    for field, value in data.items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    return PlanOut.model_validate(plan)
