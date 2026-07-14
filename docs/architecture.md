# Architecture

## System overview

```mermaid
flowchart TB
    Browser["React web app"]
    API["FastAPI routes"]
    Auth["Auth/session"]
    Jobs["Background jobs"]
    GmailSync["Gmail sync + feature extraction"]
    Classifier["Classification evaluator"]
    Rules["Rule DSL engine"]
    Agent["Rule Agent"]
    LLMWrap["LLM wrapper"]
    DB[("Postgres")]
    Google["Google OAuth + Gmail API"]
    Claude["Anthropic API"]

    Browser -->|"REST + session cookie"| API
    Browser -->|"poll job status"| API
    API --> Auth
    API --> DB
    API --> Jobs
    Auth --> Google

    Jobs --> GmailSync
    Jobs --> Classifier
    Jobs --> Agent
    Jobs --> DB

    GmailSync --> Google
    GmailSync --> DB
    Classifier --> Rules
    Classifier --> LLMWrap
    Classifier --> DB
    Agent --> LLMWrap
    Agent --> DB
    LLMWrap --> Claude
```

## Layering rules

- **`routes/*` are thin.** They authenticate the user (`core/deps.get_current_user`),
  parse/validate input, call into `gmail/`, `classify/`, or `agent/`, and shape the
  response. No business logic lives in a route handler.
- **`core/dsl.py` is I/O-free.** It defines the rule condition types and a pure
  `evaluate(rule, features) -> bool`. It has no DB import and is shared by
  `classify/rules_engine.py`, `agent/rule_agent.py`'s validator, and (serialized to JSON)
  the frontend's `RuleSection.tsx` / `ruleFormat.ts`.
- **`gmail/thread_features.py` is the only place message→thread aggregation happens.**
  Everything downstream — the rules engine, the semantic evaluator, the agent tools —
  consumes the resulting flat feature dict (`threads.features` JSONB), never raw Gmail
  message payloads.
- **`rules_engine.evaluate_bucket()` and `semantic_eval.evaluate_many()` implement the
  same interface** at the bucket level, so `classify/evaluator.py` can dispatch on a
  bucket's `mode` column instead of branching business logic.
- **`core/llm.py` is the only place `anthropic.AsyncAnthropic` is called directly.** It
  centralizes prompt-cache structure, JSON-parse retry, and (rate-limit/overload) retry
  with backoff, so every caller — sync classification, the semantic evaluator, the rule
  agent, digests — gets the same failure handling for free.
- **`core/queue.py` is the one real portability seam.** It's an in-process asyncio queue
  today; the interface (`enqueue`/`get`/`push_progress`) is designed to be swapped for an
  SQS-backed adapter without changing any caller.

## Request/response shape

- Auth: Google OAuth 2.0 authorization-code flow, refresh token encrypted at rest
  (`core/crypto.py`, Fernet), session identity carried in an httpOnly JWT cookie
  (`core/session.py`) — no tokens ever touch the frontend.
- Long-running work (Gmail sync, bucket creation → rule agent run, semantic
  classification) is enqueued as a background job (`core/queue.py`) and the frontend polls
  `GET /jobs/{id}` (see `api.ts:pollJob`) — no websockets are needed for this workload.
- The DB is Postgres, accessed exclusively through async SQLAlchemy (`core/db.py`),
  migrated with Alembic (`api/migrations/versions/*`).

## Local deployment

`docker-compose.yml` runs Postgres + the FastAPI app; the frontend is a separate Vite dev
server (or a static build) that talks to the API over `VITE_API_BASE`. The intended cloud
target is Postgres → RDS, the API container → ECS Fargate, and
`core/queue.py`'s local adapter → SQS, with no other technology swap — the local and cloud
stacks are meant to stay identical everywhere except those two seams.
