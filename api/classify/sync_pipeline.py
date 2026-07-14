"""Sync-triggered classification (section 7): classify whatever the sync job
just pulled in against every default bucket.

Threads that already have any classification are skipped (see
classify/evaluator.py's force=False default) so a sync only pays for LLM
calls on genuinely new threads, not the whole 200-thread window every time.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from classify.evaluator import evaluate
from core.models import Bucket, Thread


async def classify_new_threads(db: AsyncSession, threads: list[Thread], buckets: list[Bucket]) -> int:
    result = await evaluate(db, threads, buckets)
    return result["threads"]
