import uuid

import pytest

from classify import semantic_eval
from core.dsl import ThreadFeatures
from core.models import Bucket


def make_features() -> ThreadFeatures:
    return ThreadFeatures(
        subject="Hello",
        snippet="Preview",
        body="",
        sender_email=None,
        sender_domain=None,
        list_id=None,
        gmail_labels=frozenset(),
        headers=frozenset(),
        recipient_count=1,
        is_reply=False,
        has_attachment=False,
        internal_date=None,
        extracted_fields={},
    )


@pytest.mark.asyncio
async def test_evaluate_many_ignores_llm_thread_ids_outside_batch(monkeypatch):
    real_thread_id = uuid.uuid4()
    hallucinated_thread_id = uuid.uuid4()
    bucket = Bucket(id=uuid.uuid4(), name="Receipts", description="", kind="custom", mode="semantic")

    async def fake_evaluate_batch(_buckets, _items):
        return {
            str(real_thread_id): ["Receipts"],
            str(hallucinated_thread_id): ["Receipts"],
            "not-a-uuid": ["Receipts"],
        }

    monkeypatch.setattr(semantic_eval, "_evaluate_batch", fake_evaluate_batch)

    result = await semantic_eval.evaluate_many({real_thread_id: make_features()}, [bucket])

    assert result == {real_thread_id: ["Receipts"]}
