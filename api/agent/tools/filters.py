"""SQL predicate filters over the user's synced threads - composable AND."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Thread

TOOL_SCHEMA = {
    "name": "filter_threads",
    "description": (
        "Filter threads by sender domain, mailing-list id, and/or a time range. "
        "All provided filters are ANDed together."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sender_domain": {"type": "string"},
            "list_id": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 datetime"},
            "end": {"type": "string", "description": "ISO 8601 datetime"},
            "limit": {"type": "integer", "default": 30},
        },
    },
}


async def run(
    db: AsyncSession,
    user_id: uuid.UUID,
    sender_domain: str | None = None,
    list_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 30,
) -> list[dict]:
    stmt = select(Thread).where(Thread.user_id == user_id)
    if sender_domain:
        stmt = stmt.where(Thread.sender_domain == sender_domain)
    if list_id:
        stmt = stmt.where(Thread.features["list_id"].astext == list_id)
    if start:
        stmt = stmt.where(Thread.latest_internal_date >= datetime.fromisoformat(start))
    if end:
        stmt = stmt.where(Thread.latest_internal_date <= datetime.fromisoformat(end))
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return [
        {
            "thread_id": str(t.id),
            "subject": t.subject,
            "snippet": t.snippet,
            "sender_domain": t.sender_domain,
        }
        for t in result.scalars().all()
    ]
