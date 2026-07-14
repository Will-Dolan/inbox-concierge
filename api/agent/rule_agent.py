"""Cold-start rule agent for custom bucket creation.

Given only a bucket name/description, explores the inbox with tools,
proposes a DSL rule, validates its precision against a real LLM spot-check,
and either commits it (mode=deterministic) or falls back to mode=semantic.
Iteration-bounded so a bad exploration can't run away.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.tools import extract_field, filters, keyword_search, sample, semantic_search
from classify.features import thread_to_features
from core.config import get_settings
from core.dsl import RuleDSL, normalize_conditions
from core.dsl import evaluate as dsl_evaluate
from core.llm import LLMJSONError, LLMUnavailableError, complete_json, get_client, safe_create
from core.models import Bucket, Thread

MAX_ITERATIONS = 8
MAX_PROPOSALS = 3
PRECISION_BAR = 0.8
VALIDATION_SAMPLE_SIZE = 15

PROPOSE_RULE_TOOL = {
    "name": "propose_rule",
    "description": (
        "Propose a candidate DSL rule for this bucket. Triggers validation against real "
        "threads. You can call this again if a previous proposal's precision was too low - "
        "you'll see the validation feedback and near-misses to help you refine it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "logic": {"type": "string", "enum": ["AND", "OR", "NOT"]},
            "conditions": {
                "type": "array",
                "items": {"type": "object"},
                "description": "DSL condition/group objects",
            },
            "rationale": {"type": "string"},
        },
        "required": ["logic", "conditions", "rationale"],
    },
}

RECOMMEND_SEMANTIC_TOOL = {
    "name": "recommend_semantic",
    "description": (
        "Call this if no deterministic rule can reliably distinguish this bucket - it falls "
        "back to LLM-judgment (semantic) classification instead of a rule."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
    },
}

TOOLS = [
    keyword_search.TOOL_SCHEMA,
    semantic_search.TOOL_SCHEMA,
    filters.TOOL_SCHEMA,
    extract_field.TOOL_SCHEMA,
    sample.TOOL_SCHEMA,
    PROPOSE_RULE_TOOL,
    RECOMMEND_SEMANTIC_TOOL,
]

TOOL_RUNNERS = {
    "keyword_search": keyword_search.run,
    "semantic_search": semantic_search.run,
    "filter_threads": filters.run,
    "extract_field": extract_field.run,
    "sample": sample.run,
}

SYSTEM_PROMPT = """You are the Rule Agent for an email triage app. A user just created a custom \
bucket with only a name and description - your job is to find a deterministic rule (a \
combination of keyword/sender/label/header/time/extracted-field conditions) that reliably \
identifies threads belonging to this bucket, so classification is free and instant at runtime.

Explore the user's inbox with the search/filter/sample/extract_field tools to understand what \
distinguishes matching threads. When you have a hypothesis, call propose_rule with a DSL logic \
tree. You'll get back a validation precision score; if it's below the bar, refine your rule \
(tighten, loosen, or exclude a condition) and propose again - you get a few attempts. If no \
rule seems reliable after exploring, call recommend_semantic instead.

DSL condition types: keyword (any_of, fields: subject/snippet/body), sender \
(domain/email/list_id), gmail_label, header_present, time_range, extracted_field \
(op: >=/<=/>/</==/!=, value), recipient_count (op, value), is_reply (value), \
has_attachment (value). Nestable groups: \
{"type": "group", "logic": "AND"|"OR"|"NOT", "conditions": [...]}.

If the bucket is about unsubscribing, newsletters, or bulk/marketing mail, check sampled \
threads' `features.has_list_unsubscribe` first - a `header_present` condition on the exact \
header name "List-Unsubscribe" (RFC 8058) is a reliable, zero-cost signal for this and should \
usually be tried before falling back to keyword/sender heuristics."""


@dataclass
class AgentResult:
    mode: str  # "deterministic" | "semantic"
    rule: RuleDSL | None
    precision: float | None
    validated_on: int | None
    rationale: str


def _tool_result(tool_use_id: str, output: dict) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(output, default=str)}


