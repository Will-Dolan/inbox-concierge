import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.crypto import decrypt
from core.google_oauth import refresh_access_token
from core.models import MessageLite, Thread, User
from gmail.client import GmailClient
from gmail.thread_features import MessageFeatures, aggregate_thread_features

MAX_THREADS = 200
FETCH_CONCURRENCY = 8


def _parse_thread_detail(detail: dict) -> list[MessageFeatures]:
    parsed: list[MessageFeatures] = []
    for m in detail.get("messages", []):
        headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
        internal_date = datetime.fromtimestamp(int(m["internalDate"]) / 1000, tz=UTC)
        parsed.append(
            MessageFeatures(
                id=m["id"],
                internal_date=internal_date,
                headers=headers,
                label_ids=m.get("labelIds", []),
                snippet=m.get("snippet", ""),
            )
        )
    parsed.sort(key=lambda m: m["internal_date"])
    return parsed


async def _get_access_token(user: User) -> str:
    refresh_token = decrypt(user.encrypted_refresh_token)
    return await refresh_access_token(refresh_token)


async def sync_last_200_threads(db: AsyncSession, user: User) -> int:
    access_token = await _get_access_token(user)

    async with GmailClient(access_token) as client:
        thread_ids = await client.list_thread_ids(MAX_THREADS)
        semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

        async def fetch(tid: str) -> dict:
            async with semaphore:
                return await client.get_thread(tid)

        details = await asyncio.gather(*(fetch(tid) for tid in thread_ids))

    synced = 0
    for gmail_thread_id, detail in zip(thread_ids, details, strict=True):
        parsed = _parse_thread_detail(detail)
        if not parsed:
            continue
        latest = parsed[-1]
        features = aggregate_thread_features(parsed)

        result = await db.execute(
            select(Thread).where(Thread.user_id == user.id, Thread.gmail_thread_id == gmail_thread_id)
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            thread = Thread(user_id=user.id, gmail_thread_id=gmail_thread_id)
            db.add(thread)

        thread.subject = latest["headers"].get("Subject")
        thread.snippet = latest["snippet"]
        thread.sender_domain = features.get("sender_domain")
        thread.latest_internal_date = latest["internal_date"]
        thread.message_count = len(parsed)
        thread.features = features
        await db.flush()

        for m in parsed:
            existing = await db.execute(
                select(MessageLite).where(MessageLite.gmail_message_id == m["id"])
            )
            msg = existing.scalar_one_or_none()
            if msg is None:
                msg = MessageLite(thread_id=thread.id, gmail_message_id=m["id"])
                db.add(msg)
            msg.internal_date = m["internal_date"]
            msg.headers = m["headers"]

        synced += 1

    await db.commit()
    return synced
