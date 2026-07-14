"""Adapts a `threads` DB row into the DSL's evaluator contract.

One definition, used by rules_engine, semantic_eval, and (later) the agent's
tools - so a thread never gets described two different ways to two different
consumers.
"""

from core.dsl import ThreadFeatures
from core.models import Thread


def thread_to_features(thread: Thread) -> ThreadFeatures:
    f = thread.features or {}
    return ThreadFeatures(
        subject=thread.subject or "",
        snippet=thread.snippet or "",
        body="",  # lazy body fetch not wired up yet; conditions relying on it just won't match
        sender_email=f.get("sender_email"),
        sender_domain=thread.sender_domain,
        list_id=f.get("list_id"),
        gmail_labels=frozenset(f.get("gmail_labels", [])),
        headers=frozenset(f.get("present_headers", [])),
        recipient_count=f.get("max_recipient_count", 0),
        is_reply=f.get("is_reply", False),
        has_attachment=f.get("has_attachment", False),
        internal_date=thread.latest_internal_date,
        extracted_fields={},  # populated once extracted_fields table is wired up (agent step)
    )
