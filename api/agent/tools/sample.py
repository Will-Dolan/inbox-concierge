"""Pull full subject/snippet/features detail for inspection."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Thread

TOOL_SCHEMA = {
    "name": "sample",
    "description": (
        "Pull full subject/snippet/features detail for specific thread_ids, or a random "
        "sample of size n from the full corpus if thread_ids is omitted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thread_ids": {"type": "array", "items": {"type": "string"}},
            "n": {"type": "integer", "default": 10},
        },
    },
}


async def run(
    db: AsyncSession, user_id: uuid.UUID, thread_ids: list[str] | None = None, n: int = 10
) -> list[dict]:
    stmt = select(Thread).where(Thread.user_id == user_id)
    if thread_ids:
        stmt = stmt.where(Thread.id.in_([uuid.UUID(tid) for tid in thread_ids]))
    else:
        stmt = stmt.order_by(func.random()).limit(n)
    result = await db.execute(stmt)
    return [
        {
            "thread_id": str(t.id),
            "subject": t.subject,
            "snippet": t.snippet,
            "sender_domain": t.sender_domain,
            "features": t.features,
        }
        for t in result.scalars().all()
    ]
