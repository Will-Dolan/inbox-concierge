# Assignment Compliance

Verdicts against the project requirements, checked against the actual code.

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Web interface using **React** | Met | `frontend/package.json`: `react@^18.3.1`, `vite`, `typescript`. No Expo/React Native anywhere in the tree. Plain browser SPA (`src/main.tsx`, `index.html`). |
| 2 | Authenticate a **G-Suite/Gmail account** | Met | Full OAuth2 code flow: `Login.tsx` → `GET /auth/google/login` → `core/google_oauth.build_auth_url()` (scopes incl. `gmail.modify`) → `GET /auth/google/callback` → token exchange, ID-token verification, refresh token encrypted at rest (`core/crypto.py`), httpOnly session cookie. End-to-end, not mocked. |
| 3 | On load, group **last 200 threads** into buckets via an **LLM-powered pipeline** | Met | `gmail/sync.py:sync_last_200_threads` (`MAX_THREADS=200`, real paginated Gmail calls with 429 backoff) triggered by `InboxView.tsx` on mount → `POST /sync` → `classify/evaluator.evaluate()`. Semantic buckets are classified via real batched Anthropic calls (`classify/semantic_eval.py`, `core/llm.py`) with strict-JSON output and a fallback path on failure — not a stub. Default buckets (Newsletter, Important, Can Wait, Auto-archive) ship hand-authored per `classify/defaults.py`. |
| 4 | Show **subject + preview**, homepage-style; click-through not required | Met (and exceeded) | `GET /threads` returns subject/snippet/sender/tags; `ThreadRow.tsx` renders exactly that. Click-through into full sanitized bodies (`ThreadDetailPanel.tsx` + `EmailBody.tsx`) was implemented as a bonus even though the prompt says it isn't required. |
| 5 | Custom buckets **recategorize all emails** against the new bucket set | Met | `POST /buckets` (`routes/buckets.py`) runs the Rule Agent, then selects **every** thread for the user (no limit, no "since last sync" filter) and calls `evaluator.evaluate(all_threads, [new_bucket], force=True)`. `force=True` bypasses the "skip already-classified" optimization the sync path uses, guaranteeing full-inbox re-evaluation against the new bucket. Same pattern on rule edits and mode changes. See [classification-pipeline.md](classification-pipeline.md). |
| 6a | Production quality — **modular** | Met | Clean layering (`core` → `gmail`/`classify`/`agent` → `routes`), single-responsibility modules, shared interfaces (`rules_engine.evaluate_bucket` / `semantic_eval.evaluate_many` implement the same contract so bucket mode is a config value, not branching logic). |
| 6b | Production quality — **linted** | Met | Backend: `ruff` configured in `api/pyproject.toml` (`select = ["E","F","I","UP","B"]`). Frontend: `eslint.config.js` (typescript-eslint + react-hooks/react-refresh). `.github/workflows/ci.yml` runs backend lint/tests plus frontend lint/build on push/PR. |
| 6c | Production quality — **error handling** | Met | `core/llm.py` centralizes LLM failures into a calm `LLMUnavailableError`; `classify/semantic_eval.py` falls back to Gmail-category tags on a failed batch so the UI never shows a hole; `routes/threads.py` catches per-message body-fetch failures individually. |
| 6d | Production quality — **rate limits** | Met | Gmail: `gmail/client.py` retries 429/`rateLimitExceeded` up to 5x with exponential backoff + jitter. LLM calls use `core/llm.py:safe_create`, which retries Anthropic rate-limit/overload failures before surfacing `LLMUnavailableError`. |
| 7 | **AI-native speed** | Informational | Not directly code-verifiable. The repository shows fast iteration through modular AI-facing seams: strict JSON prompts, a shared LLM wrapper, tool-using Rule Agent, and targeted tests around the DSL/features. |
| 8 | **"Wow factor"** — high-leverage extension | Met | Four extensions are functionally implemented, not stubs: **explainability** (per-tag rationale on hover), **mass unsubscribe** (real RFC 8058 one-click POST execution, `gmail/unsubscribe.py`), **the Rule Agent** (a ReAct tool-use loop with 5 real tools and LLM-spot-checked precision validation, see [rule-agent.md](rule-agent.md)), and **digest** (cached per-bucket LLM summary). |

## Known, accepted gaps (not fixed — out of scope / explicit design trade-offs)

These are items I would finish with more time.

- `thread_tags.confidence` exists as a column but is never populated by
  `rules_engine.evaluate_bucket` or `evaluator._persist_semantic_tags` — deterministic
  rules don't have a natural per-thread confidence, and semantic batch calls don't
  currently request one. Cosmetic gap, not a functional one.
- `agent/tools/semantic_search.py` is LLM-ranked search over recent threads, not a real
  embeddings index. The tool interface is stable and swappable; pgvector would be the
  likely next implementation.
- `agent/self_improve.py` contains the patching helper for correction-driven rule updates,
  but `POST /corrections` currently treats tag edits as explicit overrides, not automatic
  rule-training feedback. Wiring that helper into a reviewed product flow is future work.
- `core/queue.py` is in-process and non-durable (jobs lost on restart) — acceptable for a
  local-first submission; the interface is designed to be replaced by an SQS adapter
  without touching any caller.
