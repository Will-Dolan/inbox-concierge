# Classification Pipeline

Everything reduces to one primitive: `evaluate(db, threads, buckets, force)` in
`api/classify/evaluator.py`. It splits the given buckets into `deterministic` and
`semantic`, runs the deterministic ones through the rules engine (free, in-process), and
batches all the semantic ones into shared LLM calls. `force` controls whether already-tagged
threads are skipped (`force=False`, the sync path) or unconditionally re-evaluated
(`force=True`, the bucket-create/edit path).

## On-load: sync + classify the last 200 threads

```mermaid
sequenceDiagram
    participant FE as InboxView.tsx
    participant API as routes/sync.py
    participant Queue as core/queue.py
    participant GmailC as gmail/client.py
    participant Feat as gmail/thread_features.py
    participant Eval as classify/evaluator.py
    participant Rules as classify/rules_engine.py
    participant Sem as classify/semantic_eval.py
    participant Claude as Anthropic API
    participant DB as Postgres

    FE->>API: POST /sync (on mount, and every 2 min)
    API->>Queue: enqueue(sync_and_classify)
    API-->>FE: 202 { job_id }
    FE->>API: GET /jobs/{id} (poll)

    Queue->>GmailC: list_thread_ids(max_total=200)
    GmailC->>GmailC: paginate /threads, retry w/ backoff on 429
    Queue->>GmailC: get_thread() x N (bounded concurrency, semaphore=8)
    Queue->>Feat: aggregate_thread_features(messages)
    Queue->>DB: upsert Thread + MessageLite rows

    Queue->>Eval: evaluate(threads, all_buckets, force=False)
    Eval->>Rules: evaluate_bucket() per deterministic bucket
    Rules->>DB: upsert thread_tags(source='agent_rule')
    Eval->>Sem: evaluate_many() - one batched call per 60 threads, all semantic buckets at once
    Sem->>Claude: complete_json() (cached static prefix + bucket descriptions + thread batch)
    Claude-->>Sem: [{thread_id, tags: [...]}]
    Sem->>DB: upsert thread_tags(source='llm')

    FE->>API: GET /jobs/{id} (poll, sees "done")
    FE->>API: GET /threads?bucket=...
    API-->>FE: subject, snippet, sender, tags, unread
```

Notes:
- Deterministic default buckets (e.g. Newsletter, matched on `List-Unsubscribe` presence)
  become visible almost immediately since they cost no LLM call.
- If a semantic batch call fails (`LLMJSONError`/`LLMUnavailableError`),
  `semantic_eval.py` falls back to a Gmail-category→bucket-name mapping so the UI never
  shows an empty hole for that batch.
- `gmail/client.py` retries Gmail 429s / `rateLimitExceeded` up to 5 times with exponential
  backoff + jitter; `core/llm.py` does the same for Anthropic rate-limit/overload errors.

## Creating a custom bucket: recategorizes ALL existing threads

This is the path behind the assignment's "allow users to create their own buckets... which
should then recategorize all of the emails based on the new buckets."

```mermaid
sequenceDiagram
    participant FE as BucketEditorDialog.tsx
    participant API as routes/buckets.py
    participant Queue as core/queue.py
    participant Agent as agent/rule_agent.py
    participant Eval as classify/evaluator.py
    participant DB as Postgres

    FE->>API: POST /buckets { name, description, classifier }
    API->>DB: insert Bucket
    API->>Queue: enqueue(create_bucket_job)
    API-->>FE: 202 { bucket_id, job_id }
    FE->>API: GET /jobs/{id} (poll - streams agent step labels)

    alt classifier = rules
        Queue->>Agent: run_rule_agent(bucket)
        Note over Agent: ReAct loop, <=8 iterations, <=3 proposals.<br/>Tools: keyword_search, semantic_search,<br/>filter_threads, extract_field, sample.
        Agent->>Agent: propose_rule -> validate_rule<br/>(LLM spot-check precision on sampled matches)
        alt precision >= 0.8 on >=30 validated samples
            Agent-->>Queue: mode=deterministic, DSL rule (versioned)
        else can't clear the bar within budget
            Agent-->>Queue: mode=semantic (fallback)
        end
    else classifier = llm
        Queue->>DB: set bucket mode=semantic
    end

    Queue->>DB: SELECT all threads WHERE user_id = :user  (no LIMIT, no "since last sync" filter)
    Queue->>Eval: evaluate(all_threads, [new_bucket], force=True)
    Note over Eval: force=True bypasses the "skip already-classified"<br/>optimization the sync path uses - every thread<br/>is re-evaluated against this bucket.
    Eval->>DB: upsert thread_tags for every matching thread

    FE->>API: GET /threads?bucket=<new bucket>
    API-->>FE: full membership across the whole inbox, not just new mail
```

The same `force=True`, all-threads pattern is reused for manual rule edits
(`PUT /buckets/{id}/rule`) and bucket mode/description changes (`PATCH /buckets/{id}`) —
any time a bucket's *definition* changes, its membership is recomputed against every thread
the user has. Existing buckets are deliberately **not** re-run when a new bucket is added —
only the new bucket's membership is (re)computed — which keeps the cost of adding a bucket
proportional to one bucket, not the whole taxonomy.

## User corrections are preserved as explicit overrides

```mermaid
sequenceDiagram
    participant FE as ThreadRow.tsx
    participant API as routes/corrections.py
    participant DB as Postgres

    FE->>API: POST /corrections { thread_id, bucket_id, value }
    API->>DB: upsert thread_tags(source='user') - ON CONFLICT DO UPDATE
    API-->>FE: 202 { applied: true, self_improve_job_id: null }

    Note over API,DB: User correction rows always win during re-evaluation.<br/>Classification pipelines skip source='user' rows, so a tag edit<br/>is not silently undone by later LLM or rule passes.
```
