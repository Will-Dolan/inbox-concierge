# Inbox Concierge — Documentation

Inbox Concierge is a web app that authenticates a user's Google account, pulls their last
200 Gmail threads, and classifies them into buckets (Important, Can Wait, Auto-archive,
Newsletter, plus user-defined custom buckets) using an LLM-powered pipeline. Users can
create their own buckets, which triggers a cold-start "Rule Agent" that explores the inbox
and either derives a deterministic rule or falls back to per-thread LLM judgment.

This folder documents how the system actually works, based on the code as it exists today
(not aspirational design).

## Contents

| Doc | Covers |
|---|---|
| [architecture.md](architecture.md) | Module layout, request flow, deployment shape |
| [data-model.md](data-model.md) | Postgres schema and entity relationships |
| [classification-pipeline.md](classification-pipeline.md) | How threads get sorted into buckets, on load and on new-bucket creation |
| [rule-agent.md](rule-agent.md) | The cold-start Rule Agent for custom bucket rule discovery |
| [api-reference.md](api-reference.md) | REST surface, grouped by resource |
| [compliance.md](compliance.md) | Assignment requirements checklist, verdict + evidence per item |

## Quick orientation

```
frontend/   React + Vite SPA (TypeScript, Tailwind, shadcn/radix components)
api/        FastAPI backend (Python, async, SQLAlchemy + Postgres)
  core/     config, db, auth/session, crypto, the rule DSL, the Anthropic LLM wrapper
  gmail/    Gmail API client, thread sync, feature aggregation, unsubscribe
  classify/ classification pipeline: rules engine, semantic evaluator, the shared evaluator entrypoint
  agent/    the Rule Agent (cold-start rule discovery) and its tools
  routes/   HTTP endpoints, thin — delegate to the modules above
```

One primitive drives classification work: `evaluate(thread_set, bucket_set)` in
`api/classify/evaluator.py`. Initial sync, new buckets, manual rule edits, and bucket
mode/description changes all reduce to a call into this function with a different
`(threads, buckets, force)` combination. User corrections are stored separately as explicit
overrides. See
[classification-pipeline.md](classification-pipeline.md) for the details.
