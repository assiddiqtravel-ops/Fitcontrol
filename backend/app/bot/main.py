"""FitControl Telegram bot (aiogram 3).

Entry point (module): ``python -m app.bot.main``.

The bot is the entry point and notification channel. It exposes:
  * /start — greeting + a button that opens the Mini App (Telegram WebApp)
  * /help  — command list
  * /report, /debtors, /ending — quick club stats for admins/owners

All reporting commands verify the caller's Telegram ID is bound to a club with
at least club_admin role; unknown users are guided to open the Mini App.
Logging never includes tokens, initData or excessive personal data.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.bot import queries
from app.core.config import settings
from app.core.money import format_uzs
from app.db.session import get_sessionmaker

logger = logging.getLogger("fitcontrol.bot")

dp = Dispatcher()


def _open_app_keyboard() -> InlineKeyboardMarkup | None:
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏋️ Открыть FitControl",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    kb = _open_app_keyboard()
    text = (
        "<b>FitControl</b> — управление фитнес-клубом.\n\n"
        "Нажмите кнопку ниже, чтобы открыть панель управления. "
        "Если у вас ещё нет клуба, внутри приложения можно создать новый "
        "или принять приглашение."
    )
    if kb is None:
        text += (
            "\n\n⚠️ WEBAPP_URL не настроен — администратор должен указать HTTPS-адрес "
            "Mini App (см. README)."
        )
    await message.answer(text, reply_markup=kb)


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/start — открыть приложение\n"
        "/report — краткий отчёт по клубу (для админов)\n"
        "/debtors — список должников (для админов)\n"
        "/ending — заканчивающиеся абонементы (для админов)\n"
        "/help — эта справка"
    )


async def _require_admin(message: Message):
    sm = get_sessionmaker()
    async with sm() as db:
        resolved = await queries.resolve_admin_club(db, message.from_user.id)
    if resolved is None:
        await message.answer(
            "У вас нет прав администратора ни в одном клубе. "
            "Откройте приложение через /start, чтобы создать клуб или принять приглашение."
        )
        return None
    return resolved


@dp.message(Command("report"))
async def cmd_report(message: Message) -> None:
    resolved = await _require_admin(message)
    if resolved is None:
        return
    _, club, _ = resolved
    sm = get_sessionmaker()
    async with sm() as db:
        data = await queries.quick_report(db, club.id)
    await message.answer(
        f"<b>{club.name}</b> — отчёт за месяц\n"
        f"👥 Активных клиентов: {data['active_clients']}\n"
        f"✅ Посещений сегодня: {data['visits_today']}\n"
        f"⏳ Заканчиваются (7 дней): {data['subscriptions_ending_soon']}\n"
        f"💰 Поступления: {format_uzs(data['income_in_period'])}\n"
        f"❗ Долги: {format_uzs(data['total_debt'])} "
        f"({data['clients_with_debt']} клиентов)"
    )


@dp.message(Command("debtors"))
async def cmd_debtors(message: Message) -> None:
    resolved = await _require_admin(message)
    if resolved is None:
        return
    _, club, _ = resolved
    sm = get_sessionmaker()
    async with sm() as db:
        rows = await queries.debtors(db, club.id)
    if not rows:
        await message.answer(f"<b>{club.name}</b>: должников нет 🎉")
        return
    lines = [f"• {name} — {format_uzs(debt)}" for _cid, name, debt in rows]
    await message.answer(f"<b>{club.name}</b> — должники:\n" + "\n".join(lines))


@dp.message(Command("ending"))
async def cmd_ending(message: Message) -> None:
    resolved = await _require_admin(message)
    if resolved is None:
        return
    _, club, _ = resolved
    sm = get_sessionmaker()
    async with sm() as db:
        subs = await queries.ending_soon(db, club.id, within_days=7)
    if not subs:
        await message.answer(f"<b>{club.name}</b>: нет абонементов, заканчивающихся в ближайшие 7 дней.")
        return
    lines = [f"• client #{s.client_id} — до {s.end_date.isoformat()}" for s in subs]
    await message.answer(
        f"<b>{club.name}</b> — заканчивающиеся абонементы:\n" + "\n".join(lines)
    )


@dp.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("Не понимаю команду. Наберите /help или откройте приложение через /start.")


async def run() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.info("Starting FitControl bot (long polling)")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
