"""Financial journal: charges, payments, adjustments and debt calculation.

Balance model (all integer UZS). A positive balance means the client owes money::

    balance = total_charged
              - total_paid_effective        # payments NOT reversed
              - total_discount              # AdjustmentType.discount reduces owed
              + total_correction_signed     # AdjustmentType.correction (signed)

``debt = max(0, balance)`` and ``credit = max(0, -balance)``.

Reversal (refund/сторно): we mark the original Payment ``is_reversed=True`` (it
is never deleted) and write a ``FinancialAdjustment`` of type ``reversal`` with
author/time/reason. Because the reversed payment is excluded from
``total_paid_effective``, the balance moves back automatically — the reversal
row is the audit record, not a second balance mutation.

Future subscriptions are billed via a Charge dated when the subscription is
created; recognizing revenue is done by *payments*, so unpaid future sales never
count as received income (see reports).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AdjustmentType, PaymentMethod
from app.core.errors import ConflictError, NotFoundError, ValidationErrorApp
from app.models import Charge, Client, FinancialAdjustment, Payment
from app.services.audit import record_audit


@dataclass
class Ledger:
    total_charged: int
    total_paid: int
    total_discount: int
    total_correction: int
    balance: int

    @property
    def debt(self) -> int:
        return max(0, self.balance)

    @property
    def credit(self) -> int:
        return max(0, -self.balance)


async def _sum(db: AsyncSession, stmt) -> int:
    result = await db.execute(stmt)
    total = 0
    for row in result.scalars().all():
        total += int(row)
    return total


async def compute_ledger(db: AsyncSession, *, club_id: int, client_id: int) -> Ledger:
    charges = await db.execute(
        select(Charge.amount).where(Charge.club_id == club_id, Charge.client_id == client_id)
    )
    total_charged = sum(int(a) for a in charges.scalars().all())

    payments = await db.execute(
        select(Payment.amount).where(
            Payment.club_id == club_id,
            Payment.client_id == client_id,
            Payment.is_reversed.is_(False),
        )
    )
    total_paid = sum(int(a) for a in payments.scalars().all())

    discounts = await db.execute(
        select(FinancialAdjustment.amount).where(
            FinancialAdjustment.club_id == club_id,
            FinancialAdjustment.client_id == client_id,
            FinancialAdjustment.type == AdjustmentType.discount.value,
        )
    )
    total_discount = sum(int(a) for a in discounts.scalars().all())

    corrections = await db.execute(
        select(FinancialAdjustment.amount).where(
            FinancialAdjustment.club_id == club_id,
            FinancialAdjustment.client_id == client_id,
            FinancialAdjustment.type == AdjustmentType.correction.value,
        )
    )
    total_correction = sum(int(a) for a in corrections.scalars().all())

    balance = total_charged - total_paid - total_discount + total_correction
    return Ledger(
        total_charged=total_charged,
        total_paid=total_paid,
        total_discount=total_discount,
        total_correction=total_correction,
        balance=balance,
    )


async def create_charge(
    db: AsyncSession,
    *,
    club_id: int,
    client_id: int,
    amount: int,
    description: str | None,
    subscription_id: int | None,
    actor_user_id: int | None,
) -> Charge:
    if amount <= 0:
        raise ValidationErrorApp("Charge amount must be greater than 0")
    charge = Charge(
        club_id=club_id,
        client_id=client_id,
        subscription_id=subscription_id,
        amount=amount,
        description=description,
        created_by=actor_user_id,
    )
    db.add(charge)
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="charge.create",
        entity_type="charge",
        entity_id=charge.id,
        meta={"amount": amount, "client_id": client_id},
    )
    return charge


async def create_payment(
    db: AsyncSession,
    *,
    club_id: int,
    client_id: int,
    amount: int,
    method: str,
    received_by: int | None,
    comment: str | None = None,
    charge_id: int | None = None,
    subscription_id: int | None = None,
    paid_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> tuple[Payment, bool]:
    """Create a payment. Returns ``(payment, created)``.

    If an ``idempotency_key`` was already used for this club, the existing
    payment is returned with ``created=False`` (safe retry).
    """
    if amount <= 0:
        raise ValidationErrorApp("Payment amount must be greater than 0")
    if method not in {m.value for m in PaymentMethod}:
        raise ValidationErrorApp(f"Unknown payment method: {method}")

    client = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.club_id == club_id)
        )
    ).scalar_one_or_none()
    if client is None:
        raise NotFoundError("Client not found")

    if idempotency_key:
        existing = (
            await db.execute(
                select(Payment).where(
                    Payment.club_id == club_id,
                    Payment.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    payment = Payment(
        club_id=club_id,
        client_id=client_id,
        charge_id=charge_id,
        subscription_id=subscription_id,
        amount=amount,
        method=method,
        comment=comment,
        received_by=received_by,
        paid_at=paid_at or datetime.now(timezone.utc),
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError:
        # Concurrent request with the same idempotency key won the race.
        await db.rollback()
        existing = (
            await db.execute(
                select(Payment).where(
                    Payment.club_id == club_id,
                    Payment.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        raise

    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=received_by,
        action="payment.create",
        entity_type="payment",
        entity_id=payment.id,
        meta={"amount": amount, "method": method, "client_id": client_id},
    )
    return payment, True


async def reverse_payment(
    db: AsyncSession,
    *,
    club_id: int,
    payment_id: int,
    reason: str,
    actor_user_id: int | None,
) -> FinancialAdjustment:
    """Reverse (refund/сторно) a payment. The payment row is preserved."""
    if not reason or not reason.strip():
        raise ValidationErrorApp("A reason is required for a reversal")
    payment = (
        await db.execute(
            select(Payment).where(Payment.id == payment_id, Payment.club_id == club_id)
        )
    ).scalar_one_or_none()
    if payment is None:
        raise NotFoundError("Payment not found")
    if payment.is_reversed:
        raise ConflictError("Payment is already reversed")

    payment.is_reversed = True
    adj = FinancialAdjustment(
        club_id=club_id,
        client_id=payment.client_id,
        charge_id=payment.charge_id,
        payment_id=payment.id,
        type=AdjustmentType.reversal.value,
        amount=payment.amount,
        reason=reason.strip(),
        created_by=actor_user_id,
    )
    db.add(adj)
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action="payment.reverse",
        entity_type="payment",
        entity_id=payment.id,
        meta={"amount": payment.amount, "reason": reason.strip()},
    )
    return adj


async def create_adjustment(
    db: AsyncSession,
    *,
    club_id: int,
    client_id: int,
    adj_type: str,
    amount: int,
    reason: str,
    actor_user_id: int | None,
    charge_id: int | None = None,
) -> FinancialAdjustment:
    """Create a discount or a (signed) correction. Reversals use reverse_payment."""
    if adj_type not in {AdjustmentType.discount.value, AdjustmentType.correction.value}:
        raise ValidationErrorApp("adjustment type must be 'discount' or 'correction'")
    if not reason or not reason.strip():
        raise ValidationErrorApp("A reason is required for an adjustment")
    if adj_type == AdjustmentType.discount.value and amount <= 0:
        raise ValidationErrorApp("Discount amount must be greater than 0")
    if amount == 0:
        raise ValidationErrorApp("Adjustment amount cannot be 0")

    adj = FinancialAdjustment(
        club_id=club_id,
        client_id=client_id,
        charge_id=charge_id,
        type=adj_type,
        amount=amount,
        reason=reason.strip(),
        created_by=actor_user_id,
    )
    db.add(adj)
    await db.flush()
    await record_audit(
        db,
        club_id=club_id,
        actor_user_id=actor_user_id,
        action=f"adjustment.{adj_type}",
        entity_type="financial_adjustment",
        entity_id=adj.id,
        meta={"amount": amount, "client_id": client_id, "reason": reason.strip()},
    )
    return adj
