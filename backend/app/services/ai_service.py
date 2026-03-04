"""AI service abstraction supporting multiple providers (OpenAI, DeepSeek)."""

from __future__ import annotations

from enum import Enum
from typing import List

from openai import AsyncOpenAI

from app.config import settings


class AIProvider(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


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
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        model = settings.DEEPSEEK_MODEL
    else:
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
