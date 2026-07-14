"""Default buckets ship hand-authored (decision #12) - no agent run at first login."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.dsl import RuleDSL
from core.models import Bucket, Rule

DEFAULT_BUCKETS = [
    {
        "name": "Newsletter",
        "description": "Bulk or marketing email you're subscribed to - carries a List-Unsubscribe header.",
        "mode": "deterministic",
    },
    {
        "name": "Important",
        "description": (
            "Needs your attention soon: direct requests, deadlines, personal correspondence, "
            "anything actionable."
        ),
        "mode": "semantic",
        "mode_rationale": (
            "What counts as \"needs attention\" depends on tone and context, not just keywords or "
            "sender - an LLM judges each thread individually against this description."
        ),
    },
    {
        "name": "Can Wait",
        "description": (
            "Not urgent but worth reading eventually: FYIs, receipts, non-time-sensitive updates."
        ),
        "mode": "semantic",
        "mode_rationale": (
            "Urgency is contextual and can't be captured by a fixed rule - an LLM judges each "
            "thread individually against this description."
        ),
    },
    {
        "name": "Auto-archive",
        "description": (
            "Low-value automated notifications, promotions, or noise safe to ignore or archive."
        ),
        "mode": "semantic",
        "mode_rationale": (
            "\"Low-value\" varies by sender and content, not a fixed pattern - an LLM judges each "
            "thread individually against this description."
        ),
    },
]


async def ensure_default_buckets(db: AsyncSession) -> list[Bucket]:
    result = await db.execute(select(Bucket).where(Bucket.kind == "system"))
    existing = {b.name: b for b in result.scalars().all()}

    buckets: list[Bucket] = []
    for spec in DEFAULT_BUCKETS:
        bucket = existing.get(spec["name"])
        if bucket is None:
            bucket = Bucket(
                user_id=None,
                name=spec["name"],
                description=spec["description"],
                kind="system",
                mode=spec["mode"],
                mode_source="default",
                mode_rationale=spec.get("mode_rationale"),
            )
            db.add(bucket)
            await db.flush()
        buckets.append(bucket)

    newsletter = next(b for b in buckets if b.name == "Newsletter")
    rule_result = await db.execute(select(Rule).where(Rule.bucket_id == newsletter.id))
    if rule_result.scalar_one_or_none() is None:
        dsl = RuleDSL(
            bucket_id=str(newsletter.id),
            version=1,
            logic="AND",
            conditions=[{"type": "header_present", "header": "List-Unsubscribe"}],
            confidence=1.0,
            rationale="RFC 8058 List-Unsubscribe header present.",
        )
        db.add(
            Rule(
                bucket_id=newsletter.id,
                version=1,
                dsl=dsl.model_dump(mode="json"),
                confidence=1.0,
                rationale=dsl.rationale,
                source="hand",
                active=True,
            )
        )

    await db.commit()
    return buckets
