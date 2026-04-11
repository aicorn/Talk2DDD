"""AI service abstraction supporting multiple providers (OpenAI, DeepSeek, MiniMax)."""

from __future__ import annotations

from enum import Enum
from typing import List

from openai import AsyncOpenAI

from app.config import settings


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

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts.
        provider: Provider name ("openai" or "deepseek").
                  Falls back to ``settings.AI_PROVIDER`` when *None*.

    Returns:
        The assistant reply as a plain string.
    """
    provider = provider or settings.AI_PROVIDER
    client, model = get_ai_client(provider)

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
    )
    choices = response.choices
    if not choices:
        raise RuntimeError("AI provider returned an empty choices list")
    return choices[0].message.content or ""
