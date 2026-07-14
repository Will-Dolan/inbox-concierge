import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.deps import get_current_user
from core.models import User
from gmail.unsubscribe import execute_one_click, list_candidates

router = APIRouter(tags=["unsubscribe"])


@router.get("/unsubscribe/candidates")
async def get_candidates(
    bucket_id: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await list_candidates(db, user.id, bucket_id)


class ExecuteRequest(BaseModel):
    url: str


@router.post("/unsubscribe/execute")
async def execute(
    body: ExecuteRequest,
    user: User = Depends(get_current_user),
) -> dict:
    ok = await execute_one_click(body.url)
    if not ok:
        raise HTTPException(502, "Unsubscribe request failed")
    return {"ok": True}
