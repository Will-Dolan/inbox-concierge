import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agent.digest import generate_digest
from core.db import get_db
from core.deps import get_current_user
from core.models import User

router = APIRouter(tags=["digest"])


@router.get("/digest")
async def get_digest(
    bucket_id: uuid.UUID = Query(...),
    force: bool = Query(False, description="Bypass the cached digest and regenerate"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await generate_digest(db, user.id, bucket_id, force=force)
