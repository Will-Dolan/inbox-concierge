import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.rule_agent import AgentResult, run_rule_agent
from classify.evaluator import evaluate as evaluator_evaluate
from core.db import async_session_factory, get_db
from core.deps import get_current_user
from core.dsl import RuleDSL, describe_rule, normalize_conditions
from core.models import Bucket, Rule, Thread, User
from core.queue import queue

router = APIRouter(tags=["buckets"])


class CreateBucketRequest(BaseModel):
    name: str
    description: str | None = None
    classifier: Literal["llm", "rules"] = "rules"


class UpdateBucketRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    mode: Literal["deterministic", "semantic"] | None = None


class RuleUpdateRequest(BaseModel):
    logic: Literal["AND", "OR", "NOT"] = "AND"
    conditions: list[dict]


async def _active_rule(db: AsyncSession, bucket_id: uuid.UUID) -> Rule | None:
    result = await db.execute(
        select(Rule).where(Rule.bucket_id == bucket_id, Rule.active.is_(True)).order_by(Rule.version.desc())
    )
    return result.scalars().first()


async def _visible_bucket_with_name(
    db: AsyncSession, user_id: uuid.UUID, name: str, *, exclude_bucket_id: uuid.UUID | None = None
) -> Bucket | None:
    query = select(Bucket).where(
        ((Bucket.user_id == user_id) | (Bucket.user_id.is_(None))),
        func.lower(Bucket.name) == name.lower(),
    )
    if exclude_bucket_id is not None:
        query = query.where(Bucket.id != exclude_bucket_id)
    result = await db.execute(query)
    return result.scalars().first()


@router.get("/buckets")
async def list_buckets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(select(Bucket).where((Bucket.user_id == user.id) | (Bucket.user_id.is_(None))))
    buckets = result.scalars().all()

    out = []
    for b in buckets:
        rule = await _active_rule(db, b.id) if b.mode == "deterministic" else None
        out.append(
            {
                "id": str(b.id),
                "name": b.name,
                "description": b.description,
                "kind": b.kind,
                "mode": b.mode,
                "mode_source": b.mode_source,
                "rule_confidence": rule.confidence if rule else None,
                "rule_rationale": rule.rationale if rule else None,
                "rule_version": rule.version if rule else None,
                "rule_summary": describe_rule(rule.dsl) if rule else None,
                "rule_logic": rule.dsl.get("logic") if rule else None,
                "rule_conditions": rule.dsl.get("conditions") if rule else None,
                "mode_rationale": b.mode_rationale,
            }
        )
    return out


