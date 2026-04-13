"""AI service abstraction supporting multiple providers (OpenAI, DeepSeek, MiniMax)."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import List

import openai
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Transient HTTP status codes that are safe to retry.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}

# Maximum number of automatic retries for retryable errors.
_MAX_RETRIES = 3

# Initial back-off in seconds; doubles on each subsequent attempt.
_RETRY_BACKOFF_BASE = 1.0


class AIProvider(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    MINIMAX = "minimax"


def get_model_name(provider: str) -> str:
    """Return the model name for *provider* without creating an API client.

    This is a lightweight lookup used by the router to populate the response
    schema.  Full validation (e.g. checking that the API key is set) is
    deferred to :func:`get_ai_client`, which is called inside
    :func:`chat_completion` when the actual network request is made.

    Raises:
        ValueError: If *provider* is not a recognised value.
    """
    try:
        prov = AIProvider(provider)
    except ValueError:
        supported = ", ".join(p.value for p in AIProvider)
        raise ValueError(f"Unsupported AI provider '{provider}'. Supported: {supported}")

    if prov == AIProvider.DEEPSEEK:
        return settings.DEEPSEEK_MODEL
    if prov == AIProvider.MINIMAX:
        return settings.MINIMAX_MODEL
    return settings.OPENAI_MODEL


def get_ai_client(provider: str) -> tuple[AsyncOpenAI, str]:
    """Return an AsyncOpenAI client and the model name for the given provider.

    DeepSeek exposes an OpenAI-compatible REST API, so the same ``openai``
    SDK can be reused by pointing it at a different base URL.

    Raises:
        ValueError: If *provider* is not a recognised value.
    """
    try:
        prov = AIProvider(provider)
    except ValueError:
        supported = ", ".join(p.value for p in AIProvider)
        raise ValueError(f"Unsupported AI provider '{provider}'. Supported: {supported}")

    if prov == AIProvider.DEEPSEEK:
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError(
                "DEEPSEEK_API_KEY is not configured. "
                "Please set it in your .env file."
            )
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        model = settings.DEEPSEEK_MODEL
    elif prov == AIProvider.MINIMAX:
        if not settings.MINIMAX_API_KEY:
            raise ValueError(
                "MINIMAX_API_KEY is not configured. "
                "Please set it in your .env file."
            )
        client = AsyncOpenAI(
            api_key=settings.MINIMAX_API_KEY,
            base_url=settings.MINIMAX_BASE_URL,
        )
        model = settings.MINIMAX_MODEL
    else:
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not configured. "
                "Please set it in your .env file."
            )
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        model = settings.OPENAI_MODEL

    return client, model


async def chat_completion(
    messages: List[dict],
    provider: str | None = None,
) -> str:
    """Send *messages* to the selected AI provider and return the reply text.

    Automatically retries on transient errors (HTTP 429, 500, 502, 503, 529)
    with exponential back-off (up to :data:`_MAX_RETRIES` attempts).

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts.
        provider: Provider name ("openai", "deepseek", or "minimax").
                  Falls back to ``settings.AI_PROVIDER`` when *None*.

    Returns:
        The assistant reply as a plain string.
    """
    provider = provider or settings.AI_PROVIDER
    client, model = get_ai_client(provider)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
            )
            choices = response.choices
            if not choices:
                raise RuntimeError("AI provider returned an empty choices list")
            return choices[0].message.content or ""
        except openai.APIStatusError as exc:
            if exc.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "AI provider returned HTTP %s (attempt %d/%d), retrying in %.1fs: %s",
                    exc.status_code,
                    attempt + 1,
                    _MAX_RETRIES,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
                last_exc = exc
                continue
            raise
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "AI provider connection error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
                last_exc = exc
                continue
            raise

    # Should not be reached, but satisfy type checker
    raise last_exc  # type: ignore[misc]
