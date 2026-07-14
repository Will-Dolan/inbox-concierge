"""Rule DSL: schema + evaluator.

One definition, three consumers: the rules engine (runtime), the agent's rule
validator (propose/validate/refine loop), and — serialized — the frontend
RuleEditor. `evaluate()` is a pure function: no I/O, no DB, no network.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Evaluator input contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThreadFeatures:
    """Everything a rule (or the agent) can look at for one thread.

    Built by adapting a `threads` row + its `features` JSONB + any
    `extracted_fields` rows — see classify/rules_engine.py. Kept flat and
    dependency-free so this module never needs to import the DB layer.
    """

    subject: str = ""
    snippet: str = ""
    body: str = ""
    sender_email: str | None = None
    sender_domain: str | None = None
    list_id: str | None = None
    gmail_labels: frozenset[str] = field(default_factory=frozenset)
    # header names present, OR'd across messages
    headers: frozenset[str] = field(default_factory=frozenset)
    recipient_count: int = 0
    is_reply: bool = False
    has_attachment: bool = False
    internal_date: datetime | None = None
    extracted_fields: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Condition types
# ---------------------------------------------------------------------------

ComparisonOp = Literal[">=", "<=", ">", "<", "==", "!="]


def _compare(actual: object, op: ComparisonOp, expected: object) -> bool:
    if actual is None:
        return False
    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected
    # ordering comparisons require compatible types
    if op == ">=":
        return actual >= expected
    if op == "<=":
        return actual <= expected
    if op == ">":
        return actual > expected
    return actual < expected


class KeywordCondition(BaseModel):
    type: Literal["keyword"] = "keyword"
    any_of: list[str]
    fields: list[Literal["subject", "snippet", "body"]] = ["subject", "snippet", "body"]

    def evaluate(self, tf: ThreadFeatures) -> bool:
        haystacks = [getattr(tf, f, "") or "" for f in self.fields]
        return any(kw.lower() in h.lower() for h in haystacks for kw in self.any_of)


class SenderCondition(BaseModel):
    type: Literal["sender"] = "sender"
    domain: str | None = None
    email: str | None = None
    list_id: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "SenderCondition":
        if not (self.domain or self.email or self.list_id):
            raise ValueError("sender condition needs at least one of domain/email/list_id")
        return self

    def evaluate(self, tf: ThreadFeatures) -> bool:
        checks = []
        if self.domain is not None:
            checks.append((tf.sender_domain or "").lower() == self.domain.lower())
        if self.email is not None:
            checks.append((tf.sender_email or "").lower() == self.email.lower())
        if self.list_id is not None:
            checks.append((tf.list_id or "") == self.list_id)
        return all(checks)


class GmailLabelCondition(BaseModel):
    type: Literal["gmail_label"] = "gmail_label"
    label: str

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return self.label in tf.gmail_labels


class HeaderPresentCondition(BaseModel):
    type: Literal["header_present"] = "header_present"
    header: str

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return self.header.lower() in {h.lower() for h in tf.headers}


class TimeRangeCondition(BaseModel):
    type: Literal["time_range"] = "time_range"
    start: datetime | None = None
    end: datetime | None = None

    def evaluate(self, tf: ThreadFeatures) -> bool:
        if tf.internal_date is None:
            return False
        if self.start is not None and tf.internal_date < self.start:
            return False
        if self.end is not None and tf.internal_date > self.end:
            return False
        return True


class ExtractedFieldCondition(BaseModel):
    type: Literal["extracted_field"] = "extracted_field"
    field: str
    op: ComparisonOp
    value: float | str | bool

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return _compare(tf.extracted_fields.get(self.field), self.op, self.value)


class RecipientCountCondition(BaseModel):
    type: Literal["recipient_count"] = "recipient_count"
    op: ComparisonOp
    value: int

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return _compare(tf.recipient_count, self.op, self.value)


class IsReplyCondition(BaseModel):
    type: Literal["is_reply"] = "is_reply"
    value: bool = True

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return tf.is_reply == self.value


class HasAttachmentCondition(BaseModel):
    type: Literal["has_attachment"] = "has_attachment"
    value: bool = True

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return tf.has_attachment == self.value


Condition = (
    KeywordCondition
    | SenderCondition
    | GmailLabelCondition
    | HeaderPresentCondition
    | TimeRangeCondition
    | ExtractedFieldCondition
    | RecipientCountCondition
    | IsReplyCondition
    | HasAttachmentCondition
)


# ---------------------------------------------------------------------------
# Composable AND/OR/NOT groups (nestable)
# ---------------------------------------------------------------------------


class ConditionGroup(BaseModel):
    type: Literal["group"] = "group"
    logic: Literal["AND", "OR", "NOT"]
    conditions: list["Node"]

    @model_validator(mode="after")
    def _not_is_unary(self) -> "ConditionGroup":
        if self.logic == "NOT" and len(self.conditions) != 1:
            raise ValueError("NOT groups must have exactly one condition")
        if not self.conditions:
            raise ValueError("groups must have at least one condition")
        return self

    def evaluate(self, tf: ThreadFeatures) -> bool:
        return _evaluate_group(self.logic, self.conditions, tf)


Node = Annotated[
    KeywordCondition
    | SenderCondition
    | GmailLabelCondition
    | HeaderPresentCondition
    | TimeRangeCondition
    | ExtractedFieldCondition
    | RecipientCountCondition
    | IsReplyCondition
    | HasAttachmentCondition
    | ConditionGroup,
    Field(discriminator="type"),
]
ConditionGroup.model_rebuild()


def _evaluate_group(
    logic: Literal["AND", "OR", "NOT"], conditions: list, tf: ThreadFeatures
) -> bool:
    results = (c.evaluate(tf) for c in conditions)
    if logic == "AND":
        return all(results)
    if logic == "OR":
        return any(results)
    return not next(results)  # NOT: exactly one condition, validated above


def normalize_conditions(conditions: list) -> list:
    """LLM-authored condition trees predictably omit the "type": "group" tag on
    nested groups (they mirror the untagged top-level logic/conditions shape).
    Inject it recursively before validating, rather than rejecting an
    otherwise-correct rule over a discriminator technicality."""

    def _normalize(node: object) -> object:
        if not isinstance(node, dict):
            return node
        if "logic" in node and "conditions" in node and "type" not in node:
            node = {**node, "type": "group"}
        if "conditions" in node:
            node = {**node, "conditions": [_normalize(c) for c in node["conditions"]]}
        return node

    return [_normalize(c) for c in conditions]


# ---------------------------------------------------------------------------
# Top-level rule (what's persisted in `rules.dsl`)
# ---------------------------------------------------------------------------


class RuleDSL(BaseModel):
    bucket_id: str
    version: int
    logic: Literal["AND", "OR", "NOT"]
    conditions: list[Node]
    confidence: float | None = None
    validated_on: int | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _not_is_unary(self) -> "RuleDSL":
        if self.logic == "NOT" and len(self.conditions) != 1:
            raise ValueError("NOT groups must have exactly one condition")
        if not self.conditions:
            raise ValueError("rule must have at least one condition")
        return self


def evaluate(rule: RuleDSL, features: ThreadFeatures) -> bool:
    """Pure evaluation: `evaluate(dsl, thread_features) -> bool`. No I/O."""
    return _evaluate_group(rule.logic, rule.conditions, features)


def _describe_condition(node: dict) -> str:
    t = node.get("type")
    if t == "keyword":
        fields = "/".join(node.get("fields", []))
        return f"keyword in [{', '.join(node.get('any_of', []))}] ({fields})"
    if t == "sender":
        parts = [f"{k}={node[k]}" for k in ("domain", "email", "list_id") if node.get(k)]
        return "sender " + " & ".join(parts)
    if t == "gmail_label":
        return f"label={node.get('label')}"
    if t == "header_present":
        return f"header present: {node.get('header')}"
    if t == "time_range":
        return f"time between {node.get('start') or '...'} and {node.get('end') or '...'}"
    if t == "extracted_field":
        return f"{node.get('field')} {node.get('op')} {node.get('value')}"
    if t == "recipient_count":
        return f"recipient_count {node.get('op')} {node.get('value')}"
    if t == "is_reply":
        return f"is_reply == {node.get('value', True)}"
    if t == "has_attachment":
        return f"has_attachment == {node.get('value', True)}"
    if t == "group":
        inner = ", ".join(_describe_condition(c) for c in node.get("conditions", []))
        return f"{node.get('logic')}({inner})"
    return str(node)


def describe_rule(dsl: dict) -> str:
    """Plain-English rendering of a persisted rule's `dsl` JSON, for the
    frontend to show users what a deterministic bucket is actually matching on."""
    inner = ", ".join(_describe_condition(c) for c in dsl.get("conditions", []))
    return f"{dsl.get('logic')}({inner})"
