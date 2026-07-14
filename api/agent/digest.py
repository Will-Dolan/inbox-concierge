"""Morning digest: one LLM call summarizing a single bucket's threads.

Scoped to whichever bucket the user has open - "worth knowing about" means
something different for every bucket, not just a hardcoded "Can Wait".

Cached in the digests table, one row per bucket - opening the panel (or
reloading the page) reads the cached digest instead of re-running the LLM;
only an explicit refresh (force=True) regenerates it."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.llm import LLMUnavailableError, get_client, safe_create
from core.models import Bucket, Digest, Thread, ThreadTag

_SYSTEM_PROMPT = """You are writing a short digest of one bucket in a user's email triage app. \
Below are threads currently in that bucket, plus its name/description for context. Write a \
brief, friendly digest (a short paragraph or a few bullet points) grouping related items and \
calling out anything time-sensitive. Do not invent details that aren't in the list below. Keep \
it under 150 words.

Formatting: plain markdown only (paragraphs, "-" bullet lists, **bold**, *italics*) - no title/ \
heading lines (no "#"), and no emojis."""

MAX_THREADS = 40


async def generate_digest(
    db: AsyncSession, user_id: uuid.UUID, bucket_id: uuid.UUID, force: bool = False
) -> dict:
    bucket = await db.get(Bucket, bucket_id)
    if bucket is None or (bucket.user_id is not None and bucket.user_id != user_id):
        return {"digest": "Bucket not found.", "generated_at": None}

    cached = await db.get(Digest, bucket_id)
    if cached is not None and not force:
        return {"digest": cached.text, "generated_at": cached.generated_at.isoformat()}

    threads_result = await db.execute(
        select(Thread)
        .join(ThreadTag, ThreadTag.thread_id == Thread.id)
        .where(
            ThreadTag.bucket_id == bucket.id,
            ThreadTag.value.is_(True),
            Thread.user_id == user_id,
        )
        .order_by(Thread.latest_internal_date.desc())
        .limit(MAX_THREADS)
    )
    threads = threads_result.scalars().all()
    if not threads:
        return {
            "digest": f'Nothing in "{bucket.name}" right now — you\'re all caught up.',
            "generated_at": None,
        }

    lines = [
        f"- {t.subject or '(no subject)'} from {t.sender_domain or 'unknown sender'}: "
        f"{(t.snippet or '')[:200]}"
        for t in threads
    ]
    header = f"Bucket: {bucket.name}\nDescription: {bucket.description or '(none)'}"

    settings = get_settings()
    client = get_client()
    try:
        resp = await safe_create(
            client,
            model=settings.llm_model,
            max_tokens=512,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"{header}\n\n" + "\n".join(lines)}],
        )
    except LLMUnavailableError as exc:
        return {"digest": str(exc), "generated_at": None}

    text = "".join(block.text for block in resp.content if block.type == "text").strip()

    if cached is None:
        cached = Digest(bucket_id=bucket_id, text=text)
        db.add(cached)
    else:
        cached.text = text
    await db.commit()
    await db.refresh(cached)

    return {"digest": text, "generated_at": cached.generated_at.isoformat()}
