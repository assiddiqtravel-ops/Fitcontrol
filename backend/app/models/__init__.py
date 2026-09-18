"""SQLAlchemy models for FitControl.

Tenant isolation: every club-scoped table carries a ``club_id`` FK. All queries
in the service layer filter by ``club_id`` taken from the authenticated
membership; buttons are never the security boundary.

Money: integer UZS (see app.core.money).
Financial journal: Charge (начисление), Payment (оплата) and
FinancialAdjustment (скидка/сторно/коррекция) are append-only. Payments are
never physically deleted; corrections are new signed rows with an author,
timestamp and reason.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AdjustmentType,
    ClientStatus,
    DurationUnit,
    InviteStatus,
    PaymentMethod,
    Role,
    SubscriptionStatus,
    VisitResult,
)
from app.db.base import Base, PKMixin, TimestampMixin


# --------------------------------------------------------------------------- #
# Identity & tenancy
# --------------------------------------------------------------------------- #
class User(PKMixin, TimestampMixin, Base):
    """A Telegram user. Global (not club-scoped); links to clubs via membership."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships: Mapped[list["ClubMembership"]] = relationship(back_populates="user")


class Club(PKMixin, TimestampMixin, Base):
    __tablename__ = "clubs"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tashkent", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    default_language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Notification preferences (JSON-ish flat columns keep the MVP simple)
    notify_expiry_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_overdue_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_daily_summary_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    expiry_reminder_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Out-of-band recovery contacts. Support verifies these BEFORE restoring
    # access to a new Telegram account, so a Telegram ID is never the only way
    # to recover a club. Never used for authentication, only identity checks.
    recovery_email: Mapped[str | None] = mapped_column(String(200))
    recovery_phone: Mapped[str | None] = mapped_column(String(32))

    memberships: Mapped[list["ClubMembership"]] = relationship(back_populates="club")


class ClubMembership(PKMixin, TimestampMixin, Base):
    """Association of a user with a club and a role. The RBAC anchor."""

    __tablename__ = "club_memberships"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="uq_membership_club_user"),
        Index("ix_membership_club", "club_id"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default=Role.trainer.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    club: Mapped["Club"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class StaffInvite(PKMixin, TimestampMixin, Base):
    """One-time invite: by Telegram ID or by short code, with an expiry."""

    __tablename__ = "staff_invites"
    __table_args__ = (
        UniqueConstraint("code", name="uq_invite_code"),
        Index("ix_invite_club", "club_id"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=Role.trainer.value, nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=InviteStatus.pending.value, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
class Client(PKMixin, TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_client_club", "club_id"),
        Index("ix_client_club_status", "club_id", "status"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default=ClientStatus.active.value, nullable=False
    )


# --------------------------------------------------------------------------- #
# Plans & subscriptions
# --------------------------------------------------------------------------- #
class Plan(PKMixin, TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (Index("ix_plan_club", "club_id"),)

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)  # integer UZS
    duration_value: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(8), nullable=False)  # days|months
    visit_limit: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Subscription(PKMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_sub_club", "club_id"),
        Index("ix_sub_client", "club_id", "client_id"),
        Index("ix_sub_status", "club_id", "status"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=SubscriptionStatus.active.value, nullable=False
    )
    visit_limit: Mapped[int | None] = mapped_column(Integer)  # snapshot from plan
    visits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)  # snapshot; integer UZS
    # Total frozen days accumulated (for reference / auditing).
    frozen_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_reason: Mapped[str | None] = mapped_column(Text)


class SubscriptionFreeze(PKMixin, TimestampMixin, Base):
    __tablename__ = "subscription_freezes"
    __table_args__ = (Index("ix_freeze_sub", "subscription_id"),)

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)  # None = still frozen
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )


# --------------------------------------------------------------------------- #
# Financial journal
# --------------------------------------------------------------------------- #
class Charge(PKMixin, TimestampMixin, Base):
    """A billable line (начисление) — e.g. the cost of a subscription."""

    __tablename__ = "charges"
    __table_args__ = (
        Index("ix_charge_club", "club_id"),
        Index("ix_charge_client", "club_id", "client_id"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # integer UZS, > 0
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )


class Payment(PKMixin, TimestampMixin, Base):
    """A received payment. Append-only; never physically deleted."""

    __tablename__ = "payments"
    __table_args__ = (
        # Idempotency: a client-supplied key is unique per club so a retried
        # request cannot create a duplicate payment.
        UniqueConstraint("club_id", "idempotency_key", name="uq_payment_idempotency"),
        Index("ix_payment_club", "club_id"),
        Index("ix_payment_client", "club_id", "client_id"),
        Index("ix_payment_created", "club_id", "created_at"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    charge_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("charges.id", ondelete="SET NULL")
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # integer UZS, > 0
    method: Mapped[str] = mapped_column(
        String(16), default=PaymentMethod.cash.value, nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    received_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    # Nullable: only set when the caller provides an Idempotency-Key.
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    # True once reversed by an adjustment (kept for auditability; row stays).
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FinancialAdjustment(PKMixin, TimestampMixin, Base):
    """Signed correction to the ledger: discount, reversal/refund, correction.

    ``amount`` semantics (all integer UZS):
      - discount:   positive value that REDUCES the amount owed
      - reversal:   positive value that REVERSES a prior payment (refund)
      - correction: signed value applied per ``reason``
    Never deletes anything; always records author, time and reason.
    """

    __tablename__ = "financial_adjustments"
    __table_args__ = (
        Index("ix_adj_club", "club_id"),
        Index("ix_adj_client", "club_id", "client_id"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    charge_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("charges.id", ondelete="SET NULL")
    )
    payment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("payments.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # AdjustmentType
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # integer UZS
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )


# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #
class Visit(PKMixin, TimestampMixin, Base):
    __tablename__ = "visits"
    __table_args__ = (
        Index("ix_visit_club", "club_id"),
        Index("ix_visit_client", "club_id", "client_id"),
        Index("ix_visit_created", "club_id", "created_at"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    result: Mapped[str] = mapped_column(
        String(16), default=VisitResult.allowed.value, nullable=False
    )
    override_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )


# --------------------------------------------------------------------------- #
# Notifications & audit
# --------------------------------------------------------------------------- #
class NotificationLog(PKMixin, TimestampMixin, Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        UniqueConstraint("club_id", "dedup_key", name="uq_notification_dedup"),
        Index("ix_notiflog_club", "club_id"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # expiry|overdue|daily_summary
    target_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    dedup_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="sent", nullable=False)
    payload: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class AuditLog(PKMixin, TimestampMixin, Base):
    """Append-only audit trail for financial & administrative actions."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_club", "club_id"),
        Index("ix_audit_entity", "club_id", "entity_type", "entity_id"),
    )

    club_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    meta: Mapped[str | None] = mapped_column(Text)  # JSON string (no secrets)


__all__ = [
    "User",
    "Club",
    "ClubMembership",
    "StaffInvite",
    "Client",
    "Plan",
    "Subscription",
    "SubscriptionFreeze",
    "Charge",
    "Payment",
    "FinancialAdjustment",
    "Visit",
    "NotificationLog",
    "AuditLog",
]
