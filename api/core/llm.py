"""Owns prompt-cache structure, batching, and JSON validation/retry for every
LLM call in the app (sync classification, semantic evaluator, rule agent) - implemented once.
"""

import asyncio
import json
import random
import re

import anthropic
from anthropic import AsyncAnthropic

from core.config import get_settings

_client: AsyncAnthropic | None = None

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_MAX_RETRIES = 5


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


class LLMJSONError(Exception):
    pass


class LLMUnavailableError(Exception):
    """The AI call itself failed (rate limit, overload, network, timeout) - as
    opposed to LLMJSONError, where the call succeeded but returned bad JSON.
    Message is written to be shown to the user as-is: calm, no stack trace."""

    def __init__(self) -> None:
        super().__init__("The AI service is briefly unavailable. Please try again in a moment.")


async def safe_create(client: AsyncAnthropic, /, **kwargs):
    """Every direct client.messages.create() call in the app should go through
    this so an Anthropic API failure never surfaces as a raw exception/500.
    Rate-limit (429) and transient overload (529) errors are retried with
    exponential backoff + jitter, mirroring gmail/client.py's handling of
    Gmail's 429s - anything else fails immediately."""
    for attempt in range(_MAX_RETRIES):
        try:
            return await client.messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise LLMUnavailableError() from exc
            await asyncio.sleep(2**attempt + random.random())
        except anthropic.APIError as exc:
            raise LLMUnavailableError() from exc
    raise LLMUnavailableError()


def _strip_markdown_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


async def complete_json(
    *,
    cached_system: str,
    dynamic_system: str = "",
    dynamic_system_cached: bool = False,
    user_content: str,
    max_tokens: int = 4096,
) -> list | dict:
    """One LLM call, `cached_system` marked for prompt caching (shared static
    prefix across all users/calls), `dynamic_system` appended after it. Pass
    `dynamic_system_cached=True` when the dynamic block is also stable across
    many calls in practice (e.g. a bucket-name list that rarely changes) so it
    gets its own cache breakpoint instead of being resent uncached every time.
    Parses strict JSON from the response, retrying once on parse failure.
    """
    settings = get_settings()
    client = get_client()

    system = [{"type": "text", "text": cached_system, "cache_control": {"type": "ephemeral"}}]
    if dynamic_system:
        block = {"type": "text", "text": dynamic_system}
        if dynamic_system_cached:
            block["cache_control"] = {"type": "ephemeral"}
        system.append(block)

    messages = [{"role": "user", "content": user_content}]
    last_error: Exception | None = None

    for attempt in range(2):
        resp = await safe_create(
            client,
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        try:
            return json.loads(_strip_markdown_fences(text))
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt == 0:
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "That was not valid JSON. Return ONLY a valid JSON value - "
                            "no prose, no markdown fences."
                        ),
                    },
                ]

    raise LLMJSONError(f"LLM did not return valid JSON after retry: {last_error}")
