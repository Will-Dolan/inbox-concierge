# The Rule Agent

`api/agent/rule_agent.py` is the most technically substantial piece of the system — a
cold-start agent that turns a user-supplied bucket name/description into either a free,
deterministic rule or an explicit decision to fall back to per-thread LLM judgment. It's the
mechanism behind requirement #5 (custom buckets) and the project's standout "wow" feature.

## Cold-start loop

```mermaid
flowchart TD
    Start(["Bucket created:<br/>title + optional description"]) --> Loop

    subgraph Loop["ReAct loop - max 8 iterations, max 3 rule proposals"]
        direction TB
        Reason["Reason about distinguishing signals"]
        ToolCall{"Call a tool"}
        Reason --> ToolCall
        ToolCall -->|keyword_search| KW["Postgres full-text search<br/>(tsvector, subject+snippet)"]
        ToolCall -->|semantic_search| SS["LLM-ranked relevance search<br/>over up to 300 recent threads"]
        ToolCall -->|filter_threads| FT["SQL predicate filter<br/>(sender domain, list_id, time range)"]
        ToolCall -->|extract_field| EF["Regex-first extraction,<br/>LLM fallback, cached in extracted_fields"]
        ToolCall -->|sample| SM["Pull subject/snippet/features<br/>for N thread ids"]
        KW --> Reason
        SS --> Reason
        FT --> Reason
        EF --> Reason
        SM --> Reason
        ToolCall -->|propose_rule| Propose["Propose a DSL rule"]
    end

    Propose --> Validate["validate_rule(): apply rule to all real threads,<br/>sample matches + near-misses,<br/>LLM spot-check for precision"]
    Validate --> Bar{"precision >= 0.8<br/>on >= 30 samples?"}
    Bar -->|yes| Deploy["Save rule (versioned, active).<br/>mode = deterministic.<br/>Evaluate against all threads - free."]
    Bar -->|no, budget remains| Loop
    Bar -->|no, budget exhausted| Fallback["mode = semantic.<br/>Bucket runs through the batched<br/>semantic evaluator instead."]
    ToolCall -->|recommend_semantic| Fallback

    Deploy --> Done(["Bucket ready, membership computed<br/>over the whole inbox"])
    Fallback --> Done
```

Iteration and proposal budgets are hard caps (`MAX_ITERATIONS=8`, `MAX_PROPOSALS=3` in
`rule_agent.py`) — the agent always terminates in bounded time, either with a validated
rule or an explicit semantic fallback. Every step is streamed to the frontend via an
`on_step` callback (`core/queue.push_progress`), which `BucketEditorDialog.tsx` renders live
as "Agent is exploring…" progress.

## Design notes

- The agent's tools only ever query **our own Postgres data** (already-synced threads),
  never live Gmail — exploration is fast and free of additional Gmail quota.
- `semantic_search` is LLM-based ranking today, not embeddings. The interface is stable and
  the implementation is swappable; pgvector would be the likely production replacement.
- `extract_field` results are cached forever per `(thread_id, field)`, so the same
  extraction (e.g., "amount") computed once during agent validation is reused by any rule
  or subsequent agent run without a repeat LLM call.
