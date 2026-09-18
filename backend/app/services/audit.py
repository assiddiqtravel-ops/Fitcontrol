"""Audit logging helper.

Records administrative & financial actions. Never stores secrets or full
payment card data — only IDs, amounts and short reasons.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_audit(
    db: AsyncSession,
    *,
    club_id: int,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        club_id=club_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    db.add(entry)
    await db.flush()
    return entry
