"""Lightweight in-process rate limiting.

This is a single-process FastAPI app (see core/queue.py's LocalQueue - an
in-process job queue, not a distributed one), so an in-memory fixed-window
rate limiter is consistent with the rest of the architecture. No Redis or
external infra needed; a plain dict is fine since asyncio runs on a single
event loop (same reasoning LocalQueue uses to skip locking).
"""

import time
from collections.abc import Callable

from fastapi import HTTPException, Request

from core.session import SESSION_COOKIE_NAME, decode_session_token

# key -> (window_start_epoch_seconds, count)
_buckets: dict[str, tuple[float, int]] = {}


def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Raise HTTPException(429) if `key` has exceeded `limit` hits within the
    current fixed window of `window_seconds`, otherwise record this hit."""
    now = time.monotonic()
    window_start, count = _buckets.get(key, (now, 0))

    if now - window_start >= window_seconds:
        # Window has elapsed - start a fresh one.
        window_start, count = now, 0

    count += 1
    _buckets[key] = (window_start, count)

    if count > limit:
        retry_after = int(window_start + window_seconds - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests, try again in {retry_after}s",
        )


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable[..., None]:
    """FastAPI dependency factory: rate-limit by authenticated user.

    Relies on the session cookie directly (rather than depending on
    get_current_user) so it can run alongside the auth dependency without
    forcing an ordering; if there's no session, requests are keyed by client
    IP instead so unauthenticated calls still get bucketed.
    """

    def dependency(request: Request) -> None:
        session = request.cookies.get(SESSION_COOKIE_NAME)
        user_id = decode_session_token(session) if session else None
        ident = user_id or _client_ip(request)
        check_rate_limit(f"{name}:{ident}", limit, window_seconds)

    return dependency


def rate_limit_by_ip(name: str, limit: int, window_seconds: int) -> Callable[..., None]:
    """FastAPI dependency factory: rate-limit by client IP.

    For unauthenticated endpoints (e.g. the OAuth login redirect) where no
    user id is available yet. Note: Request.client.host is naive without a
    trusted-proxy setup (e.g. behind a load balancer it may report the proxy's
    IP for every request) - acceptable for this app's current scope, but
    would need X-Forwarded-For handling behind a real proxy.
    """

    def dependency(request: Request) -> None:
        check_rate_limit(f"{name}:{_client_ip(request)}", limit, window_seconds)

    return dependency


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
