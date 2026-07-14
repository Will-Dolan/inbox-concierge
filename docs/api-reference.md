# API Reference

Base URL: `VITE_API_BASE` (frontend) / FastAPI app root. All routes except `/auth/google/*`
and `/healthz` require a valid `session` cookie (`core/deps.get_current_user`).

| Method | Path | File | Purpose |
|---|---|---|---|
| GET | `/healthz` | main.py | Liveness check |
| GET | `/auth/me` | routes/auth.py | Current session's user, or 401 |
| GET | `/auth/google/login` | routes/auth.py | Redirect to Google consent screen |
| GET | `/auth/google/callback` | routes/auth.py | OAuth code exchange, sets session cookie, redirects to frontend |
| POST | `/auth/google/logout` | routes/auth.py | Clear session cookie (204, not a redirect — SPA-friendly) |
| POST | `/sync` | routes/sync.py | Enqueue Gmail sync (last 200 threads) + classification → `202 { job_id }` |
| GET | `/jobs/{job_id}` | routes/sync.py | Poll status/progress of a background job |
| GET | `/threads` | routes/threads.py | List threads, optionally filtered by bucket |
| GET | `/threads/{thread_id}` | routes/threads.py | Full thread detail; lazily fetches + caches full MIME bodies |
| GET | `/buckets` | routes/buckets.py | List buckets with mode, active rule summary |
| POST | `/buckets` | routes/buckets.py | Create a custom bucket → `202`, then full-inbox evaluation. Request supports `classifier: "rules"` (Rule Agent) or `"llm"` (semantic judgment). |
| PATCH | `/buckets/{bucket_id}` | routes/buckets.py | Rename / change mode / description → re-evaluates that bucket over all threads |
| PUT | `/buckets/{bucket_id}/rule` | routes/buckets.py | Manually edit a bucket's DSL rule → re-evaluates that bucket over all threads |
| DELETE | `/buckets/{bucket_id}` | routes/buckets.py | Delete a custom bucket (system buckets are protected) |
| POST | `/corrections` | routes/corrections.py | Add/remove a user tag on a thread → `202`; stores an explicit override |
| GET | `/digest` | routes/digest.py | Cached (or `force=true` regenerated) LLM summary of a bucket |
| GET | `/unsubscribe/candidates` | routes/unsubscribe.py | Sender-domain-grouped unsubscribe candidates for a bucket |
| POST | `/unsubscribe/execute` | routes/unsubscribe.py | Execute a one-click (RFC 8058) unsubscribe |
| GET | `/debug/threads` | routes/debug.py | Raw thread dump for the current user (dev/debug only) |

## Conventions

- **Async job pattern**: any endpoint that does real work (Gmail sync, LLM classification,
  agent runs) returns `202 { job_id }` immediately; the frontend polls `GET /jobs/{id}`
  (`frontend/src/api.ts:pollJob`) rather than blocking the request or using websockets.
- **Auth**: session identity is an httpOnly JWT cookie (`core/session.py`), never exposed to
  JS. All authenticated routes depend on `core/deps.get_current_user`.
- **Errors**: LLM failures surface as a calm, user-safe message
  (`core/llm.LLMUnavailableError`) rather than a raw 500; Gmail 429s are retried
  transparently before ever reaching a route handler.