@router.delete("/buckets/{bucket_id}", status_code=204)
async def delete_bucket(
    bucket_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    bucket = await db.get(Bucket, bucket_id)
    if bucket is None or (bucket.user_id is not None and bucket.user_id != user.id):
        raise HTTPException(404, "bucket not found")
    if bucket.kind == "system":
        raise HTTPException(400, "default buckets can't be deleted")
    await db.delete(bucket)
    await db.commit()


@router.put("/buckets/{bucket_id}/rule")
async def update_rule(
    bucket_id: uuid.UUID,
    body: RuleUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Allow direct rule edits without going through the agent.

    Always creates a new version and deactivates the old one, same as
    self-improve, so a bad manual edit can be traced/rolled back.
    """
    bucket = await db.get(Bucket, bucket_id)
    if bucket is None or (bucket.user_id is not None and bucket.user_id != user.id):
        raise HTTPException(404, "bucket not found")
    if not body.conditions:
        raise HTTPException(400, "rule needs at least one condition")

    prev = await _active_rule(db, bucket_id)
    version = (prev.version + 1) if prev else 1
    try:
        dsl = RuleDSL(
            bucket_id=str(bucket_id),
            version=version,
            logic=body.logic,
            conditions=normalize_conditions(body.conditions),
        )
    except Exception as exc:
        raise HTTPException(400, f"Invalid rule: {exc}") from exc

    if prev is not None:
        prev.active = False

    db.add(
        Rule(
            bucket_id=bucket_id,
            version=version,
            dsl=dsl.model_dump(mode="json"),
            confidence=prev.confidence if prev else None,
            validated_on=prev.validated_on if prev else None,
            rationale="Edited by user",
            source="user",
            active=True,
        )
    )
    bucket.mode = "deterministic"
    bucket.mode_source = "user"
    bucket.mode_rationale = None
    await db.commit()

    threads = (await db.execute(select(Thread).where(Thread.user_id == user.id))).scalars().all()
    result = await evaluator_evaluate(db, list(threads), [bucket], force=True)

    return {
        "id": str(bucket.id),
        "rule_version": version,
        "matched": result["matched"].get(bucket.name, 0),
        "evaluated": result["threads"],
    }


@router.patch("/buckets/{bucket_id}")
async def update_bucket(
    bucket_id: uuid.UUID,
    body: UpdateBucketRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    bucket = await db.get(Bucket, bucket_id)
    if bucket is None or (bucket.user_id is not None and bucket.user_id != user.id):
        raise HTTPException(404, "bucket not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "bucket name is required")
        existing = await _visible_bucket_with_name(db, user.id, name, exclude_bucket_id=bucket.id)
        if existing is not None:
            raise HTTPException(409, "bucket name already exists")
        bucket.name = name

    description_changed = body.description is not None and body.description != bucket.description
    if description_changed:
        bucket.description = body.description

    mode_changed = body.mode is not None and body.mode != bucket.mode
    if mode_changed:
        bucket.mode = body.mode
        bucket.mode_source = "user"
        bucket.mode_rationale = "Switched to AI judgment by you." if body.mode == "semantic" else None

    semantic_eval_needed = (mode_changed and bucket.mode == "semantic") or (
        description_changed and bucket.mode == "semantic"
    )
    if semantic_eval_needed:
        await db.commit()
        user_id = user.id
        queued_bucket_id = bucket.id

        async def run() -> dict:
            async with async_session_factory() as session:
                fresh_bucket = await session.get(Bucket, queued_bucket_id)
                threads = (
                    (await session.execute(select(Thread).where(Thread.user_id == user_id)))
                    .scalars()
                    .all()
                )
                result = await evaluator_evaluate(session, list(threads), [fresh_bucket], force=True)
                return {
                    "bucket_id": str(queued_bucket_id),
                    "matched": result["matched"].get(fresh_bucket.name, 0),
                    "evaluated": result["threads"],
                }

        job_id = queue.enqueue(run, user_id)
        return {
            "id": str(bucket.id),
            "mode": bucket.mode,
            "mode_source": bucket.mode_source,
            "description": bucket.description,
            "classification_job_id": job_id,
        }

    if mode_changed:
        threads = (await db.execute(select(Thread).where(Thread.user_id == user.id))).scalars().all()
        await db.commit()
        result = await evaluator_evaluate(db, list(threads), [bucket], force=True)
        return {
            "id": str(bucket.id),
            "mode": bucket.mode,
            "mode_source": bucket.mode_source,
            "description": bucket.description,
            "matched": result["matched"].get(bucket.name, 0),
            "evaluated": result["threads"],
        }

    await db.commit()
    return {"id": str(bucket.id), "name": bucket.name, "description": bucket.description}


@router.post("/buckets", status_code=202)
async def create_bucket(
    body: CreateBucketRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "bucket name is required")
    existing = await _visible_bucket_with_name(db, user.id, name)
    if existing is not None:
        raise HTTPException(409, "bucket name already exists")

    bucket = Bucket(
        user_id=user.id,
        name=name,
        description=body.description,
        kind="custom",
        mode="semantic",  # placeholder until the agent decides; always classifiable in the meantime
        mode_source="agent",
    )
    db.add(bucket)
    await db.commit()
    await db.refresh(bucket)

    bucket_id = bucket.id
    user_id = user.id
    classifier = body.classifier
    job_id = queue.reserve(user_id)

    async def run() -> dict:
        async with async_session_factory() as session:
            fresh_bucket = await session.get(Bucket, bucket_id)

            if classifier == "llm":
                # User explicitly wants AI-judgment classification - skip the rule
                # agent's inbox exploration entirely rather than have it search for
                # a deterministic rule nobody asked for.
                queue.push_progress(job_id, {"label": "Setting up AI-judgment classification"})
                agent_result = AgentResult(
                    mode="semantic",
                    rule=None,
                    precision=None,
                    validated_on=None,
                    rationale="Set to AI judgment by you.",
                )
            else:
                agent_result = await run_rule_agent(
                    session,
                    user_id,
                    fresh_bucket,
                    on_step=lambda event: queue.push_progress(job_id, event),
                )

            if agent_result.mode == "deterministic" and agent_result.rule is not None:
                session.add(
                    Rule(
                        bucket_id=bucket_id,
                        version=1,
                        dsl=agent_result.rule.model_dump(mode="json"),
                        confidence=agent_result.precision,
                        validated_on=agent_result.validated_on,
                        rationale=agent_result.rationale,
                        source="agent",
                        active=True,
                    )
                )
                fresh_bucket.mode = "deterministic"
                fresh_bucket.mode_rationale = None
            else:
                fresh_bucket.mode = "semantic"
                fresh_bucket.mode_rationale = agent_result.rationale
            fresh_bucket.mode_source = "user" if classifier == "llm" else "agent"
            await session.commit()

            threads = (
                (await session.execute(select(Thread).where(Thread.user_id == user_id))).scalars().all()
            )
            result = await evaluator_evaluate(session, list(threads), [fresh_bucket], force=True)

            return {
                "bucket_id": str(bucket_id),
                "mode": fresh_bucket.mode,
                "precision": agent_result.precision,
                "validated_on": agent_result.validated_on,
                "rationale": agent_result.rationale,
                "matched": result["matched"].get(fresh_bucket.name, 0),
                "evaluated": result["threads"],
            }

    queue.start(job_id, run)
    return {"bucket_id": str(bucket.id), "job_id": job_id}
