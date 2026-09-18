"""Pydantic request/response schemas.

All money fields are integer UZS. Amounts are validated ``> 0`` where a positive
value is required. Generic list responses carry pagination metadata.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AdjustmentType,
    ClientStatus,
    DurationUnit,
    PaymentMethod,
    Role,
)

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# --- Auth / clubs ---
class UserOut(ORMModel):
    id: int
    telegram_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language: str
    is_platform_admin: bool


class ClubOut(ORMModel):
    id: int
    name: str
    timezone: str
    currency: str
    default_language: str
    is_active: bool
    notify_expiry_enabled: bool
    notify_overdue_enabled: bool
    notify_daily_summary_enabled: bool
    expiry_reminder_days: int
    created_at: datetime


class ClubCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="Asia/Tashkent", max_length=64)
    default_language: str = Field(default="ru", max_length=8)


class ClubSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    default_language: str | None = Field(default=None, max_length=8)
    notify_expiry_enabled: bool | None = None
    notify_overdue_enabled: bool | None = None
    notify_daily_summary_enabled: bool | None = None
    expiry_reminder_days: int | None = Field(default=None, ge=0, le=60)


class ClubMembershipOut(BaseModel):
    club: ClubOut
    role: Role


class AuthMe(BaseModel):
    user: UserOut
    clubs: list[ClubMembershipOut]


# --- Clients ---
class ClientBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    note: str | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    note: str | None = None


class ClientOut(ORMModel):
    id: int
    first_name: str
    last_name: str | None = None
    phone: str | None = None
    birth_date: date | None = None
    note: str | None = None
    status: ClientStatus
    created_at: datetime


# --- Plans ---
class PlanBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: int = Field(ge=0, description="Integer UZS")
    duration_value: int = Field(gt=0)
    duration_unit: DurationUnit
    visit_limit: int | None = Field(default=None, gt=0)
    description: str | None = None
    is_active: bool = True


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: int | None = Field(default=None, ge=0)
    duration_value: int | None = Field(default=None, gt=0)
    duration_unit: DurationUnit | None = None
    visit_limit: int | None = Field(default=None, gt=0)
    description: str | None = None
    is_active: bool | None = None


class PlanOut(ORMModel):
    id: int
    name: str
    price: int
    duration_value: int
    duration_unit: DurationUnit
    visit_limit: int | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime


# --- Subscriptions ---
class SubscriptionCreate(BaseModel):
    client_id: int
    plan_id: int
    start_date: date
    create_charge: bool = True


class SubscriptionFreezeIn(BaseModel):
    start_date: date


class SubscriptionUnfreezeIn(BaseModel):
    end_date: date


class SubscriptionCancelIn(BaseModel):
    reason: str | None = None


class SubscriptionOut(ORMModel):
    id: int
    client_id: int
    plan_id: int
    start_date: date
    end_date: date
    status: str
    visit_limit: int | None = None
    visits_used: int
    price: int
    frozen_days: int
    created_at: datetime


# --- Payments / debts ---
class PaymentCreate(BaseModel):
    client_id: int
    amount: int = Field(gt=0, description="Integer UZS, > 0")
    method: PaymentMethod = PaymentMethod.cash
    comment: str | None = None
    charge_id: int | None = None
    subscription_id: int | None = None
    paid_at: datetime | None = None


class PaymentOut(ORMModel):
    id: int
    client_id: int
    charge_id: int | None = None
    subscription_id: int | None = None
    amount: int
    method: PaymentMethod
    comment: str | None = None
    paid_at: datetime
    received_by: int | None = None
    is_reversed: bool
    created_at: datetime


class PaymentReverseIn(BaseModel):
    reason: str = Field(min_length=1)


class AdjustmentCreate(BaseModel):
    client_id: int
    type: AdjustmentType
    amount: int = Field(description="Integer UZS; discount>0, correction signed")
    reason: str = Field(min_length=1)
    charge_id: int | None = None


class AdjustmentOut(ORMModel):
    id: int
    client_id: int
    charge_id: int | None = None
    payment_id: int | None = None
    type: AdjustmentType
    amount: int
    reason: str
    created_by: int | None = None
    created_at: datetime


class LedgerOut(BaseModel):
    client_id: int
    total_charged: int
    total_paid: int
    total_discount: int
    total_correction: int
    balance: int
    debt: int
    credit: int


class DebtRow(BaseModel):
    client_id: int
    client_name: str
    debt: int


# --- Visits ---
class VisitCreate(BaseModel):
    client_id: int
    note: str | None = None
    override_reason: str | None = None


class VisitEligibilityOut(BaseModel):
    allowed: bool
    reason: str
    subscription_id: int | None = None
    status: str | None = None
    visits_left: int | None = None


class VisitOut(ORMModel):
    id: int
    client_id: int
    subscription_id: int | None = None
    result: str
    override_reason: str | None = None
    note: str | None = None
    recorded_by: int | None = None
    created_at: datetime


# --- Staff / invites ---
class InviteCreate(BaseModel):
    role: Role
    telegram_id: int | None = None
    ttl_hours: int = Field(default=72, gt=0, le=720)


class InviteOut(ORMModel):
    id: int
    code: str
    role: Role
    telegram_id: int | None = None
    status: str
    expires_at: datetime
    created_at: datetime


class InviteAcceptIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class StaffOut(BaseModel):
    membership_id: int
    user: UserOut
    role: Role
    is_active: bool


class StaffSetActiveIn(BaseModel):
    is_active: bool


# --- Dashboard / reports ---
class DashboardOut(BaseModel):
    active_clients: int
    visits_today: int
    subscriptions_ending_soon: int
    clients_with_debt: int
    total_debt: int
    income_in_period: int
    period_start: date
    period_end: date


class IncomeByMethod(BaseModel):
    method: PaymentMethod
    total: int
    count: int


class ReportIncomeOut(BaseModel):
    period_start: date
    period_end: date
    total_income: int
    total_refunds: int
    net_income: int
    by_method: list[IncomeByMethod]
