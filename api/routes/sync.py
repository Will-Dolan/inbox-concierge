import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from classify.sync_pipeline import classify_new_threads
from core.db import async_session_factory
from core.deps import get_current_user
from core.models import Bucket, Thread, User
from core.queue import queue
from gmail.sync import sync_last_200_threads

router = APIRouter(tags=["sync"])


@router.post("/sync", status_code=202)
async def start_sync(user: User = Depends(get_current_user)) -> dict:
    user_id: uuid.UUID = user.id

    async def run() -> dict:
        async with async_session_factory() as session:
            fresh_user = await session.get(User, user_id)
            synced = await sync_last_200_threads(session, fresh_user)

            threads = (
                (await session.execute(select(Thread).where(Thread.user_id == user_id)))
                .scalars()
                .all()
            )
            default_buckets = (
                (await session.execute(select(Bucket).where(Bucket.kind == "system")))
                .scalars()
                .all()
            )
            classified = await classify_new_threads(session, list(threads), list(default_buckets))
            return {"threads_synced": synced, "threads_classified": classified}

    job_id = queue.enqueue(user_id, run)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: User = Depends(get_current_user)) -> dict:
    job = queue.get(job_id, user.id)
    if job is None:
        return {"status": "not_found"}
    return {"status": job.status, "result": job.result, "error": job.error, "progress": job.progress}
