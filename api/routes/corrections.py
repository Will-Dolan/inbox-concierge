import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.deps import get_current_user
from core.models import Bucket, Thread, ThreadTag, User

router = APIRouter(tags=["corrections"])


class CorrectionRequest(BaseModel):
    thread_id: str
    bucket_id: str
    action: Literal["add", "remove"]


@router.post("/corrections", status_code=202)
async def create_correction(
    body: CorrectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    thread_id = uuid.UUID(body.thread_id)
    bucket_id = uuid.UUID(body.bucket_id)

    thread = await db.get(Thread, thread_id)
    if thread is None or thread.user_id != user.id:
        raise HTTPException(404, "thread not found")
    bucket = await db.get(Bucket, bucket_id)
    if bucket is None or (bucket.user_id is not None and bucket.user_id != user.id):
        raise HTTPException(404, "bucket not found")

    value = body.action == "add"
    stmt = (
        pg_insert(ThreadTag)
        .values(thread_id=thread_id, bucket_id=bucket_id, source="user", value=value)
        .on_conflict_do_update(
            index_elements=[ThreadTag.thread_id, ThreadTag.bucket_id],
            set_={"source": "user", "value": value},
        )
    )
    await db.execute(stmt)
    await db.commit()

    # This endpoint is an override, not training feedback. A user may remove a
    # tag because the email is handled, stale, or otherwise should disappear
    # from the current bucket view; that does not necessarily mean the
    # classifier/rule was wrong.
    #
    # There is already a self-improvement agent in agent/self_improve.py, but
    # for the sake of time this was not built out into a refined product flow
    # with explicit example selection, review/rollback UX, and separate
    # "teach the rule" intent. Until that exists, avoid inferring rule-training
    # feedback from ordinary tag edits.
    return {"applied": True, "self_improve_job_id": None}
