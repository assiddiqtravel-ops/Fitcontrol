"""API-level tests: tenant isolation, RBAC, billing, idempotency, visits."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.core.enums import Role
from app.db.session import get_sessionmaker
from tests.conftest import ApiUser, seed_club, seed_membership, seed_user

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# Auth & club bootstrap
# --------------------------------------------------------------------------- #
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_create_club_makes_owner(client):
    user = ApiUser(client, telegram_id=5001)
    r = await user.post("/api/v1/clubs", json={"name": "New Gym"})
    assert r.status_code == 201, r.text
    club_id = r.json()["id"]
    me = await user.get("/api/v1/auth/me")
    assert me.status_code == 200
    clubs = me.json()["clubs"]
    assert any(c["club"]["id"] == club_id and c["role"] == "club_owner" for c in clubs)


# --------------------------------------------------------------------------- #
# Clients & plans (endpoints #8)
# --------------------------------------------------------------------------- #
async def test_clients_crud_and_search(owner_ctx: ApiUser):
    r = await owner_ctx.post(
        "/api/v1/clients", json={"first_name": "Aziz", "last_name": "Karimov", "phone": "+99890"}
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    # search by phone
    r = await owner_ctx.get("/api/v1/clients", params={"q": "99890"})
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # archive (soft delete)
    r = await owner_ctx.post(f"/api/v1/clients/{cid}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    # archived excluded from default active filter
    r = await owner_ctx.get("/api/v1/clients", params={"status": "active"})
    assert r.json()["total"] == 0


async def test_plans_crud(owner_ctx: ApiUser):
    r = await owner_ctx.post(
        "/api/v1/plans",
        json={
            "name": "Monthly",
            "price": 300000,
            "duration_value": 1,
            "duration_unit": "months",
            "visit_limit": 12,
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = await owner_ctx.patch(f"/api/v1/plans/{pid}", json={"price": 350000})
    assert r.status_code == 200
    assert r.json()["price"] == 350000


# --------------------------------------------------------------------------- #
# Tenant isolation (#2)
# --------------------------------------------------------------------------- #
async def test_tenant_isolation(client):
    # Two clubs, two owners.
    u1 = await seed_user(2001)
    u2 = await seed_user(2002)
    c1 = await seed_club("Club One")
    c2 = await seed_club("Club Two")
    await seed_membership(u1.id, c1.id, Role.club_owner)
    await seed_membership(u2.id, c2.id, Role.club_owner)

    owner1 = ApiUser(client, telegram_id=2001, club_id=c1.id)
    owner2 = ApiUser(client, telegram_id=2002, club_id=c2.id)

    # Owner1 creates a client in club1.
    r = await owner1.post("/api/v1/clients", json={"first_name": "Secret"})
    assert r.status_code == 201
    secret_client_id = r.json()["id"]

    # Owner2 (different club) cannot see it by listing.
    r = await owner2.get("/api/v1/clients")
    assert r.status_code == 200
    assert r.json()["total"] == 0

    # Owner2 cannot fetch it by ID (no leakage across clubs).
    r = await owner2.get(f"/api/v1/clients/{secret_client_id}")
    assert r.status_code == 404

    # Owner2 forging club1's X-Club-Id is rejected server-side (no membership).
    forged = await client.get(
        f"/api/v1/clients/{secret_client_id}",
        headers={"X-Dev-Telegram-Id": "2002", "X-Club-Id": str(c1.id)},
    )
    assert forged.status_code == 403


# --------------------------------------------------------------------------- #
# RBAC (#3)
# --------------------------------------------------------------------------- #
async def test_rbac_roles(client):
    club = await seed_club("RBAC Gym")
    owner = await seed_user(3001)
    admin = await seed_user(3002)
    trainer = await seed_user(3003)
    await seed_membership(owner.id, club.id, Role.club_owner)
    await seed_membership(admin.id, club.id, Role.club_admin)
    await seed_membership(trainer.id, club.id, Role.trainer)

    owner_u = ApiUser(client, 3001, club.id)
    admin_u = ApiUser(client, 3002, club.id)
    trainer_u = ApiUser(client, 3003, club.id)

    # Trainer can read clients but NOT create them (needs admin).
    assert (await trainer_u.get("/api/v1/clients")).status_code == 200
    assert (await trainer_u.post("/api/v1/clients", json={"first_name": "X"})).status_code == 403

    # Admin can create clients.
    assert (await admin_u.post("/api/v1/clients", json={"first_name": "Y"})).status_code == 201

    # Only owner can change club settings.
    assert (await admin_u.patch("/api/v1/settings", json={"name": "Nope"})).status_code == 403
    assert (await owner_u.patch("/api/v1/settings", json={"name": "Renamed"})).status_code == 200


# --------------------------------------------------------------------------- #
# Billing helpers
# --------------------------------------------------------------------------- #
async def _make_client_and_plan(u: ApiUser, price=300000, unit="months", value=1, limit=None):
    rc = await u.post("/api/v1/clients", json={"first_name": "Payer"})
    cid = rc.json()["id"]
    body = {"name": "Plan", "price": price, "duration_value": value, "duration_unit": unit}
    if limit is not None:
        body["visit_limit"] = limit
    rp = await u.post("/api/v1/plans", json=body)
    pid = rp.json()["id"]
    return cid, pid


# --------------------------------------------------------------------------- #
# Partial payment & debt (#4)
# --------------------------------------------------------------------------- #
async def test_partial_payment_and_debt(owner_ctx: ApiUser):
    cid, pid = await _make_client_and_plan(owner_ctx, price=300000)
    r = await owner_ctx.post(
        "/api/v1/subscriptions",
        json={"client_id": cid, "plan_id": pid, "start_date": str(date.today())},
    )
    assert r.status_code == 201, r.text

    # Debt equals full charge before any payment.
    ledger = (await owner_ctx.get(f"/api/v1/clients/{cid}/ledger")).json()
    assert ledger["total_charged"] == 300000
    assert ledger["debt"] == 300000

    # Partial payment of 100000.
    r = await owner_ctx.post(
        "/api/v1/payments", json={"client_id": cid, "amount": 100000, "method": "cash"}
    )
    assert r.status_code == 201, r.text

    ledger = (await owner_ctx.get(f"/api/v1/clients/{cid}/ledger")).json()
    assert ledger["total_paid"] == 100000
    assert ledger["debt"] == 200000

    # Overpay never yields negative debt; surfaces as credit.
    await owner_ctx.post(
        "/api/v1/payments", json={"client_id": cid, "amount": 500000, "method": "card"}
    )
    ledger = (await owner_ctx.get(f"/api/v1/clients/{cid}/ledger")).json()
    assert ledger["debt"] == 0
    assert ledger["credit"] == 300000


async def test_negative_or_zero_payment_rejected(owner_ctx: ApiUser):
    cid, _ = await _make_client_and_plan(owner_ctx)
    r = await owner_ctx.post("/api/v1/payments", json={"client_id": cid, "amount": 0})
    assert r.status_code == 422
    r = await owner_ctx.post("/api/v1/payments", json={"client_id": cid, "amount": -5})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Idempotency (#7)
# --------------------------------------------------------------------------- #
async def test_payment_idempotency(owner_ctx: ApiUser):
    cid, _ = await _make_client_and_plan(owner_ctx)
    headers = {"Idempotency-Key": "abc-123"}
    r1 = await owner_ctx.post(
        "/api/v1/payments", json={"client_id": cid, "amount": 50000}, headers=headers
    )
    assert r1.status_code == 201
    r2 = await owner_ctx.post(
        "/api/v1/payments", json={"client_id": cid, "amount": 50000}, headers=headers
    )
    assert r2.status_code == 200  # existing returned, not created
    assert r1.json()["id"] == r2.json()["id"]

    ledger = (await owner_ctx.get(f"/api/v1/clients/{cid}/ledger")).json()
    assert ledger["total_paid"] == 50000  # counted once


# --------------------------------------------------------------------------- #
# Reversal / сторно + audit (#5)
# --------------------------------------------------------------------------- #
async def test_reversal_and_audit(owner_ctx: ApiUser):
    cid, _ = await _make_client_and_plan(owner_ctx)
    r = await owner_ctx.post("/api/v1/payments", json={"client_id": cid, "amount": 120000})
    payment_id = r.json()["id"]

    # Reverse requires a reason.
    r = await owner_ctx.post(f"/api/v1/payments/{payment_id}/reverse", json={"reason": ""})
    assert r.status_code == 422

    r = await owner_ctx.post(
        f"/api/v1/payments/{payment_id}/reverse", json={"reason": "customer refund"}
    )
    assert r.status_code == 200, r.text

    # Payment still exists (never deleted) but is marked reversed.
    payments = (await owner_ctx.get("/api/v1/payments", params={"client_id": cid})).json()
    assert len(payments) == 1
    assert payments[0]["is_reversed"] is True

    # Reversed payment no longer counts toward paid total.
    ledger = (await owner_ctx.get(f"/api/v1/clients/{cid}/ledger")).json()
    assert ledger["total_paid"] == 0

    # Double reversal blocked.
    r = await owner_ctx.post(
        f"/api/v1/payments/{payment_id}/reverse", json={"reason": "again"}
    )
    assert r.status_code == 409

    # Audit log recorded the payment + reversal.
    from app.models import AuditLog

    sm = get_sessionmaker()
    async with sm() as s:
        from sqlalchemy import select

        actions = [
            a.action
            for a in (await s.execute(select(AuditLog))).scalars().all()
        ]
    assert "payment.create" in actions
    assert "payment.reverse" in actions


# --------------------------------------------------------------------------- #
# Expired subscription blocks visit (#6)
# --------------------------------------------------------------------------- #
async def test_expired_subscription_blocks_visit(owner_ctx: ApiUser):
    # 1-day plan starting well in the past -> expired.
    cid, pid = await _make_client_and_plan(owner_ctx, price=0, unit="days", value=1)
    past = date.today() - timedelta(days=10)
    r = await owner_ctx.post(
        "/api/v1/subscriptions",
        json={"client_id": cid, "plan_id": pid, "start_date": str(past)},
    )
    assert r.status_code == 201, r.text

    elig = (await owner_ctx.get(f"/api/v1/clients/{cid}/visit-eligibility")).json()
    assert elig["allowed"] is False
    assert elig["reason"] == "expired"

    # Visit blocked without override.
    r = await owner_ctx.post("/api/v1/visits", json={"client_id": cid})
    assert r.status_code == 409

    # Authorized override with a written reason is allowed and recorded.
    r = await owner_ctx.post(
        "/api/v1/visits",
        json={"client_id": cid, "override_reason": "manager approved trial"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["result"] == "override"


async def test_active_subscription_allows_and_counts_visits(owner_ctx: ApiUser):
    cid, pid = await _make_client_and_plan(owner_ctx, price=0, unit="months", value=1, limit=2)
    r = await owner_ctx.post(
        "/api/v1/subscriptions",
        json={"client_id": cid, "plan_id": pid, "start_date": str(date.today())},
    )
    assert r.status_code == 201

    # Two allowed visits, then limit reached.
    assert (await owner_ctx.post("/api/v1/visits", json={"client_id": cid})).status_code == 201
    assert (await owner_ctx.post("/api/v1/visits", json={"client_id": cid})).status_code == 201
    elig = (await owner_ctx.get(f"/api/v1/clients/{cid}/visit-eligibility")).json()
    assert elig["reason"] == "limit_reached"
    r = await owner_ctx.post("/api/v1/visits", json={"client_id": cid})
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
# Dashboard separates income from debt
# --------------------------------------------------------------------------- #
async def test_dashboard_income_vs_debt(owner_ctx: ApiUser):
    cid, pid = await _make_client_and_plan(owner_ctx, price=300000)
    await owner_ctx.post(
        "/api/v1/subscriptions",
        json={"client_id": cid, "plan_id": pid, "start_date": str(date.today())},
    )
    await owner_ctx.post("/api/v1/payments", json={"client_id": cid, "amount": 100000})

    dash = (await owner_ctx.get("/api/v1/dashboard", params={"period": "today"})).json()
    assert dash["income_in_period"] == 100000  # received money
    assert dash["total_debt"] == 200000        # outstanding, shown separately
    assert dash["active_clients"] == 1
