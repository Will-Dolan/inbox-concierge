"""Semantic buckets: one batched LLM call per thread-batch judging all
semantic buckets at once (never one call per bucket per thread).

Implements the same evaluate(thread_features, bucket) -> bool interface as
classify/rules_engine.py (decision #5). Operates on ThreadFeatures, not the
ORM, so a different implementation (embeddings, sentiment) can swap in later
without redesigning callers (decision #3).
"""

import asyncio
import json
import uuid

from core.dsl import ThreadFeatures
from core.llm import LLMJSONError, LLMUnavailableError, complete_json
from core.models import Bucket

BATCH_SIZE = 60

STATIC_PROMPT_PREFIX = """You are an email triage assistant for an inbox app.

Classify each email thread into zero or more of the provided buckets, based on \
its subject, preview, sender, Gmail labels, and unsubscribe signal.

Rules:
- A thread may belong to multiple buckets, or none (return an empty tags list \
  if nothing fits - never invent a catch-all bucket).
- Only use the bucket names given to you; never invent new ones.
- Weigh the bucket's description, not just its name.
- has_unsubscribe_link is true when the message carries a List-Unsubscribe \
  header (RFC 8058) - a strong, reliable signal for newsletters, marketing \
  email, and anything else described as unsubscribable.

Output strict JSON: a list of objects, one per input thread, each shaped exactly as:
{"thread_id": "<id>", "tags": ["<bucket name>", ...]}

Return ONLY the JSON array - no prose, no markdown fences, one entry per thread_id given."""

# Cheap, LLM-free fallback so a batch failure never leaves the UI with a hole.
_GMAIL_CATEGORY_FALLBACK = {
    "CATEGORY_PROMOTIONS": "Auto-archive",
    "CATEGORY_FORUMS": "Auto-archive",
    "CATEGORY_UPDATES": "Can Wait",
    "IMPORTANT": "Important",
}


def _thread_payload(thread_id: uuid.UUID, tf: ThreadFeatures) -> dict:
    headers_lower = {h.lower() for h in tf.headers}
    return {
        "thread_id": str(thread_id),
        "subject": tf.subject,
        "snippet": tf.snippet,
        "sender_domain": tf.sender_domain or "",
        "gmail_labels": sorted(tf.gmail_labels),
        "has_unsubscribe_link": "list-unsubscribe" in headers_lower,
    }


def _bucket_block(buckets: list[Bucket]) -> str:
    lines = [f"- {b.name}: {b.description or '(no description)'}" for b in buckets]
    return "Buckets (use these exact names):\n" + "\n".join(lines)


def _gmail_category_fallback(
    buckets: list[Bucket], items: list[tuple[uuid.UUID, ThreadFeatures]]
) -> dict[str, list[str]]:
    valid_names = {b.name for b in buckets}
    out: dict[str, list[str]] = {}
    for thread_id, tf in items:
        tags = [
            name
            for label, name in _GMAIL_CATEGORY_FALLBACK.items()
            if label in tf.gmail_labels and name in valid_names
        ]
        out[str(thread_id)] = tags
    return out


async def _evaluate_batch(
    buckets: list[Bucket], items: list[tuple[uuid.UUID, ThreadFeatures]]
) -> dict[str, list[str]]:
    valid_names = {b.name for b in buckets}
    user_content = json.dumps([_thread_payload(tid, tf) for tid, tf in items])

    try:
        raw = await complete_json(
            cached_system=STATIC_PROMPT_PREFIX,
            # Bucket names/descriptions only change when the user edits a bucket,
            # so this is worth its own cache breakpoint separate from the
            # per-batch thread payload below.
            dynamic_system=_bucket_block(buckets),
            dynamic_system_cached=True,
            user_content=user_content,
        )
    except (LLMJSONError, LLMUnavailableError):
        return _gmail_category_fallback(buckets, items)

    result: dict[str, list[str]] = {}
    for item in raw if isinstance(raw, list) else []:
        thread_id = item.get("thread_id")
        tags = [t for t in item.get("tags", []) if t in valid_names]
        if thread_id:
            result[thread_id] = tags

    missing = [(tid, tf) for tid, tf in items if str(tid) not in result]
    if missing:
        result.update(_gmail_category_fallback(buckets, missing))
    return result


async def evaluate_many(
    features_by_id: dict[uuid.UUID, ThreadFeatures], buckets: list[Bucket]
) -> dict[uuid.UUID, list[str]]:
    """Judge every thread against every semantic bucket, BATCH_SIZE threads per call."""
    if not features_by_id or not buckets:
        return {}

    items = list(features_by_id.items())
    batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    batch_results = await asyncio.gather(*(_evaluate_batch(buckets, b) for b in batches))

    merged: dict[uuid.UUID, list[str]] = {}
    allowed_thread_ids = set(features_by_id)
    for tag_map in batch_results:
        for thread_id_str, tags in tag_map.items():
            try:
                thread_id = uuid.UUID(thread_id_str)
            except ValueError:
                continue
            if thread_id in allowed_thread_ids:
                merged[thread_id] = tags
    return merged


async def evaluate(thread_id: uuid.UUID, tf: ThreadFeatures, bucket: Bucket) -> bool:
    """Single (thread, bucket) check for interface parity with rules_engine.
    One LLM call - prefer evaluate_many() for bulk work."""
    result = await _evaluate_batch([bucket], [(thread_id, tf)])
    return bucket.name in result.get(str(thread_id), [])
