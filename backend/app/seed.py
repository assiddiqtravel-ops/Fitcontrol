"""Development sample data loader (NEVER run against production).

Creates a demo owner, club, plans, clients, a subscription, a partial payment
and a visit so the Mini App has something to show. Safe to re-run: it checks for
an existing demo club first.

Run: ``python -m app.seed`` (or ``docker compose run --rm api seed``).

The demo owner's Telegram ID is 999000001 — set VITE_DEV_TELEGRAM_ID to that
value (with DEV_AUTH_MODE=true) to log in as the owner locally.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.enums import Role
from app.db.session import get_sessionmaker
from app.models import Client, Club, Plan, User
from app.services import billing as billing_svc
from app.services import clubs as clubs_svc
from app.services import subscriptions as sub_svc
from app.services import visits as visit_svc

logger = logging.getLogger("fitcontrol.seed")

DEMO_OWNER_TG = 999000001


async def seed() -> None:
    if settings.is_production:
        raise SystemExit("Refusing to seed in production (ENVIRONMENT=production).")

    sm = get_sessionmaker()
    async with sm() as db:
        existing = (
            await db.execute(select(Club).where(Club.name == "Demo Fitness"))
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("Demo data already present (club id=%s). Skipping.", existing.id)
            return

        owner = (
            await db.execute(select(User).where(User.telegram_id == DEMO_OWNER_TG))
        ).scalar_one_or_none()
        if owner is None:
            owner = User(telegram_id=DEMO_OWNER_TG, first_name="Demo", last_name="Owner")
            db.add(owner)
            await db.flush()

        club = await clubs_svc.create_club(db, owner=owner, name="Demo Fitness")

        plan_month = Plan(
            club_id=club.id,
            name="Месячный безлимит",
            price=300000,
            duration_value=1,
            duration_unit="months",
            visit_limit=None,
            description="30 дней без ограничений",
        )
        plan_12 = Plan(
            club_id=club.id,
            name="12 занятий",
            price=250000,
            duration_value=2,
            duration_unit="months",
            visit_limit=12,
        )
        db.add_all([plan_month, plan_12])
        await db.flush()

        # Clients
        alice = Client(club_id=club.id, first_name="Алишер", last_name="Усманов", phone="+998901112233")
        bob = Client(club_id=club.id, first_name="Дилноза", last_name="Каримова", phone="+998907776655")
        db.add_all([alice, bob])
        await db.flush()

        # Alice: active subscription + partial payment (leaves a debt)
        sub = await sub_svc.create_subscription(
            db,
            club_id=club.id,
            client_id=alice.id,
            plan_id=plan_month.id,
            start_date=date.today() - timedelta(days=3),
            actor_user_id=owner.id,
        )
        await billing_svc.create_payment(
            db,
            club_id=club.id,
            client_id=alice.id,
            amount=100000,
            method="cash",
            comment="Частичная оплата",
            received_by=owner.id,
            subscription_id=sub.id,
        )
        await visit_svc.register_visit(
            db, club_id=club.id, client_id=alice.id, actor_user_id=owner.id
        )

        # Bob: limited plan, fully paid
        sub2 = await sub_svc.create_subscription(
            db,
            club_id=club.id,
            client_id=bob.id,
            plan_id=plan_12.id,
            start_date=date.today(),
            actor_user_id=owner.id,
        )
        await billing_svc.create_payment(
            db,
            club_id=club.id,
            client_id=bob.id,
            amount=250000,
            method="card",
            received_by=owner.id,
            subscription_id=sub2.id,
        )

        await db.commit()
        logger.info(
            "Seeded demo club id=%s owner_tg=%s (set VITE_DEV_TELEGRAM_ID=%s).",
            club.id,
            DEMO_OWNER_TG,
            DEMO_OWNER_TG,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())


if __name__ == "__main__":
    main()
