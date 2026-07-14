from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.deps import get_current_user
from core.models import Thread, User

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/threads")
async def debug_threads(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(Thread).where(Thread.user_id == user.id).order_by(Thread.latest_internal_date.desc())
    )
    threads = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "gmail_thread_id": t.gmail_thread_id,
            "subject": t.subject,
            "snippet": t.snippet,
            "sender_domain": t.sender_domain,
            "latest_internal_date": t.latest_internal_date.isoformat() if t.latest_internal_date else None,
            "message_count": t.message_count,
            "features": t.features,
        }
        for t in threads
    ]