def _call_label(name: str, tool_input: dict) -> str:
    if name == "keyword_search":
        return f'Searching threads for "{tool_input.get("query", "")}"'
    if name == "semantic_search":
        return f'Asking the LLM to judge threads matching: "{tool_input.get("query", "")}"'
    if name == "filter_threads":
        parts = [f"{k}={v}" for k, v in tool_input.items() if v and k != "limit"]
        return f"Filtering threads by {', '.join(parts)}" if parts else "Filtering threads"
    if name == "extract_field":
        return f'Extracting field "{tool_input.get("field_name", "")}" from matching threads'
    if name == "sample":
        return "Sampling threads for a closer look"
    if name == "propose_rule":
        n = len(tool_input.get("conditions", []))
        return f"Proposing rule: {tool_input.get('logic')} of {n} condition(s)"
    if name == "recommend_semantic":
        return "Recommending AI-judgment (semantic) classification instead of a rule"
    return f"Calling {name}"


def _result_label(name: str, output: object) -> str | None:
    if name in ("propose_rule", "recommend_semantic"):
        return None  # the caller emits a more specific label once validation/decision is known
    if isinstance(output, list):
        return f"Found {len(output)} matching thread(s)"
    return None


async def run_rule_agent(
    db: AsyncSession,
    user_id: uuid.UUID,
    bucket: Bucket,
    on_step: Callable[[dict], None] | None = None,
) -> AgentResult:
    settings = get_settings()
    client = get_client()

    def emit(label: str) -> None:
        if on_step is not None:
            on_step({"label": label})

    messages: list[dict] = [
        {
            "role": "user",
            "content": f"Bucket name: {bucket.name}\nDescription: {bucket.description or '(none given)'}",
        }
    ]

    proposals = 0
    last_validation: dict | None = None

    # SYSTEM_PROMPT + TOOLS are byte-identical on every one of up to
    # MAX_ITERATIONS calls in this loop (and across every bucket-creation run)
    # - cache_control on the last system block caches tools+system together,
    # so only the growing message history is billed at full price per turn.
    cached_system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    for _ in range(MAX_ITERATIONS):
        try:
            resp = await safe_create(
                client,
                model=settings.llm_model,
                max_tokens=2048,
                system=cached_system,
                tools=TOOLS,
                messages=messages,
            )
        except LLMUnavailableError as exc:
            return AgentResult(
                mode="semantic",
                rule=None,
                precision=None,
                validated_on=None,
                rationale=str(exc),
            )
        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            break  # agent stopped without proposing anything - fall through to semantic

        tool_results = []
        final: AgentResult | None = None

        for block in tool_uses:
            emit(_call_label(block.name, block.input))

            if block.name == "recommend_semantic":
                final = AgentResult(
                    mode="semantic",
                    rule=None,
                    precision=None,
                    validated_on=None,
                    rationale=block.input.get("reason", ""),
                )
                tool_results.append(_tool_result(block.id, {"ok": True}))
                continue

            if block.name == "propose_rule":
                proposals += 1
                try:
                    dsl = RuleDSL(
                        bucket_id=str(bucket.id),
                        version=proposals,
                        logic=block.input["logic"],
                        conditions=normalize_conditions(block.input["conditions"]),
                    )
                except Exception as exc:
                    emit(f"Rule proposal was invalid: {exc}")
                    tool_results.append(_tool_result(block.id, {"error": f"Invalid DSL: {exc}"}))
                    continue

                validation = await validate_rule(db, user_id, dsl, bucket)
                last_validation = validation
                cleared_bar = validation["precision"] >= PRECISION_BAR and validation["matched_count"] > 0

                if cleared_bar:
                    dsl.confidence = validation["precision"]
                    dsl.validated_on = validation["sample_size"]
                    dsl.rationale = block.input.get("rationale", "")
                    final = AgentResult(
                        mode="deterministic",
                        rule=dsl,
                        precision=validation["precision"],
                        validated_on=validation["sample_size"],
                        rationale=dsl.rationale,
                    )
                    emit(
                        f"Rule cleared the precision bar: {validation['precision'] * 100:.0f}% "
                        f"on {validation['sample_size']} samples — accepted"
                    )
                    tool_results.append(_tool_result(block.id, {**validation, "accepted": True}))
                elif proposals >= MAX_PROPOSALS:
                    final = AgentResult(
                        mode="semantic",
                        rule=None,
                        precision=validation["precision"],
                        validated_on=validation["sample_size"],
                        rationale=f"Could not clear the precision bar after {proposals} proposals.",
                    )
                    emit(
                        f"Precision {validation['precision'] * 100:.0f}% after {proposals} attempts — "
                        "falling back to AI judgment"
                    )
                    tool_results.append(_tool_result(block.id, {**validation, "accepted": False}))
                else:
                    emit(
                        f"Precision {validation['precision'] * 100:.0f}% — below bar, "
                        "agent will refine and retry"
                    )
                    tool_results.append(
                        _tool_result(
                            block.id,
                            {
                                **validation,
                                "accepted": False,
                                "hint": (
                                    "Below bar - tighten, loosen, or exclude a condition, "
                                    "then propose again."
                                ),
                            },
                        )
                    )
                continue

            runner = TOOL_RUNNERS.get(block.name)
            if runner is None:
                tool_results.append(_tool_result(block.id, {"error": "unknown tool"}))
                continue
            try:
                output = await runner(db, user_id, **block.input)
            except Exception as exc:
                output = {"error": str(exc)}
            result_label = _result_label(block.name, output)
            if result_label:
                emit(result_label)
            tool_results.append(_tool_result(block.id, output))

        messages.append({"role": "user", "content": tool_results})

        if final is not None:
            return final

    if last_validation is not None:
        return AgentResult(
            mode="semantic",
            rule=None,
            precision=last_validation["precision"],
            validated_on=last_validation["sample_size"],
            rationale="Iteration budget exhausted before clearing the precision bar.",
        )
    return AgentResult(
        mode="semantic",
        rule=None,
        precision=None,
        validated_on=None,
        rationale="Agent did not propose a rule.",
    )


