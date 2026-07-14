# Data Model

Ground truth is `api/core/models.py` (SQLAlchemy ORM) plus the Alembic migrations in
`api/migrations/versions/`. This reflects the schema as actually built.

```mermaid
erDiagram
    USERS ||--o{ THREADS : owns
    USERS ||--o{ BUCKETS : owns
    THREADS ||--o{ MESSAGES_LITE : contains
    THREADS ||--o{ THREAD_TAGS : tagged
    THREADS ||--o{ EXTRACTED_FIELDS : caches
    BUCKETS ||--o{ THREAD_TAGS : assigns
    BUCKETS ||--o{ RULES : versions
    BUCKETS ||--o| DIGESTS : caches

    USERS {
        uuid id
        string google_sub
        string email
        text encrypted_refresh_token
        timestamp created_at
    }
    THREADS {
        uuid id
        uuid user_id
        string gmail_thread_id
        string subject
        string snippet
        string sender_domain
        timestamp latest_internal_date
        int message_count
        jsonb features
    }
    MESSAGES_LITE {
        uuid id
        uuid thread_id
        string gmail_message_id
        timestamp internal_date
        jsonb headers
        bool body_fetched
        text body_text
        text body_html
    }
    BUCKETS {
        uuid id
        uuid user_id
        string name
        string description
        string kind
        string mode
        string mode_source
        text mode_rationale
    }
    RULES {
        uuid id
        uuid bucket_id
        int version
        jsonb dsl
        float confidence
        int validated_on
        text rationale
        string source
        bool active
    }
    THREAD_TAGS {
        uuid thread_id
        uuid bucket_id
        string source
        bool value
        float confidence
    }
    EXTRACTED_FIELDS {
        uuid thread_id
        string field_name
        jsonb value
        string extractor
    }
    DIGESTS {
        uuid bucket_id
        text digest_text
        timestamp generated_at
    }
```

Mermaid reserves some words in ER attributes, so the diagram uses `field_name` for the
actual `extracted_fields.field` column and `digest_text` for the actual `digests.text`
column.

## Invariants

- **`thread_tags` rows with `source='user'` are never overwritten by a pipeline.**
  `classify/rules_engine.py` and `classify/evaluator.py` explicitly skip threads with an
  existing user correction for a bucket when re-deriving `agent_rule`/`llm` tags.
- **Zero tags = generic inbox.** There's no sentinel "uncategorized" row — a thread with no
  `thread_tags` rows simply doesn't match any bucket. The frontend's "all" / unbucketed
  view is `NOT EXISTS (thread_tags for thread)`.
- **Re-evaluation deletes + re-derives `llm`/`agent_rule` rows** for the (thread, bucket)
  scope being evaluated; it never touches `user`-sourced rows.
- **Rule versions are append-only.** `rules.active` is the only mutable field on an
  existing row from the rollback path — a new rule proposal always inserts a new
  `(bucket_id, version)` row and deactivates the prior one, so history (and rollback) is
  preserved.
- **`extracted_fields` is a forever-cache**, keyed by `(thread_id, field)`: once a value is
  extracted (regex or LLM) for a thread, it's reused by any rule or agent tool call that
  needs it, never recomputed.
