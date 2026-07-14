"""LLM-ranked semantic search over subject+snippet.

Pluggable: swap for real embeddings (pgvector) later without changing the
tool's interface.
"""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm import LLMJSONError, LLMUnavailableError, complete_json
from core.models import Thread

# Caps the corpus sent to the ranking call - the rule agent can invoke this
# tool several times per exploration run, so an unbounded thread set here
# means re-sending (and re-billing) the same large payload repeatedly.
MAX_CANDIDATES = 300

TOOL_SCHEMA = {
    "name": "semantic_search",
    "description": (
        "Find threads semantically related to a natural-language query, even if they don't "
        "share exact keywords (e.g. 'shipping notifications' should also find "
        "'your package has left the warehouse')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
}

_RANK_PROMPT = """Given a search query and a list of email threads (id, subject, snippet), \
return the thread_ids of the threads most semantically relevant to the query, best first.

Output strict JSON: {"thread_ids": ["<id>", ...]}. Return ONLY JSON."""


async def run(db: AsyncSession, user_id: uuid.UUID, query: str, k: int = 10) -> list[dict]:
    result = await db.execute(
        select(Thread)
        .where(Thread.user_id == user_id)
        .order_by(Thread.latest_internal_date.desc())
        .limit(MAX_CANDIDATES)
    )
    threads = result.scalars().all()
    if not threads:
        return []

    candidates = [
        {"thread_id": str(t.id), "subject": t.subject or "", "snippet": (t.snippet or "")[:200]}
        for t in threads
    ]
    user_content = json.dumps({"query": query, "k": k, "threads": candidates})
    try:
        raw = await complete_json(cached_system=_RANK_PROMPT, user_content=user_content)
    except (LLMJSONError, LLMUnavailableError):
        return []

    ranked_ids = raw.get("thread_ids", [])[:k] if isinstance(raw, dict) else []
    by_id = {str(t.id): t for t in threads}
    return [_summary(by_id[tid]) for tid in ranked_ids if tid in by_id]


def _summary(t: Thread) -> dict:
    return {
        "thread_id": str(t.id),
        "subject": t.subject,
        "snippet": t.snippet,
        "sender_domain": t.sender_domain,
    }
