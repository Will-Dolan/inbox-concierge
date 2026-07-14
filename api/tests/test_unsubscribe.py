import uuid

import pytest

import gmail.unsubscribe as unsubscribe


def test_parse_unsubscribe_one_click():
    headers = {
        "List-Unsubscribe": "<https://example.com/unsub?token=abc>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    info = unsubscribe._parse_unsubscribe(headers)
    assert info == {"method": "one_click", "url": "https://example.com/unsub?token=abc"}


def test_parse_unsubscribe_link_without_one_click_post():
    headers = {"List-Unsubscribe": "<https://example.com/unsub>"}
    info = unsubscribe._parse_unsubscribe(headers)
    assert info == {"method": "link", "url": "https://example.com/unsub"}


def test_parse_unsubscribe_mailto():
    headers = {"List-Unsubscribe": "<mailto:unsub@example.com>"}
    info = unsubscribe._parse_unsubscribe(headers)
    assert info == {"method": "mailto", "url": "mailto:unsub@example.com"}


def test_parse_unsubscribe_missing_header_returns_none():
    assert unsubscribe._parse_unsubscribe({}) is None


@pytest.mark.asyncio
async def test_get_one_click_url_returns_url_for_matching_one_click_domain(monkeypatch):
    """The server must only ever POST to a URL it derived itself from this
    user's own thread data - never a client-supplied one. This exercises the
    lookup that replaced the old raw-`url` request body (the SSRF vector)."""

    async def fake_candidates_by_domain(db, user_id, bucket_id):
        return {
            "news.example.com": {
                "sender_domain": "news.example.com",
                "thread_count": 3,
                "method": "one_click",
                "url": "https://news.example.com/unsub?u=123",
            },
            "manual.example.com": {
                "sender_domain": "manual.example.com",
                "thread_count": 1,
                "method": "link",
                "url": "https://manual.example.com/unsub",
            },
        }

    monkeypatch.setattr(unsubscribe, "_candidates_by_domain", fake_candidates_by_domain)

    url = await unsubscribe.get_one_click_url(None, uuid.uuid4(), uuid.uuid4(), "news.example.com")
    assert url == "https://news.example.com/unsub?u=123"


@pytest.mark.asyncio
async def test_get_one_click_url_rejects_non_one_click_method(monkeypatch):
    """A domain whose only candidate is a manual `link` (or mailto) must never
    be executed server-side - only real one-click (RFC 8058) candidates are
    eligible for the outbound POST."""

    async def fake_candidates_by_domain(db, user_id, bucket_id):
        return {
            "manual.example.com": {
                "sender_domain": "manual.example.com",
                "thread_count": 1,
                "method": "link",
                "url": "https://manual.example.com/unsub",
            }
        }

    monkeypatch.setattr(unsubscribe, "_candidates_by_domain", fake_candidates_by_domain)

    url = await unsubscribe.get_one_click_url(None, uuid.uuid4(), uuid.uuid4(), "manual.example.com")
    assert url is None


@pytest.mark.asyncio
async def test_get_one_click_url_returns_none_for_unknown_domain(monkeypatch):
    """A domain not present in this user's own bucket/thread data must never
    resolve to a URL - this is what stops a client from asking the server to
    unsubscribe an arbitrary/unrelated domain."""

    async def fake_candidates_by_domain(db, user_id, bucket_id):
        return {}

    monkeypatch.setattr(unsubscribe, "_candidates_by_domain", fake_candidates_by_domain)

    url = await unsubscribe.get_one_click_url(None, uuid.uuid4(), uuid.uuid4(), "attacker.example.com")
    assert url is None
