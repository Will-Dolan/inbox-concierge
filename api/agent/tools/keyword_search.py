"""Postgres full-text search over subject+snippet. Portable to OpenSearch later."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Thread

TOOL_SCHEMA = {
    "name": "keyword_search",
    "description": "Full-text search this user's synced threads by subject/snippet keywords.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search phrase, e.g. 'receipt invoice order'"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    },
}


async def run(db: AsyncSession, user_id: uuid.UUID, query: str, limit: int = 20) -> list[dict]:
    tsvector = func.to_tsvector(
        "english", func.coalesce(Thread.subject, "") + " " + func.coalesce(Thread.snippet, "")
    )
    tsquery = func.plainto_tsquery("english", query)
    stmt = select(Thread).where(Thread.user_id == user_id, tsvector.op("@@")(tsquery)).limit(limit)
    result = await db.execute(stmt)
    return [_summary(t) for t in result.scalars().all()]


def _summary(t: Thread) -> dict:
    return {
        "thread_id": str(t.id),
        "subject": t.subject,
        "snippet": t.snippet,
        "sender_domain": t.sender_domain,
    }
