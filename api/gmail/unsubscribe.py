"""Mass unsubscribe: group a bucket's threads by sender domain.

Classify each group by unsubscribe method using the List-Unsubscribe /
List-Unsubscribe-Post headers already captured during sync (RFC 2369/8058 -
the same headers Gmail's own "Unsubscribe" chip reads, not scraped from the
email body), and let the caller bulk-execute the automatable ones (RFC 8058
one-click POST) while handing off manual mailto:/link candidates.

Scoped to one bucket at a time - not every bucket's senders are bulk mail
with an unsubscribe header, so this only ever surfaces the subset of a
bucket's threads that actually have one."""

import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import Thread, ThreadTag

_HTTP_RE = re.compile(r"<(https?://[^>]+)>")
_MAILTO_RE = re.compile(r"<mailto:([^>]+)>")


def _parse_unsubscribe(headers: dict) -> dict | None:
    list_unsub = headers.get("List-Unsubscribe")
    if not list_unsub:
        return None

    one_click = "one-click" in headers.get("List-Unsubscribe-Post", "").lower()
    http_match = _HTTP_RE.search(list_unsub)
    mailto_match = _MAILTO_RE.search(list_unsub)

    if http_match and one_click:
        return {"method": "one_click", "url": http_match.group(1)}
    if http_match:
        return {"method": "link", "url": http_match.group(1)}
    if mailto_match:
        return {"method": "mailto", "url": f"mailto:{mailto_match.group(1)}"}
    return None


async def _candidates_by_domain(
    db: AsyncSession, user_id: uuid.UUID, bucket_id: uuid.UUID
) -> dict[str, dict]:
    result = await db.execute(
        select(Thread)
        .join(ThreadTag, ThreadTag.thread_id == Thread.id)
        .where(
            ThreadTag.bucket_id == bucket_id,
            ThreadTag.value.is_(True),
            Thread.user_id == user_id,
        )
        .options(selectinload(Thread.messages))
    )
    threads = result.scalars().unique().all()

    by_domain: dict[str, dict] = {}
    for t in threads:
        if not t.messages:
            continue
        latest = max(t.messages, key=lambda m: m.internal_date)
        info = _parse_unsubscribe(latest.headers)
        if info is None or not t.sender_domain:
            continue

        domain = t.sender_domain
        entry = by_domain.get(domain)
        if entry is None:
            by_domain[domain] = {"sender_domain": domain, "thread_count": 1, **info}
        else:
            entry["thread_count"] += 1

    return by_domain


async def list_candidates(db: AsyncSession, user_id: uuid.UUID, bucket_id: uuid.UUID) -> list[dict]:
    by_domain = await _candidates_by_domain(db, user_id, bucket_id)
    return sorted(by_domain.values(), key=lambda e: e["thread_count"], reverse=True)


async def get_one_click_url(
    db: AsyncSession, user_id: uuid.UUID, bucket_id: uuid.UUID, sender_domain: str
) -> str | None:
    """Re-derive the one-click unsubscribe URL for a user's own thread data.

    Never trust a client-supplied URL for the actual outbound POST - always
    recompute it server-side from this user's bucket/thread headers so the
    server can only ever hit a target it derived itself (SSRF prevention).
    """
    by_domain = await _candidates_by_domain(db, user_id, bucket_id)
    entry = by_domain.get(sender_domain)
    if entry is None or entry.get("method") != "one_click":
        return None
    return entry["url"]


async def execute_one_click(url: str) -> bool:
    """RFC 8058 one-click unsubscribe: POST body 'List-Unsubscribe=One-Click'."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, data={"List-Unsubscribe": "One-Click"})
        return resp.status_code < 400
