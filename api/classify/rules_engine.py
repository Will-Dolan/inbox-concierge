"""Deterministic buckets: DSL rule evaluated in-process. Zero marginal cost.

Implements the same evaluate(thread_features, bucket) -> bool interface as
classify/semantic_eval.py so per-bucket mode is a config value, not branching
logic.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from classify.features import thread_to_features
from core.dsl import RuleDSL, ThreadFeatures
from core.dsl import evaluate as dsl_evaluate
from core.models import Bucket, Rule, Thread, ThreadTag


async def _get_active_rule(db: AsyncSession, bucket_id: uuid.UUID) -> Rule | None:
    result = await db.execute(
        select(Rule)
        .where(Rule.bucket_id == bucket_id, Rule.active.is_(True))
        .order_by(Rule.version.desc())
    )
    return result.scalars().first()


async def evaluate(db: AsyncSession, tf: ThreadFeatures, bucket: Bucket) -> bool:
    """Single (thread, bucket) check - the shared interface. Read-only, no
    persistence. Prefer evaluate_bucket() for many threads against one rule."""
    rule = await _get_active_rule(db, bucket.id)
    if rule is None:
        return False
    return dsl_evaluate(RuleDSL.model_validate(rule.dsl), tf)


async def evaluate_bucket(
    db: AsyncSession, threads: list[Thread], bucket: Bucket
) -> dict[uuid.UUID, bool]:
    """Evaluate one deterministic bucket's active rule against many threads at
    zero marginal cost. Upserts thread_tags (source='agent_rule'). Threads the
    user has already corrected (source='user') are skipped entirely - their
    tag is never touched (decisions #7, #11)."""
    rule = await _get_active_rule(db, bucket.id)
    if rule is None:
        return dict.fromkeys((t.id for t in threads), False)

    corrected_result = await db.execute(
        select(ThreadTag.thread_id).where(ThreadTag.bucket_id == bucket.id, ThreadTag.source == "user")
    )
    corrected_ids = {row[0] for row in corrected_result.all()}

    dsl = RuleDSL.model_validate(rule.dsl)
    evaluable = [t for t in threads if t.id not in corrected_ids]
    matches = {t.id: dsl_evaluate(dsl, thread_to_features(t)) for t in evaluable}

    await db.execute(
        delete(ThreadTag).where(
            ThreadTag.bucket_id == bucket.id,
            ThreadTag.source != "user",
            ThreadTag.thread_id.in_([t.id for t in evaluable]),
        )
    )
    for thread_id, matched in matches.items():
        if matched:
            db.add(ThreadTag(thread_id=thread_id, bucket_id=bucket.id, source="agent_rule"))
    await db.commit()
    return matches
