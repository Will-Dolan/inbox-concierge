"""The only place message -> thread aggregation happens.

Everything downstream (rules engine, semantic evaluator, agent tools) consumes
the feature dict this produces, never raw per-message headers.
"""

from email.utils import getaddresses
from typing import TypedDict


class MessageFeatures(TypedDict):
    id: str
    internal_date: object  # datetime, kept loose to avoid a circular import
    headers: dict[str, str]
    label_ids: list[str]
    snippet: str


def _domain(address: str | None) -> str | None:
    if not address:
        return None
    addrs = getaddresses([address])
    if not addrs or "@" not in addrs[0][1]:
        return None
    return addrs[0][1].split("@")[-1].lower()


def _email(address: str | None) -> str | None:
    if not address:
        return None
    addrs = getaddresses([address])
    return addrs[0][1].lower() if addrs and addrs[0][1] else None


def _recipient_count(headers: dict[str, str]) -> int:
    to = headers.get("To", "")
    cc = headers.get("Cc", "")
    if not to and not cc:
        return 0
    return len(getaddresses([to, cc]))


def _has_attachment(headers: dict[str, str]) -> bool:
    content_type = (headers.get("Content-Type") or "").lower()
    return "multipart/mixed" in content_type or "attachment" in content_type


def aggregate_thread_features(messages: list[MessageFeatures]) -> dict:
    """OR-across-messages for content signals, latest-message for display fields."""
    if not messages:
        return {}

    messages_sorted = sorted(messages, key=lambda m: m["internal_date"])
    latest = messages_sorted[-1]

    def any_header(name: str) -> bool:
        return any(bool(m["headers"].get(name)) for m in messages)

    all_labels: set[str] = set()
    for m in messages:
        all_labels.update(m.get("label_ids") or [])

    list_id = next(
        (m["headers"].get("List-Id") for m in reversed(messages_sorted) if m["headers"].get("List-Id")),
        None,
    )

    recipient_counts = [_recipient_count(m["headers"]) for m in messages]

    present_headers: set[str] = set()
    for m in messages:
        present_headers.update(m["headers"].keys())

    return {
        "sender_domain": _domain(latest["headers"].get("From")),
        "sender_email": _email(latest["headers"].get("From")),
        "present_headers": sorted(present_headers),
        "has_attachment": any(_has_attachment(m["headers"]) for m in messages),
        "has_list_unsubscribe": any_header("List-Unsubscribe"),
        "has_list_unsubscribe_post": any_header("List-Unsubscribe-Post"),
        "list_id": list_id,
        "is_bulk_precedence": any(
            (m["headers"].get("Precedence") or "").lower() == "bulk" for m in messages
        ),
        "is_auto_submitted": any_header("Auto-Submitted"),
        "is_reply": any(
            m["headers"].get("In-Reply-To") or m["headers"].get("References") for m in messages
        ),
        "reply_to_differs_from_from": any(
            m["headers"].get("Reply-To") and m["headers"].get("Reply-To") != m["headers"].get("From")
            for m in messages
        ),
        "max_recipient_count": max(recipient_counts) if recipient_counts else 0,
        "gmail_labels": sorted(all_labels),
        "message_count": len(messages),
    }