async def validate_rule(
    db: AsyncSession,
    user_id: uuid.UUID,
    dsl: RuleDSL,
    bucket: Bucket,
    exclude_thread_ids: set[uuid.UUID] | None = None,
) -> dict:
    """LLM spot-check precision of `dsl` against real threads. `exclude_thread_ids`
    lets self-improvement validate a patch on the general population without
    re-asking the LLM about threads that are already ground truth (corrections)."""
    result = await db.execute(select(Thread).where(Thread.user_id == user_id))
    threads = list(result.scalars().all())
    if exclude_thread_ids:
        threads = [t for t in threads if t.id not in exclude_thread_ids]

    matches = [t for t in threads if dsl_evaluate(dsl, thread_to_features(t))]
    if not matches:
        return {"precision": 0.0, "sample_size": 0, "matched_count": 0, "near_misses": []}

    sample_threads = matches[:VALIDATION_SAMPLE_SIZE]
    verdicts = await _llm_spot_check(bucket, sample_threads)
    correct = sum(1 for v in verdicts.values() if v)
    precision = correct / len(verdicts) if verdicts else 0.0

    matched_ids = {t.id for t in matches}
    non_matches = [t for t in threads if t.id not in matched_ids][:5]

    return {
        "precision": round(precision, 3),
        "sample_size": len(verdicts),
        "matched_count": len(matches),
        "near_misses": [{"subject": t.subject, "snippet": (t.snippet or "")[:120]} for t in non_matches],
    }


_SPOT_CHECK_PROMPT = """For each email thread below, answer whether it genuinely belongs in the \
described bucket. Output strict JSON: a list of {"thread_id": "<id>", "belongs": true|false}. \
Return ONLY JSON."""


async def _llm_spot_check(bucket: Bucket, threads: list[Thread]) -> dict[str, bool]:
    payload = json.dumps(
        [{"thread_id": str(t.id), "subject": t.subject or "", "snippet": t.snippet or ""} for t in threads]
    )
    dynamic = f"Bucket: {bucket.name}\nDescription: {bucket.description or ''}"
    try:
        raw = await complete_json(
            cached_system=_SPOT_CHECK_PROMPT, dynamic_system=dynamic, user_content=payload
        )
    except (LLMJSONError, LLMUnavailableError):
        return {}

    out: dict[str, bool] = {}
    for item in raw if isinstance(raw, list) else []:
        tid = item.get("thread_id")
        if tid:
            out[tid] = bool(item.get("belongs"))
    return out
