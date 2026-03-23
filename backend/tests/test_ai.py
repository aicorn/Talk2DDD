"""Tests for the /api/v1/ai/chat endpoint."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_chat_returns_200(client):
    with patch(
        "app.routers.v1.ai.chat_completion",
        new_callable=AsyncMock,
        return_value="Hello from mock",
    ):
        response = await client.post(
            "/api/v1/ai/chat",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_response_schema(client):
    with patch(
        "app.routers.v1.ai.chat_completion",
        new_callable=AsyncMock,
        return_value="Test reply",
    ):
        response = await client.post(
            "/api/v1/ai/chat",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )
    data = response.json()
    assert "reply" in data
    assert "provider" in data
    assert "model" in data
    assert data["reply"] == "Test reply"


@pytest.mark.asyncio
async def test_chat_uses_openai_provider_by_default(client):
    with patch(
        "app.routers.v1.ai.chat_completion",
        new_callable=AsyncMock,
        return_value="openai reply",
    ) as mock_chat:
        await client.post(
            "/api/v1/ai/chat",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )
    mock_chat.assert_called_once()
    _, kwargs = mock_chat.call_args
    assert kwargs.get("provider") in (None, "openai")


@pytest.mark.asyncio
async def test_chat_with_deepseek_provider(client):
    with patch(
        "app.routers.v1.ai.chat_completion",
        new_callable=AsyncMock,
        return_value="deepseek reply",
    ) as mock_chat:
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "messages": [{"role": "user", "content": "Hi"}],
                "provider": "deepseek",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "deepseek"
    mock_chat.assert_called_once()
    _, kwargs = mock_chat.call_args
    assert kwargs.get("provider") == "deepseek"


@pytest.mark.asyncio
async def test_chat_with_minimax_provider(client):
    with patch(
        "app.routers.v1.ai.chat_completion",
        new_callable=AsyncMock,
        return_value="minimax reply",
    ) as mock_chat:
        response = await client.post(
            "/api/v1/ai/chat",
            json={
                "messages": [{"role": "user", "content": "Hi"}],
                "provider": "minimax",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "minimax"
    mock_chat.assert_called_once()
    _, kwargs = mock_chat.call_args
    assert kwargs.get("provider") == "minimax"


@pytest.mark.asyncio
async def test_chat_empty_messages_returns_422(client):
    response = await client.post(
        "/api/v1/ai/chat",
        json={"messages": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_provider_error_returns_502(client):
    with patch(
        "app.routers.v1.ai.chat_completion",
        new_callable=AsyncMock,
        side_effect=RuntimeError("connection refused"),
    ):
        response = await client.post(
            "/api/v1/ai/chat",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )
    assert response.status_code == 502
    assert "AI provider error" in response.json()["detail"]
