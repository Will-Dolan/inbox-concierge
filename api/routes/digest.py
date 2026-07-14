import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agent.digest import generate_digest
from core.db import get_db
from core.deps import get_current_user
from core.models import User
from core.ratelimit import check_rate_limit, rate_limit

router = APIRouter(tags=["digest"])


@router.get("/digest")
async def get_digest(
    bucket_id: uuid.UUID = Query(...),
    force: bool = Query(False, description="Bypass the cached digest and regenerate"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit("digest", limit=20, window_seconds=300)),
) -> dict:
    # `force=true` bypasses the cache and re-triggers the LLM-backed digest
    # generation, so it gets its own tighter budget on top of the general one.
    if force:
        check_rate_limit(f"digest_force:{user.id}", limit=5, window_seconds=300)
    return await generate_digest(db, user.id, bucket_id, force=force)
