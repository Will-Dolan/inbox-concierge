import uuid
from datetime import UTC, datetime

from classify.features import thread_to_features
from core.models import Thread


def test_thread_to_features_maps_json_features():
    thread = Thread(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        gmail_thread_id="abc",
        subject="Hello",
        snippet="preview",
        sender_domain="acme.com",
        latest_internal_date=datetime(2026, 1, 1, tzinfo=UTC),
        message_count=1,
        features={
            "sender_email": "a@acme.com",
            "list_id": "list.acme.com",
            "gmail_labels": ["INBOX"],
            "present_headers": ["From", "List-Unsubscribe"],
            "max_recipient_count": 2,
            "is_reply": True,
            "has_attachment": True,
        },
    )

    tf = thread_to_features(thread)

    assert tf.subject == "Hello"
    assert tf.sender_email == "a@acme.com"
    assert tf.sender_domain == "acme.com"
    assert tf.list_id == "list.acme.com"
    assert "List-Unsubscribe" in tf.headers
    assert tf.recipient_count == 2
    assert tf.is_reply is True
    assert tf.has_attachment is True


def test_thread_to_features_defaults_when_features_empty():
    thread = Thread(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        gmail_thread_id="abc",
        subject=None,
        snippet=None,
        sender_domain=None,
        latest_internal_date=None,
        message_count=0,
        features={},
    )

    tf = thread_to_features(thread)

    assert tf.subject == ""
    assert tf.headers == frozenset()
    assert tf.recipient_count == 0
    assert tf.is_reply is False
