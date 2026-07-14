import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.deps import get_current_user
from core.models import User
from gmail.unsubscribe import execute_one_click, get_one_click_url, list_candidates

router = APIRouter(tags=["unsubscribe"])


@router.get("/unsubscribe/candidates")
async def get_candidates(
    bucket_id: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await list_candidates(db, user.id, bucket_id)


class ExecuteRequest(BaseModel):
    bucket_id: uuid.UUID
    sender_domain: str


@router.post("/unsubscribe/execute")
async def execute(
    body: ExecuteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Never POST to a client-supplied URL: always re-derive the one-click
    # target server-side from this user's own thread data (SSRF prevention).
    url = await get_one_click_url(db, user.id, body.bucket_id, body.sender_domain)
    if url is None:
        raise HTTPException(404, "No one-click unsubscribe candidate found")
    ok = await execute_one_click(url)
    if not ok:
        raise HTTPException(502, "Unsubscribe request failed")
    return {"ok": True}
