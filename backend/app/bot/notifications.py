"""Background notification jobs (expiry reminders, overdue debts, daily summary).

Design & safety:
  * Recipients are ONLY club staff (club_admin and above). Client-facing
    messages are out of scope for the MVP and require explicit opt-in.
  * Each send is de-duplicated via ``NotificationLog(club_id, dedup_key)`` — a
    unique constraint guarantees we never send the same reminder twice, even if
    the loop restarts.
  * Failures are caught and logged (never crash the loop); a failed row is
    recorded with status="error".
  * The daily summary respects each club's IANA timezone and the configured
    ``daily_summary_hour``.

Run standalone: ``python -m app.bot.notifications`` (loops every 60s) or import
:func:`run_due_jobs` to trigger once from another scheduler (cron/systemd).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ROLE_WEIGHT, Role
from app.core.money import format_uzs
from app.db.session import get_sessionmaker
from app.models import Club, ClubMembership, NotificationLog, User
from app.services import reports as reports_svc

logger = logging.getLogger("fitcontrol.notifications")


class Sender:
    """Abstract message sink. The real implementation wraps an aiogram Bot;
    tests can pass a fake to capture messages without network calls."""

    async def send(self, telegram_id: int, text: str) -> None:  # pragma: no cover
        raise NotImplementedError


class LoggingSender(Sender):
    """Fallback sink used when no bot token is configured (dev/testing)."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, telegram_id: int, text: str) -> None:
        self.sent.append((telegram_id, text))
        logger.info("[notify -> %s] %s", telegram_id, text.replace("\n", " | "))


async def _staff_recipients(db: AsyncSession, club_id: int) -> list[int]:
    rows = (
        await db.execute(
            select(User.telegram_id, ClubMembership.role)
            .join(ClubMembership, ClubMembership.user_id == User.id)
            .where(ClubMembership.club_id == club_id, ClubMembership.is_active.is_(True))
        )
    ).all()
    return [
        tg
        for tg, role in rows
        if ROLE_WEIGHT.get(role, 0) >= ROLE_WEIGHT[Role.club_admin.value]
    ]


async def _record_and_send(
    db: AsyncSession,
    sender: Sender,
    *,
    club_id: int,
    kind: str,
    dedup_key: str,
    telegram_id: int,
    text: str,
) -> bool:
    """Insert a dedup row then send. Returns True if actually sent.

    The unique (club_id, dedup_key) constraint prevents duplicates: if the row
    already exists we skip silently.
    """
    log = NotificationLog(
        club_id=club_id,
        kind=kind,
        target_telegram_id=telegram_id,
        dedup_key=dedup_key,
        status="pending",
    )
    db.add(log)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False  # already sent

    try:
        await sender.send(telegram_id, text)
        log.status = "sent"
    except Exception as exc:  # noqa: BLE001 - never crash the loop
        log.status = "error"
        log.error = str(exc)[:500]
        logger.warning("Notification send failed for club %s: %s", club_id, exc)
    await db.commit()
    return log.status == "sent"


async def run_expiry_reminders(db: AsyncSession, sender: Sender, club: Club, today: date) -> int:
    if not club.notify_expiry_enabled:
        return 0
    subs = await reports_svc.ending_soon_subscriptions(
        db, club_id=club.id, within_days=club.expiry_reminder_days, today=today
    )
    if not subs:
        return 0
    recipients = await _staff_recipients(db, club.id)
    count = 0
    lines = [f"• client #{s.client_id} — до {s.end_date.isoformat()}" for s in subs]
    text = f"⏳ {club.name}: заканчиваются абонементы\n" + "\n".join(lines)
    for tg in recipients:
        # dedup per staff per day so the reminder is sent at most once daily.
        key = f"expiry:{today.isoformat()}:{tg}"
        if await _record_and_send(
            db, sender, club_id=club.id, kind="expiry", dedup_key=key,
            telegram_id=tg, text=text,
        ):
            count += 1
    return count


