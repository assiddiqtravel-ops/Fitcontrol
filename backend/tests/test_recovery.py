"""Account-recovery & support endpoints."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.enums import Role
from app.db.session import get_sessionmaker
from app.models import AuditLog, Client, ClubMembership
from tests.conftest import ApiUser, seed_club, seed_membership, seed_user

pytestmark = pytest.mark.asyncio


async def test_grant_access_preserves_club_and_requires_admin(client):
    # A club with data owned by a now-lost Telegram account.
    lost_owner = await seed_user(8001)
    club = await seed_club("Recover Gym")
    await seed_membership(lost_owner.id, club.id, Role.club_owner)
    # Seed a client so we can prove data survives.
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(Client(club_id=club.id, first_name="Persistent"))
        await s.commit()

    # A non-platform-admin cannot use support endpoints.
    outsider = ApiUser(client, telegram_id=8002)
    r = await outsider.post(
        f"/api/v1/support/clubs/{club.id}/grant-access",
        json={"telegram_id": 8003, "role": "club_owner", "reason": "ticket-1"},
    )
    assert r.status_code == 403

    # Support (platform_admin) restores access to a NEW Telegram account.
    await seed_user(9999, is_platform_admin=True)
    support = ApiUser(client, telegram_id=9999)
    r = await support.post(
        f"/api/v1/support/clubs/{club.id}/grant-access",
        json={"telegram_id": 8003, "role": "club_owner", "reason": "verified via email"},
    )
    assert r.status_code == 200, r.text
    assert club.id in r.json()["affected_club_ids"]

    # The new account can now access the club and its data is intact.
    new_owner = ApiUser(client, telegram_id=8003, club_id=club.id)
    me = await new_owner.get("/api/v1/auth/me")
    assert any(c["club"]["id"] == club.id for c in me.json()["clubs"])
    clients = await new_owner.get("/api/v1/clients")
    assert clients.json()["total"] == 1  # data preserved

    # Audit recorded.
    async with sm() as s:
        actions = [a.action for a in (await s.execute(select(AuditLog))).scalars().all()]
    assert "recovery.grant_access" in actions


async def test_change_telegram_id_keeps_memberships(client):
    user = await seed_user(8100)
    c1 = await seed_club("Club A")
    c2 = await seed_club("Club B")
    await seed_membership(user.id, c1.id, Role.club_owner)
    await seed_membership(user.id, c2.id, Role.club_admin)
    await seed_user(9999, is_platform_admin=True)
    support = ApiUser(client, telegram_id=9999)

    r = await support.post(
        "/api/v1/support/recovery/change-telegram-id",
        json={"current_telegram_id": 8100, "new_telegram_id": 8200, "reason": "device lost"},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["affected_club_ids"]) == {c1.id, c2.id}

    # Old ID no longer resolves to those clubs; the new ID inherits everything.
    new_ident = ApiUser(client, telegram_id=8200)
    me = await new_ident.get("/api/v1/auth/me")
    club_ids = {c["club"]["id"] for c in me.json()["clubs"]}
    assert club_ids == {c1.id, c2.id}

    # Same underlying user row (membership count unchanged).
    sm = get_sessionmaker()
    async with sm() as s:
        memberships = (
            await s.execute(select(ClubMembership).where(ClubMembership.user_id == user.id))
        ).scalars().all()
    assert len(memberships) == 2


async def test_change_telegram_id_conflict(client):
    await seed_user(8300)
    await seed_user(8400)  # already taken
    await seed_user(9999, is_platform_admin=True)
    support = ApiUser(client, telegram_id=9999)
    r = await support.post(
        "/api/v1/support/recovery/change-telegram-id",
        json={"current_telegram_id": 8300, "new_telegram_id": 8400, "reason": "ticket-9"},
    )
    assert r.status_code == 409


async def test_webhook_disabled_by_default(client):
    # Default TELEGRAM_UPDATE_MODE=polling -> webhook endpoint returns 404.
    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "whatever"},
    )
    assert r.status_code == 404


async def test_webhook_secret_enforced(client, monkeypatch):
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "telegram_update_mode", "webhook")
    monkeypatch.setattr(config_mod.settings, "telegram_webhook_secret", "s3cret")

    # Wrong secret -> 403.
    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
    )
    assert r.status_code == 403

    # Correct secret, malformed update -> handler swallows error, returns 200.
    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"not": "an update"},
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
