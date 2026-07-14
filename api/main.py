from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from classify.defaults import ensure_default_buckets
from core.config import get_settings
from core.db import async_session_factory
from routes import auth, buckets, corrections, debug, digest, sync, threads, unsubscribe

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as session:
        await ensure_default_buckets(session)
    yield


app = FastAPI(title="Inbox Concierge API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(auth.me_router)
app.include_router(sync.router)
if settings.env == "local":
    # /debug/threads dumps a user's full thread feature set. It's properly
    # scoped to the caller's own data, but it's unnecessary attack surface
    # outside local development, so only register it there.
    app.include_router(debug.router)
app.include_router(threads.router)
app.include_router(buckets.router)
app.include_router(corrections.router)
app.include_router(digest.router)
app.include_router(unsubscribe.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
