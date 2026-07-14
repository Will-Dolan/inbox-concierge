from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.dsl import RuleDSL, ThreadFeatures, evaluate, normalize_conditions


def make_features(**overrides) -> ThreadFeatures:
    defaults = dict(
        subject="Your receipt from Acme",
        snippet="Thanks for your order",
        body="Total: $75.00",
        sender_email="billing@acme.com",
        sender_domain="acme.com",
        list_id="newsletter.acme.com",
        gmail_labels=frozenset({"INBOX", "CATEGORY_UPDATES"}),
        headers=frozenset({"From", "To", "List-Unsubscribe"}),
        recipient_count=1,
        is_reply=False,
        has_attachment=True,
        internal_date=datetime(2026, 6, 15, tzinfo=UTC),
        extracted_fields={"amount": 75.0},
    )
    defaults.update(overrides)
    return ThreadFeatures(**defaults)


def rule(logic: str, conditions: list[dict]) -> RuleDSL:
    return RuleDSL(bucket_id="b1", version=1, logic=logic, conditions=conditions)


def test_keyword_matches_any_field_case_insensitive():
    r = rule("AND", [{"type": "keyword", "any_of": ["RECEIPT"], "fields": ["subject"]}])
    assert evaluate(r, make_features()) is True

    r_miss = rule("AND", [{"type": "keyword", "any_of": ["invoice"], "fields": ["subject"]}])
    assert evaluate(r_miss, make_features()) is False


def test_sender_domain_and_email_and_list_id():
    assert evaluate(rule("AND", [{"type": "sender", "domain": "acme.com"}]), make_features()) is True
    assert evaluate(rule("AND", [{"type": "sender", "domain": "other.com"}]), make_features()) is False
    assert evaluate(rule("AND", [{"type": "sender", "email": "billing@acme.com"}]), make_features()) is True
    assert (
        evaluate(rule("AND", [{"type": "sender", "list_id": "newsletter.acme.com"}]), make_features())
        is True
    )


def test_sender_condition_requires_a_field():
    with pytest.raises(ValidationError):
        rule("AND", [{"type": "sender"}])


def test_gmail_label():
    assert evaluate(rule("AND", [{"type": "gmail_label", "label": "INBOX"}]), make_features()) is True
    assert evaluate(rule("AND", [{"type": "gmail_label", "label": "SPAM"}]), make_features()) is False


def test_header_present_case_insensitive():
    assert (
        evaluate(rule("AND", [{"type": "header_present", "header": "list-unsubscribe"}]), make_features())
        is True
    )
    assert (
        evaluate(rule("AND", [{"type": "header_present", "header": "X-Mailer"}]), make_features()) is False
    )


def test_time_range():
    r = rule(
        "AND",
        [
            {
                "type": "time_range",
                "start": "2026-06-01T00:00:00Z",
                "end": "2026-06-30T00:00:00Z",
            }
        ],
    )
    assert evaluate(r, make_features()) is True
    assert evaluate(r, make_features(internal_date=datetime(2026, 7, 1, tzinfo=UTC))) is False
    assert evaluate(r, make_features(internal_date=None)) is False


@pytest.mark.parametrize(
    "op,value,expected",
    [(">=", 50, True), (">", 75.0, False), ("==", 75.0, True), ("!=", 75.0, False), ("<", 100, True)],
)
def test_extracted_field_comparisons(op, value, expected):
    r = rule("AND", [{"type": "extracted_field", "field": "amount", "op": op, "value": value}])
    assert evaluate(r, make_features()) is expected


def test_extracted_field_missing_is_false():
    r = rule("AND", [{"type": "extracted_field", "field": "not_there", "op": ">=", "value": 1}])
    assert evaluate(r, make_features()) is False


def test_recipient_count():
    r = rule("AND", [{"type": "recipient_count", "op": ">=", "value": 2}])
    assert evaluate(r, make_features(recipient_count=3)) is True
    assert evaluate(r, make_features(recipient_count=1)) is False


def test_is_reply_and_has_attachment_booleans():
    assert evaluate(rule("AND", [{"type": "is_reply", "value": False}]), make_features()) is True
    assert evaluate(rule("AND", [{"type": "has_attachment", "value": True}]), make_features()) is True
    assert evaluate(rule("AND", [{"type": "has_attachment", "value": False}]), make_features()) is False


def test_nested_and_or_not():
    # (sender is acme.com AND NOT is_reply) OR gmail_label == "SPAM"
    r = rule(
        "OR",
        [
            {
                "type": "group",
                "logic": "AND",
                "conditions": [
                    {"type": "sender", "domain": "acme.com"},
                    {"type": "group", "logic": "NOT", "conditions": [{"type": "is_reply", "value": True}]},
                ],
            },
            {"type": "gmail_label", "label": "SPAM"},
        ],
    )
    assert evaluate(r, make_features()) is True
    assert evaluate(r, make_features(sender_domain="other.com", is_reply=True)) is False


def test_not_group_must_be_unary():
    with pytest.raises(ValidationError):
        rule("NOT", [{"type": "is_reply", "value": True}, {"type": "has_attachment", "value": True}])


def test_group_must_have_at_least_one_condition():
    with pytest.raises(ValidationError):
        rule("AND", [])


def test_rule_dsl_round_trips_through_json():
    r = rule(
        "AND",
        [
            {"type": "keyword", "any_of": ["receipt", "invoice"], "fields": ["subject", "snippet"]},
            {"type": "extracted_field", "field": "amount", "op": ">=", "value": 50},
        ],
    )
    reparsed = RuleDSL.model_validate_json(r.model_dump_json())
    assert evaluate(reparsed, make_features()) is True


def test_normalize_conditions_injects_missing_group_type():
    # LLM-authored nested group, missing the "type": "group" discriminator tag
    conditions = [
        {
            "logic": "AND",
            "conditions": [
                {"type": "sender", "domain": "acme.com"},
                {"logic": "NOT", "conditions": [{"type": "is_reply", "value": True}]},
            ],
        },
        {"type": "gmail_label", "label": "SPAM"},
    ]
    r = rule("OR", normalize_conditions(conditions))
    assert evaluate(r, make_features()) is True
    assert evaluate(r, make_features(sender_domain="other.com", is_reply=True)) is False


def test_normalize_conditions_leaves_tagged_conditions_untouched():
    conditions = [{"type": "keyword", "any_of": ["receipt"], "fields": ["subject"]}]
    assert normalize_conditions(conditions) == conditions
