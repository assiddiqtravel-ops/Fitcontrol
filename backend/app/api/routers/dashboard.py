"""Dashboard and financial reports."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_trainer
from app.core.enums import PaymentMethod
from app.core.errors import ValidationErrorApp
from app.db.session import get_db
from app.schemas import (
    DashboardOut,
    IncomeByMethod,
    ReportIncomeOut,
)
from app.services import reports as reports_svc

router = APIRouter()


def _resolve_period(
    period: str, start: date | None, end: date | None, today: date
) -> tuple[date, date]:
    if period == "today":
        return today, today
    if period == "7d":
        return today - timedelta(days=6), today
    if period == "month":
        return today.replace(day=1), today
    if period == "custom":
        if start is None or end is None:
            raise ValidationErrorApp("custom period requires start and end")
        if end < start:
            raise ValidationErrorApp("end date is before start date")
        return start, end
    raise ValidationErrorApp("period must be one of: today, 7d, month, custom")


@router.get("/dashboard", response_model=DashboardOut, tags=["dashboard"])
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    period: str = Query(default="month"),
    start: date | None = None,
    end: date | None = None,
) -> DashboardOut:
    today = date.today()
    p_start, p_end = _resolve_period(period, start, end, today)
    data = await reports_svc.dashboard(
        db, club_id=ctx.club_id, start=p_start, end=p_end, today=today
    )
    return DashboardOut(**data)


@router.get("/reports/income", response_model=ReportIncomeOut, tags=["reports"])
async def report_income(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_trainer),
    period: str = Query(default="month"),
    start: date | None = None,
    end: date | None = None,
) -> ReportIncomeOut:
    today = date.today()
    p_start, p_end = _resolve_period(period, start, end, today)
    total_income = await reports_svc.income_in_period(
        db, club_id=ctx.club_id, start=p_start, end=p_end
    )
    total_refunds = await reports_svc.refunds_in_period(
        db, club_id=ctx.club_id, start=p_start, end=p_end
    )
    by_method_rows = await reports_svc.income_by_method(
        db, club_id=ctx.club_id, start=p_start, end=p_end
    )
    return ReportIncomeOut(
        period_start=p_start,
        period_end=p_end,
        total_income=total_income,
        total_refunds=total_refunds,
        net_income=total_income - total_refunds,
        by_method=[
            IncomeByMethod(method=PaymentMethod(m), total=t, count=c)
            for m, t, c in by_method_rows
        ],
    )
