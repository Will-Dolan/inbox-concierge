import pytest
from fastapi import HTTPException

from core.ratelimit import _buckets, check_rate_limit


@pytest.fixture(autouse=True)
def _clear_buckets():
    _buckets.clear()
    yield
    _buckets.clear()


def test_allows_requests_under_the_limit():
    for _ in range(5):
        check_rate_limit("user-a:create_bucket", limit=5, window_seconds=60)


def test_raises_429_once_limit_is_exceeded():
    for _ in range(5):
        check_rate_limit("user-b:create_bucket", limit=5, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit("user-b:create_bucket", limit=5, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert "Too many requests" in exc_info.value.detail


def test_different_keys_are_tracked_independently():
    for _ in range(5):
        check_rate_limit("user-c:create_bucket", limit=5, window_seconds=60)

    # A different key (e.g. a different user or endpoint) has its own budget.
    check_rate_limit("user-d:create_bucket", limit=5, window_seconds=60)


def test_window_resets_after_it_elapses(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("core.ratelimit.time.monotonic", lambda: now[0])

    for _ in range(3):
        check_rate_limit("user-e:sync", limit=3, window_seconds=10)

    with pytest.raises(HTTPException):
        check_rate_limit("user-e:sync", limit=3, window_seconds=10)

    # Advance past the window - the limiter should allow requests again.
    now[0] += 11
    check_rate_limit("user-e:sync", limit=3, window_seconds=10)
