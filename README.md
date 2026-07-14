# Inbox Concierge

Inbox Concierge is a React + FastAPI app that authenticates a Gmail account, syncs the
last 200 Gmail threads, and classifies them into useful buckets with a mix of deterministic
rules and batched LLM judgment. Users can create custom buckets, run a Rule Agent to find
deterministic rules, override tags manually, generate bucket digests, and act on grouped
unsubscribe candidates.

## What is included

- Google OAuth login with server-side refresh-token storage.
- Gmail sync for the latest 200 threads.
- Thread-level feature aggregation and classification.
- Default buckets: Newsletter, Important, Can Wait, Auto-archive.
- Custom buckets with either Rule Agent discovery or direct LLM classification.
- Subject + preview inbox UI, bucket filtering, corrections, digest, and unsubscribe tools.

## Tech stack

- Frontend: React, Vite, TypeScript, Tailwind, Radix/shadcn-style components.
- Backend: FastAPI, async SQLAlchemy, Alembic, Postgres.
- AI: Anthropic API through a shared JSON/retry wrapper.
- Gmail: Gmail API via OAuth, metadata-first sync, lazy body fetch.

## Prerequisites

- Python 3.11+
- Node 18+
- Docker, for local Postgres
- Google OAuth client configured for `http://localhost:8000/auth/google/callback`
- Anthropic API key

## Environment

Copy the example files:

```bash
cp api/.env.example api/.env
cp frontend/.env.example frontend/.env
```

Fill in:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `TOKEN_ENCRYPTION_KEY`
- `ANTHROPIC_API_KEY`

`TOKEN_ENCRYPTION_KEY` should be a Fernet key. For local development, generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Run locally

Install dependencies:

```bash
make setup
```

Run Postgres, apply migrations, and start both the API and frontend:

```bash
make dev
```

Open `http://localhost:5173`.

`make dev` starts:

- Postgres via Docker Compose
- FastAPI at `http://localhost:8000`
- Vite frontend at `http://localhost:5173`

If you prefer to run each process manually:

```bash
docker compose up -d postgres
cd api
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## Test and lint

Run the full local check suite:

```bash
make test
```

That runs backend lint/tests and frontend lint/build. You can also run them separately:

```bash
cd api
uv run ruff check .
uv run pytest
cd frontend
npm run lint
npm run build
```

## Documentation

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Classification pipeline](docs/classification-pipeline.md)
- [Rule Agent](docs/rule-agent.md)
- [API reference](docs/api-reference.md)
- [Assignment compliance](docs/compliance.md)

## Submission notes

For Ashby, submit the YouTube walkthrough link, this public GitHub repository, and the
deployed/live link if available. If no deployment is available, note that the app runs
locally with the instructions above.
