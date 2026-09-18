"""Payments, financial adjustments and debt endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_admin, require_trainer
from app.db.session import get_db
from app.models import Payment
from app.schemas import (
    AdjustmentCreate,
    AdjustmentOut,
    DebtRow,
    LedgerOut,
    PaymentCreate,
    PaymentOut,
    PaymentReverseIn,
)
from app.services import billing as billing_svc
from app.services import reports as reports_svc

router = APIRouter()


@router.get("/payments", response_model=list[PaymentOut], tags=["payments"])
async def list_payments(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    client_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PaymentOut]:
    conditions = [Payment.club_id == ctx.club_id]
    if client_id is not None:
        conditions.append(Payment.client_id == client_id)
    rows = (
        await db.execute(
            select(Payment)
            .where(*conditions)
            .order_by(Payment.paid_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return [PaymentOut.model_validate(p) for p in rows]


@router.post("/payments", response_model=PaymentOut, tags=["payments"])
async def create_payment(
    payload: PaymentCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PaymentOut:
    """Record a payment. Supply an ``Idempotency-Key`` header to make retries safe.

    Returns 201 when a new payment is created, 200 when an existing payment is
    returned for a repeated idempotency key.
    """
    payment, created = await billing_svc.create_payment(
        db,
        club_id=ctx.club_id,
        client_id=payload.client_id,
        amount=payload.amount,
        method=payload.method.value,
        comment=payload.comment,
        received_by=ctx.user.id,
        charge_id=payload.charge_id,
        subscription_id=payload.subscription_id,
        paid_at=payload.paid_at,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    response.status_code = 201 if created else 200
    return PaymentOut.model_validate(payment)


@router.post(
    "/payments/{payment_id}/reverse", response_model=AdjustmentOut, tags=["payments"]
)
async def reverse_payment(
    payment_id: int,
    payload: PaymentReverseIn,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> AdjustmentOut:
    adj = await billing_svc.reverse_payment(
        db,
        club_id=ctx.club_id,
        payment_id=payment_id,
        reason=payload.reason,
        actor_user_id=ctx.user.id,
    )
    await db.commit()
    return AdjustmentOut.model_validate(adj)


@router.post("/adjustments", response_model=AdjustmentOut, status_code=201, tags=["payments"])
async def create_adjustment(
    payload: AdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> AdjustmentOut:
    adj = await billing_svc.create_adjustment(
        db,
        club_id=ctx.club_id,
        client_id=payload.client_id,
        adj_type=payload.type.value,
        amount=payload.amount,
        reason=payload.reason,
        actor_user_id=ctx.user.id,
        charge_id=payload.charge_id,
    )
    await db.commit()
    return AdjustmentOut.model_validate(adj)


@router.get("/clients/{client_id}/ledger", response_model=LedgerOut, tags=["debts"])
async def client_ledger(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
) -> LedgerOut:
    ledger = await billing_svc.compute_ledger(
        db, club_id=ctx.club_id, client_id=client_id
    )
    return LedgerOut(
        client_id=client_id,
        total_charged=ledger.total_charged,
        total_paid=ledger.total_paid,
        total_discount=ledger.total_discount,
        total_correction=ledger.total_correction,
        balance=ledger.balance,
        debt=ledger.debt,
        credit=ledger.credit,
    )


@router.get("/debts", response_model=list[DebtRow], tags=["debts"])
async def list_debts(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
) -> list[DebtRow]:
    debtors = await reports_svc.clients_with_debt(db, club_id=ctx.club_id)
    return [
        DebtRow(client_id=cid, client_name=name, debt=debt) for cid, name, debt in debtors
    ]
