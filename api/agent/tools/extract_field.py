"""Regex-first field extraction; batched LLM fallback for ambiguity.

Cached in extracted_fields - computed once per (thread, field), reused by any
rule forever.
"""

import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm import LLMJSONError, LLMUnavailableError, complete_json
from core.models import ExtractedField, Thread

TOOL_SCHEMA = {
    "name": "extract_field",
    "description": (
        "Extract a structured field (e.g. 'amount', 'date_mentioned', or any other field name) "
        "from a set of threads. Cached - free on repeat calls for the same threads/field."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thread_ids": {"type": "array", "items": {"type": "string"}},
            "field": {"type": "string"},
        },
        "required": ["thread_ids", "field"],
    },
}

_AMOUNT_RE = re.compile(r"\$\s?([\d,]+\.\d{2}|\d+)")
_DATE_RE = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]{2,8}\s+\d{1,2}(st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2})\b"
)

_LLM_EXTRACT_PROMPT = """Extract the requested field from each email thread's subject and preview. \
If the field isn't present, use null.

Output strict JSON: a list of {"thread_id": "<id>", "value": <value or null>}. Return ONLY JSON."""


def _regex_extract(field: str, text: str) -> object | None:
    if field == "amount":
        m = _AMOUNT_RE.search(text)
        return float(m.group(1).replace(",", "")) if m else None
    if field == "date_mentioned":
        m = _DATE_RE.search(text)
        return m.group(0) if m else None
    return None


async def run(db: AsyncSession, user_id: uuid.UUID, thread_ids: list[str], field: str) -> dict[str, object]:
    ids = [uuid.UUID(tid) for tid in thread_ids]
    existing = await db.execute(
        select(ExtractedField).where(ExtractedField.thread_id.in_(ids), ExtractedField.field == field)
    )
    cached: dict[str, object] = {str(row.thread_id): row.value for row in existing.scalars().all()}

    missing_ids = [i for i in ids if str(i) not in cached]
    if not missing_ids:
        return cached

    result = await db.execute(select(Thread).where(Thread.id.in_(missing_ids)))
    threads = {t.id: t for t in result.scalars().all()}

    llm_candidates = []
    for tid in missing_ids:
        t = threads.get(tid)
        if t is None:
            continue
        text = f"{t.subject or ''} {t.snippet or ''}"
        value = _regex_extract(field, text)
        if value is not None:
            db.add(ExtractedField(thread_id=tid, field=field, value=value, extractor="regex"))
            cached[str(tid)] = value
        else:
            llm_candidates.append(t)

    if llm_candidates:
        payload = json.dumps(
            [
                {"thread_id": str(t.id), "subject": t.subject or "", "snippet": t.snippet or ""}
                for t in llm_candidates
            ]
        )
        try:
            raw = await complete_json(
                cached_system=_LLM_EXTRACT_PROMPT,
                dynamic_system=f"Field to extract: {field}",
                user_content=payload,
            )
        except (LLMJSONError, LLMUnavailableError):
            raw = []
        for item in raw if isinstance(raw, list) else []:
            tid_str = item.get("thread_id")
            value = item.get("value")
            if tid_str is None:
                continue
            if value is not None:
                db.add(
                    ExtractedField(
                        thread_id=uuid.UUID(tid_str), field=field, value=value, extractor="llm"
                    )
                )
            cached[tid_str] = value

    await db.commit()
    return cached
