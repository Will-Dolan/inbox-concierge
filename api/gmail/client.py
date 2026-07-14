import asyncio
import random

import httpx

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

METADATA_HEADERS = [
    "From",
    "To",
    "Cc",
    "Subject",
    "Date",
    "Reply-To",
    "List-Unsubscribe",
    "List-Unsubscribe-Post",
    "List-Id",
    "List-Post",
    "Precedence",
    "Auto-Submitted",
    "In-Reply-To",
    "References",
    "Content-Type",
    "X-Mailer",
]

MAX_RETRIES = 5


class GmailAPIError(Exception):
    pass


class GmailClient:
    def __init__(self, access_token: str):
        self._client = httpx.AsyncClient(
            base_url=GMAIL_API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GmailClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(MAX_RETRIES):
            resp = await self._client.get(path, params=params)
            is_rate_limited = resp.status_code == 429 or (
                resp.status_code == 403 and "rateLimitExceeded" in resp.text
            )
            if is_rate_limited:
                await asyncio.sleep((2**attempt) + random.random())
                continue
            resp.raise_for_status()
            return resp.json()
        raise GmailAPIError(f"Rate limited after {MAX_RETRIES} retries: {path}")

    async def _post(self, path: str, json: dict) -> dict:
        for attempt in range(MAX_RETRIES):
            resp = await self._client.post(path, json=json)
            is_rate_limited = resp.status_code == 429 or (
                resp.status_code == 403 and "rateLimitExceeded" in resp.text
            )
            if is_rate_limited:
                await asyncio.sleep((2**attempt) + random.random())
                continue
            resp.raise_for_status()
            return resp.json()
        raise GmailAPIError(f"Rate limited after {MAX_RETRIES} retries: {path}")

    async def mark_thread_read(self, thread_id: str) -> None:
        await self._post(f"/threads/{thread_id}/modify", {"removeLabelIds": ["UNREAD"]})

    async def list_thread_ids(self, max_total: int = 200) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < max_total:
            params: dict = {"maxResults": min(100, max_total - len(ids))}
            if page_token:
                params["pageToken"] = page_token
            data = await self._get("/threads", params=params)
            ids.extend(t["id"] for t in data.get("threads", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids[:max_total]

    async def get_thread(self, thread_id: str) -> dict:
        params = {"format": "metadata", "metadataHeaders": METADATA_HEADERS}
        return await self._get(f"/threads/{thread_id}", params=params)

    async def get_message(self, message_id: str) -> dict:
        """Full MIME body - only called lazily when a user opens a thread
        (see routes/threads.py), never during bulk sync."""
        return await self._get(f"/messages/{message_id}", params={"format": "full"})
