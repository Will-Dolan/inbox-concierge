"""Self-improvement: patch an existing deterministic rule using accumulated
user corrections as ground truth.

Pulls false positives/negatives from corrections, reasons about the failure
pattern in one targeted LLM call (no open-ended tool exploration needed -
the mistakes are already concrete), proposes a patched rule, and only
deploys it if it agrees with every correction *and* still clears the
general precision bar. Old rule versions are kept (active=False) for
rollback.
"""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.rule_agent import validate_rule
from classify.features import thread_to_features
from core.dsl import RuleDSL, normalize_conditions
from core.dsl import evaluate as dsl_evaluate
from core.llm import LLMJSONError, LLMUnavailableError, complete_json
from core.models import Bucket, Rule, Thread, ThreadTag

MIN_CORRECTIONS_TO_TRIGGER = 2
PRECISION_BAR = 0.8

_PATCH_PROMPT = """You are patching an email triage rule using real user corrections as ground \
truth. You'll be given the current DSL rule and two sets of mistakes:
- false_positives: threads the rule currently matches, but the user says do NOT belong
- false_negatives: threads the rule currently misses, but the user says DO belong

Propose a revised DSL rule that fixes these mistakes. Each example includes subject, snippet, \
sender_domain, and gmail_labels - the fix might need to loosen or tighten ANY of these signals, \
not just keywords (e.g. a false_negative from a different sender_domain likely means the sender \
condition itself needs to change, not the keywords). Use the same DSL condition types \
(keyword, sender, gmail_label, header_present, time_range, extracted_field, recipient_count, \
is_reply, has_attachment) composed via nestable AND/OR/NOT groups.

Output strict JSON with EXACTLY these top-level keys, not nested under any other key:
{"logic": "AND"|"OR"|"NOT", "conditions": [...], "rationale": "<why this fixes it>"}

Return ONLY that JSON object - no prose, no markdown fences."""


async def _active_rule(db: AsyncSession, bucket_id: uuid.UUID) -> Rule | None:
    result = await db.execute(
        select(Rule).where(Rule.bucket_id == bucket_id, Rule.active.is_(True)).order_by(Rule.version.desc())
    )
    return result.scalars().first()


async def improve_bucket(db: AsyncSession, user_id: uuid.UUID, bucket: Bucket) -> dict:
    """No-ops (changed=False) if there's nothing to fix or the bucket has no
    active deterministic rule yet. Otherwise proposes, validates, and - if
    it clears the bar - deploys a patched rule version."""
    active_rule = await _active_rule(db, bucket.id)
    if bucket.mode != "deterministic" or active_rule is None:
        return {"changed": False, "reason": "bucket has no active deterministic rule"}

    corrections_result = await db.execute(
        select(ThreadTag, Thread)
        .join(Thread, Thread.id == ThreadTag.thread_id)
        .where(ThreadTag.bucket_id == bucket.id, ThreadTag.source == "user")
    )
    corrections = corrections_result.all()
    if len(corrections) < MIN_CORRECTIONS_TO_TRIGGER:
        return {"changed": False, "reason": "not enough corrections yet"}

    current_dsl = RuleDSL.model_validate(active_rule.dsl)

    false_positives: list[Thread] = []
    false_negatives: list[Thread] = []
    for tag, thread in corrections:
        rule_says_match = dsl_evaluate(current_dsl, thread_to_features(thread))
        if rule_says_match and not tag.value:
            false_positives.append(thread)
        elif not rule_says_match and tag.value:
            false_negatives.append(thread)

    if not false_positives and not false_negatives:
        return {"changed": False, "reason": "current rule already agrees with all corrections"}

    def _describe(t: Thread) -> dict:
        return {
            "subject": t.subject,
            "snippet": t.snippet,
            "sender_domain": t.sender_domain,
            "gmail_labels": (t.features or {}).get("gmail_labels", []),
        }

    payload = json.dumps(
        {
            "current_rule": current_dsl.model_dump(mode="json", include={"logic", "conditions"}),
            "false_positives": [_describe(t) for t in false_positives],
            "false_negatives": [_describe(t) for t in false_negatives],
        }
    )

    try:
        raw = await complete_json(cached_system=_PATCH_PROMPT, user_content=payload)
    except LLMJSONError:
        return {"changed": False, "reason": "LLM failed to propose a patch"}
    except LLMUnavailableError as exc:
        return {"changed": False, "reason": str(exc)}

    try:
        new_dsl = RuleDSL(
            bucket_id=str(bucket.id),
            version=active_rule.version + 1,
            logic=raw["logic"],
            conditions=normalize_conditions(raw["conditions"]),
        )
    except Exception as exc:
        return {"changed": False, "reason": f"invalid patched DSL: {exc}"}

    for tag, thread in corrections:
        if dsl_evaluate(new_dsl, thread_to_features(thread)) != tag.value:
            return {"changed": False, "reason": "patched rule still disagrees with a correction"}

    correction_thread_ids = {t.id for _, t in corrections}
    validation = await validate_rule(db, user_id, new_dsl, bucket, exclude_thread_ids=correction_thread_ids)
    if validation["precision"] < PRECISION_BAR:
        return {"changed": False, "reason": f"patched rule precision {validation['precision']} below bar"}

    new_dsl.confidence = validation["precision"]
    new_dsl.validated_on = validation["sample_size"]
    new_dsl.rationale = raw.get("rationale", "")

    active_rule.active = False
    db.add(
        Rule(
            bucket_id=bucket.id,
            version=new_dsl.version,
            dsl=new_dsl.model_dump(mode="json"),
            confidence=new_dsl.confidence,
            validated_on=new_dsl.validated_on,
            rationale=new_dsl.rationale,
            source="agent",
            active=True,
        )
    )
    await db.commit()

    return {
        "changed": True,
        "new_version": new_dsl.version,
        "precision": new_dsl.confidence,
        "fixed_false_positives": len(false_positives),
        "fixed_false_negatives": len(false_negatives),
        "rationale": new_dsl.rationale,
    }
