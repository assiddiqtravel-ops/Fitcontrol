"""Test configuration.

Uses an isolated, file-based SQLite database (never production). Environment
variables are set BEFORE importing the app so cached settings pick them up.
DEV_AUTH_MODE is enabled so requests can authenticate with an ``X-Dev-Telegram-Id``
header instead of a full Telegram Mini App handshake.
"""
from __future__ import annotations

import os
import tempfile

# --- Configure environment before importing the app ---
_TMP_DB = os.path.join(tempfile.gettempdir(), "fitcontrol_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["ENVIRONMENT"] = "development"
os.environ["DEV_AUTH_MODE"] = "true"
os.environ["TELEGRAM_BOT_TOKEN"] = "test-bot-token:ABC"
os.environ["CORS_ORIGINS"] = "*"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.enums import Role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Club, ClubMembership, User  # noqa: E402


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def app():
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class ApiUser:
    """Helper wrapping a dev-auth identity and its club headers."""

    def __init__(self, client: AsyncClient, telegram_id: int, club_id: int | None = None):
        self._client = client
        self.telegram_id = telegram_id
        self.club_id = club_id

    def headers(self, with_club: bool = True) -> dict:
        h = {"X-Dev-Telegram-Id": str(self.telegram_id)}
        if with_club and self.club_id is not None:
            h["X-Club-Id"] = str(self.club_id)
        return h

    def get(self, url, **kw):
        return self._client.get(url, headers={**self.headers(), **kw.pop("headers", {})}, **kw)

    def post(self, url, **kw):
        return self._client.post(url, headers={**self.headers(), **kw.pop("headers", {})}, **kw)

    def patch(self, url, **kw):
        return self._client.patch(url, headers={**self.headers(), **kw.pop("headers", {})}, **kw)


async def seed_user(telegram_id: int, is_platform_admin: bool = False) -> User:
    sm = get_sessionmaker()
    async with sm() as s:
        user = User(
            telegram_id=telegram_id,
            first_name=f"U{telegram_id}",
            is_platform_admin=is_platform_admin,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user


async def seed_club(name: str = "Club") -> Club:
    sm = get_sessionmaker()
    async with sm() as s:
        club = Club(name=name)
        s.add(club)
        await s.commit()
        await s.refresh(club)
        return club


async def seed_membership(user_id: int, club_id: int, role: Role) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(
            ClubMembership(
                user_id=user_id, club_id=club_id, role=role.value, is_active=True
            )
        )
        await s.commit()


@pytest_asyncio.fixture
async def owner_ctx(client):
    """A club with an owner user already set up. Returns (ApiUser, club_id)."""
    user = await seed_user(1001)
    club = await seed_club("Alpha Gym")
    await seed_membership(user.id, club.id, Role.club_owner)
    return ApiUser(client, telegram_id=1001, club_id=club.id)
