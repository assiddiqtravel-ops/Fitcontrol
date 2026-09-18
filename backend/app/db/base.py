"""Declarative base and shared column mixins."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# BigInteger everywhere in production (Postgres BIGSERIAL), but SQLite only
# autoincrements a plain INTEGER PRIMARY KEY — so we downgrade the type on the
# sqlite dialect used by the test suite.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )


class PKMixin:
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
