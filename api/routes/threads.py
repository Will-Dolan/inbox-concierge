import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.crypto import decrypt
from core.db import get_db
from core.deps import get_current_user
from core.google_oauth import refresh_access_token
from core.models import Bucket, Thread, ThreadTag, User
from gmail.body import extract_body
from gmail.client import GmailClient

router = APIRouter(tags=["threads"])


def _without_unread_label(features: dict | None) -> dict:
    features = features or {}
    return {
        **features,
        "gmail_labels": [label for label in features.get("gmail_labels", []) if label != "UNREAD"],
    }


@router.get("/threads")
async def list_threads(
    bucket: str | None = Query(default=None, description="Filter by bucket name"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = (
        select(Thread)
        .where(Thread.user_id == user.id)
        .options(selectinload(Thread.tags).selectinload(ThreadTag.bucket))
        .order_by(Thread.latest_internal_date.desc())
    )
    result = await db.execute(query)
    all_threads = result.scalars().unique().all()

    out = []
    for t in all_threads:
        tag_names = [tag.bucket.name for tag in t.tags if tag.value]
        if bucket is not None and bucket not in tag_names:
            continue
        out.append(
            {
                "id": str(t.id),
                "subject": t.subject,
                "snippet": t.snippet,
                "sender_domain": t.sender_domain,
                "latest_internal_date": t.latest_internal_date.isoformat()
                if t.latest_internal_date
                else None,
                "tags": tag_names,
                "unread": "UNREAD" in (t.features or {}).get("gmail_labels", []),
            }
        )
    return out


@router.post("/threads/mark-read")
async def mark_threads_read(
    bucket_id: uuid.UUID | None = Query(default=None),
    sender_domain: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Thread).where(
        Thread.user_id == user.id,
        Thread.features["gmail_labels"].contains(["UNREAD"]),
    )
    if bucket_id is not None:
        bucket_exists = await db.scalar(
            select(Bucket.id).where(
                Bucket.id == bucket_id,
                (Bucket.user_id == user.id) | (Bucket.user_id.is_(None)),
            )
        )
        if bucket_exists is None:
            raise HTTPException(404, "bucket not found")

        query = query.join(ThreadTag, ThreadTag.thread_id == Thread.id).where(
            ThreadTag.bucket_id == bucket_id,
            ThreadTag.value.is_(True),
        )
    if sender_domain is not None:
        query = query.where(Thread.sender_domain == sender_domain)

    threads = (await db.execute(query)).scalars().unique().all()
    if not threads:
        return {"marked": 0, "failed": 0}

    access_token = await refresh_access_token(decrypt(user.encrypted_refresh_token))
    marked = 0
    failed = 0
    async with GmailClient(access_token) as client:
        for thread in threads:
            try:
                await client.mark_thread_read(thread.gmail_thread_id)
            except Exception:  # noqa: BLE001 - keep going; report partial failure to the UI
                failed += 1
                continue
            thread.features = _without_unread_label(thread.features)
            marked += 1

    if marked:
        await db.commit()
    return {"marked": marked, "failed": failed}


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = (
        select(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user.id)
        .options(
            selectinload(Thread.messages),
            selectinload(Thread.tags).selectinload(ThreadTag.bucket),
        )
    )
    thread = (await db.execute(query)).unique().scalar_one_or_none()
    if thread is None:
        raise HTTPException(404, "thread not found")

    messages = sorted(thread.messages, key=lambda m: m.internal_date)

    # Bodies aren't fetched during sync (metadata-only, for cost/latency) -
    # fetch lazily here on first open, then cache so later opens don't hit
    # Gmail again.
    missing = [m for m in messages if not m.body_fetched]
    was_unread = "UNREAD" in (thread.features or {}).get("gmail_labels", [])
    if missing or was_unread:
        access_token = await refresh_access_token(decrypt(user.encrypted_refresh_token))
        async with GmailClient(access_token) as client:
            for m in missing:
                try:
                    detail = await client.get_message(m.gmail_message_id)
                    body = extract_body(detail.get("payload", {}))
                    m.body_html = body["html"]
                    m.body_text = body["text"]
                except Exception:  # noqa: BLE001 - best-effort; fall back to snippet client-side
                    m.body_html = None
                    m.body_text = None
                m.body_fetched = True

            if was_unread:
                try:
                    await client.mark_thread_read(thread.gmail_thread_id)
                    thread.features = _without_unread_label(thread.features)
                except Exception:  # noqa: BLE001 - best-effort; local state stays unread, retried next open
                    pass
        await db.commit()

    return {
        "id": str(thread.id),
        "subject": thread.subject,
        "snippet": thread.snippet,
        "sender_domain": thread.sender_domain,
        "latest_internal_date": thread.latest_internal_date.isoformat()
        if thread.latest_internal_date
        else None,
        "tags": [tag.bucket.name for tag in thread.tags if tag.value],
        "unread": "UNREAD" in (thread.features or {}).get("gmail_labels", []),
        "messages": [
            {
                "from": m.headers.get("From"),
                "to": m.headers.get("To"),
                "date": m.internal_date.isoformat(),
                "body": m.body_text,
                "body_html": m.body_html,
            }
            for m in messages
        ],
    }
