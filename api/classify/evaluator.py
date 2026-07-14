"""Shared classification primitive: evaluate(thread_set, bucket_set).

Routes each bucket to rules_engine (deterministic, free) or semantic_eval
(semantic, batched LLM) based on its mode - a config value, not branching
logic. Persists thread_tags; source='user' rows are never touched.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from classify import rules_engine, semantic_eval
from classify.features import thread_to_features
from core.models import Bucket, Thread, ThreadTag


async def evaluate(
    db: AsyncSession, threads: list[Thread], buckets: list[Bucket], *, force: bool = False
) -> dict:
    """force=False (default, used by sync) skips any thread that already has
    at least one classification, so a sync only spends LLM calls on threads
    that have never been through the pipeline. force=True (used when a
    bucket's own config changes - mode/description/rule edits) bypasses that
    skip, since the point there is to recompute that specific bucket for
    every thread regardless of stale tags.

    The returned "matched" map (bucket name -> count of threads tagged true)
    is the signal callers use to tell the user whether an update actually
    changed anything, instead of leaving them to guess."""
    empty = {"deterministic_buckets": 0, "semantic_buckets": 0, "threads": 0, "matched": {}}
    if not threads or not buckets:
        return empty

    if not force:
        threads = await _unclassified(db, threads)
        if not threads:
            return empty

    deterministic = [b for b in buckets if b.mode == "deterministic"]
    semantic = [b for b in buckets if b.mode == "semantic"]

    matched: dict[str, int] = {}
    for bucket in deterministic:
        matches = await rules_engine.evaluate_bucket(db, threads, bucket)
        matched[bucket.name] = sum(matches.values())

    if semantic:
        # semantic_eval.evaluate_many is a pure judgment call (no persistence, by
        # design - see classify/semantic_eval.py); persist it here, symmetric to
        # rules_engine.evaluate_bucket's own persistence.
        features_by_id = {t.id: thread_to_features(t) for t in threads}
        tag_map = await semantic_eval.evaluate_many(features_by_id, semantic)
        await _persist_semantic_tags(db, tag_map, semantic)
        for bucket in semantic:
            matched[bucket.name] = sum(1 for tags in tag_map.values() if bucket.name in tags)

    return {
        "deterministic_buckets": len(deterministic),
        "semantic_buckets": len(semantic),
        "threads": len(threads),
        "matched": matched,
    }


async def _unclassified(db: AsyncSession, threads: list[Thread]) -> list[Thread]:
    """Threads with zero thread_tags rows (any bucket, any source) - i.e.
    never run through evaluate() before."""
    result = await db.execute(
        select(ThreadTag.thread_id)
        .where(ThreadTag.thread_id.in_([t.id for t in threads]))
        .distinct()
    )
    classified_ids = {row[0] for row in result.all()}
    return [t for t in threads if t.id not in classified_ids]


async def _persist_semantic_tags(
    db: AsyncSession, tag_map: dict[uuid.UUID, list[str]], semantic_buckets: list[Bucket]
) -> None:
    """Threads/buckets the user has already corrected (source='user') are
    skipped entirely - never deleted, never re-inserted (decisions #7, #11)."""
    bucket_ids = [b.id for b in semantic_buckets]
    bucket_by_name = {b.name: b for b in semantic_buckets}

    corrected_result = await db.execute(
        select(ThreadTag.thread_id, ThreadTag.bucket_id).where(
            ThreadTag.bucket_id.in_(bucket_ids), ThreadTag.source == "user"
        )
    )
    corrected_pairs = {(row.thread_id, row.bucket_id) for row in corrected_result.all()}

    for thread_id, tag_names in tag_map.items():
        touchable_bucket_ids = [bid for bid in bucket_ids if (thread_id, bid) not in corrected_pairs]
        if not touchable_bucket_ids:
            continue
        await db.execute(
            delete(ThreadTag).where(
                ThreadTag.thread_id == thread_id,
                ThreadTag.source != "user",
                ThreadTag.bucket_id.in_(touchable_bucket_ids),
            )
        )
        for name in tag_names:
            bucket = bucket_by_name.get(name)
            if bucket is not None and (thread_id, bucket.id) not in corrected_pairs:
                db.add(ThreadTag(thread_id=thread_id, bucket_id=bucket.id, source="llm"))
    await db.commit()
