"""Domain enumerations shared across models, schemas and services."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    """Roles a user can hold within a single club (membership-scoped)."""

    platform_admin = "platform_admin"  # SaaS owner; cross-club (handled separately)
    club_owner = "club_owner"
    club_admin = "club_admin"
    trainer = "trainer"


# Role hierarchy weight for simple "at least" comparisons within a club.
ROLE_WEIGHT: dict[str, int] = {
    Role.trainer.value: 10,
    Role.club_admin.value: 20,
    Role.club_owner.value: 30,
    Role.platform_admin.value: 100,
}


class ClientStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class SubscriptionStatus(str, enum.Enum):
    upcoming = "upcoming"
    active = "active"
    frozen = "frozen"
    expired = "expired"
    cancelled = "cancelled"


class DurationUnit(str, enum.Enum):
    days = "days"
    months = "months"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    card = "card"
    transfer = "transfer"
    other = "other"


class AdjustmentType(str, enum.Enum):
    discount = "discount"       # reduces amount owed
    reversal = "reversal"       # reverses a prior payment (refund/сторно)
    correction = "correction"   # generic signed correction with reason


class InviteStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class VisitResult(str, enum.Enum):
    allowed = "allowed"
    override = "override"  # allowed via explicit staff exception with reason