async def run_overdue_reminders(db: AsyncSession, sender: Sender, club: Club, today: date) -> int:
    if not club.notify_overdue_enabled:
        return 0
    debtors = await reports_svc.clients_with_debt(db, club_id=club.id)
    if not debtors:
        return 0
    recipients = await _staff_recipients(db, club.id)
    total = sum(d[2] for d in debtors)
    lines = [f"• {name} — {format_uzs(debt)}" for _cid, name, debt in debtors[:10]]
    text = (
        f"❗ {club.name}: должники ({len(debtors)}), всего {format_uzs(total)}\n"
        + "\n".join(lines)
    )
    count = 0
    for tg in recipients:
        key = f"overdue:{today.isoformat()}:{tg}"
        if await _record_and_send(
            db, sender, club_id=club.id, kind="overdue", dedup_key=key,
            telegram_id=tg, text=text,
        ):
            count += 1
    return count


async def run_daily_summary(
    db: AsyncSession, sender: Sender, club: Club, now_utc: datetime
) -> int:
    if not club.notify_daily_summary_enabled:
        return 0
    try:
        tz = ZoneInfo(club.timezone or settings.default_timezone)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo(settings.default_timezone)
    local = now_utc.astimezone(tz)
    if local.hour != settings.daily_summary_hour:
        return 0
    today = local.date()
    data = await reports_svc.dashboard(
        db, club_id=club.id, start=today.replace(day=1), end=today, today=today
    )
    text = (
        f"📊 {club.name} — сводка на {today.isoformat()}\n"
        f"👥 Активных клиентов: {data['active_clients']}\n"
        f"✅ Посещений сегодня: {data['visits_today']}\n"
        f"⏳ Заканчиваются (7 дней): {data['subscriptions_ending_soon']}\n"
        f"💰 Поступления за месяц: {format_uzs(data['income_in_period'])}\n"
        f"❗ Долги: {format_uzs(data['total_debt'])}"
    )
    recipients = await _staff_recipients(db, club.id)
    count = 0
    for tg in recipients:
        key = f"daily:{today.isoformat()}:{tg}"
        if await _record_and_send(
            db, sender, club_id=club.id, kind="daily_summary", dedup_key=key,
            telegram_id=tg, text=text,
        ):
            count += 1
    return count


async def run_due_jobs(sender: Sender, now_utc: datetime | None = None) -> dict:
    """Run all notification jobs once for every active club. Returns counters."""
    now_utc = now_utc or datetime.now(tz=ZoneInfo("UTC"))
    today = now_utc.date()
    sm = get_sessionmaker()
    totals = {"expiry": 0, "overdue": 0, "daily_summary": 0}
    async with sm() as db:
        clubs = (
            await db.execute(select(Club).where(Club.is_active.is_(True)))
        ).scalars().all()
    for club in clubs:
        async with sm() as db:
            club = (await db.execute(select(Club).where(Club.id == club.id))).scalar_one()
            totals["expiry"] += await run_expiry_reminders(db, sender, club, today)
            totals["overdue"] += await run_overdue_reminders(db, sender, club, today)
            totals["daily_summary"] += await run_daily_summary(db, sender, club, now_utc)
    return totals


def _build_sender() -> Sender:
    if not settings.telegram_bot_token:
        logger.warning("No TELEGRAM_BOT_TOKEN; using LoggingSender (no messages sent).")
        return LoggingSender()
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    class BotSender(Sender):
        async def send(self, telegram_id: int, text: str) -> None:
            await bot.send_message(telegram_id, text)

    return BotSender()


async def loop(interval_seconds: int = 60) -> None:  # pragma: no cover
    sender = _build_sender()
    logger.info("Notification scheduler started (interval=%ss)", interval_seconds)
    while True:
        try:
            totals = await run_due_jobs(sender)
            if any(totals.values()):
                logger.info("Notifications sent: %s", totals)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Notification cycle failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(loop())


if __name__ == "__main__":  # pragma: no cover
    main()
