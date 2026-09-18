"""Notification jobs: sending to staff + de-duplication."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.bot.notifications import LoggingSender, run_overdue_reminders
from app.core.enums import Role
from app.db.session import get_sessionmaker
from app.models import Charge, Client, Club
from tests.conftest import seed_club, seed_membership, seed_user

pytestmark = pytest.mark.asyncio


async def _seed_debtor(club_id: int) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        client = Client(club_id=club_id, first_name="Debtor")
        s.add(client)
        await s.flush()
        s.add(Charge(club_id=club_id, client_id=client.id, amount=200000))
        await s.commit()


async def test_overdue_reminder_sends_once_to_staff():
    club = await seed_club("Notify Gym")
    owner = await seed_user(7001)
    trainer = await seed_user(7002)
    await seed_membership(owner.id, club.id, Role.club_owner)
    await seed_membership(trainer.id, club.id, Role.trainer)  # excluded (not admin+)
    await _seed_debtor(club.id)

    sender = LoggingSender()
    sm = get_sessionmaker()
    today = date.today()

    async with sm() as db:
        club_row = (await db.execute(select(Club).where(Club.id == club.id))).scalar_one()
        sent = await run_overdue_reminders(db, sender, club_row, today)
    assert sent == 1  # only the owner (admin+), not the trainer
    assert sender.sent[0][0] == 7001
    assert "Debtor" in sender.sent[0][1]

    # Running again the same day must NOT resend (dedup).
    async with sm() as db:
        club_row = (await db.execute(select(Club).where(Club.id == club.id))).scalar_one()
        sent_again = await run_overdue_reminders(db, sender, club_row, today)
    assert sent_again == 0
    assert len(sender.sent) == 1
