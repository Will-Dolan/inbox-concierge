import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    google_sub: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    threads: Mapped[list["Thread"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    buckets: Mapped[list["Bucket"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (UniqueConstraint("user_id", "gmail_thread_id", name="uq_threads_user_gmail_thread"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gmail_thread_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_domain: Mapped[str | None] = mapped_column(String, nullable=True)
    latest_internal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="threads")
    messages: Mapped[list["MessageLite"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    tags: Mapped[list["ThreadTag"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class MessageLite(Base):
    __tablename__ = "messages_lite"

    id: Mapped[uuid.UUID] = _uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    gmail_message_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    internal_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    body_fetched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    thread: Mapped["Thread"] = relationship(back_populates="messages")


class Bucket(Base):
    __tablename__ = "buckets"
    __table_args__ = (
        CheckConstraint("kind IN ('system', 'custom')", name="ck_buckets_kind"),
        CheckConstraint("mode IN ('deterministic', 'semantic')", name="ck_buckets_mode"),
        CheckConstraint("mode_source IN ('default', 'agent', 'user')", name="ck_buckets_mode_source"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    mode_source: Mapped[str] = mapped_column(String, nullable=False)
    mode_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User | None"] = relationship(back_populates="buckets")
    rules: Mapped[list["Rule"]] = relationship(back_populates="bucket", cascade="all, delete-orphan")
    tags: Mapped[list["ThreadTag"]] = relationship(back_populates="bucket", cascade="all, delete-orphan")


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint("source IN ('hand', 'agent', 'user')", name="ck_rules_source"),
        UniqueConstraint("bucket_id", "version", name="uq_rules_bucket_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buckets.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    dsl: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    validated_on: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bucket: Mapped["Bucket"] = relationship(back_populates="rules")


class ThreadTag(Base):
    __tablename__ = "thread_tags"
    __table_args__ = (
        CheckConstraint("source IN ('llm', 'agent_rule', 'user')", name="ck_thread_tags_source"),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buckets.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    # True = belongs to this bucket, False = user explicitly excluded it (a "remove"
    # correction). Needed because (thread_id, bucket_id) is the PK - a bare delete
    # can't distinguish "never tagged" from "explicitly not this bucket", and pipelines
    # would just re-add the tag on the next pass, silently undoing the correction.
    value: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="tags")
    bucket: Mapped["Bucket"] = relationship(back_populates="tags")


class Digest(Base):
    """Cached digest text for one bucket, keyed by bucket - regenerating on
    every panel open would mean an LLM call every time the user glances at a
    bucket, so this persists the last generated digest and its timestamp;
    only an explicit refresh regenerates it."""

    __tablename__ = "digests"

    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buckets.id", ondelete="CASCADE"), primary_key=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (CheckConstraint("extractor IN ('regex', 'llm')", name="ck_extracted_fields_extractor"),)

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    field: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extractor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="extracted_fields")
