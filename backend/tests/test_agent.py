"""Integration tests for the /api/v1/agent/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.main import app


def make_user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        email="agent@example.com",
        username="agentuser",
        full_name="Agent User",
        is_active=True,
        is_superuser=False,
        preferred_language="zh-CN",
        theme="light",
        bio=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest_asyncio.fixture
async def auth_client():
    """AsyncClient with both DB and auth stubbed out."""
    mock_user = make_user()

    async def mock_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, mock_user

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_agent_chat_returns_200(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())

    with (
        patch(
            "app.routers.v1.agent._ensure_conversation",
            new_callable=AsyncMock,
        ),
        patch(
            "app.routers.v1.agent._agent_core.chat",
            new_callable=AsyncMock,
        ) as mock_chat,
    ):
        from app.agent.agent_core import AgentResponse, PhaseDocumentResult

        mock_chat.return_value = AgentResponse(
            reply="你好！请介绍一下你的项目。",
            session_id=session_id,
            phase="ICEBREAK",
            phase_label="破冰引入",
            progress=0.0,
            suggestions=["请介绍项目背景"],
            extracted_concepts=[],
            requirement_changes=[],
            stale_documents=[],
            pending_documents=[],
            phase_document=PhaseDocumentResult(
                phase="ICEBREAK",
                title="项目简介",
                content="# 项目简介\n\n（待填写）",
                rendered_at=datetime.now(timezone.utc),
                turn_count=1,
            ),
        )

        response = await client.post(
            "/api/v1/agent/chat",
            json={"session_id": session_id, "message": "你好"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "你好！请介绍一下你的项目。"
    assert data["phase"] == "ICEBREAK"
    assert data["phase_label"] == "破冰引入"
    assert "progress" in data
    assert "suggestions" in data
    assert data["phase_document"]["phase"] == "ICEBREAK"


@pytest.mark.asyncio
async def test_agent_chat_response_schema(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())

    with (
        patch(
            "app.routers.v1.agent._ensure_conversation",
            new_callable=AsyncMock,
        ),
        patch(
            "app.routers.v1.agent._agent_core.chat",
            new_callable=AsyncMock,
        ) as mock_chat,
    ):
        from app.agent.agent_core import AgentResponse

        mock_chat.return_value = AgentResponse(
            reply="Test reply",
            session_id=session_id,
            phase="REQUIREMENT",
            phase_label="需求收集",
            progress=0.2,
            suggestions=["请描述核心业务流程"],
            extracted_concepts=[
                {"name": "订单", "type": "ENTITY", "confidence": 0.9}
            ],
            requirement_changes=[],
            stale_documents=[],
            pending_documents=[],
            phase_document=None,
        )

        response = await client.post(
            "/api/v1/agent/chat",
            json={"session_id": session_id, "message": "我们要做电商系统"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "phase" in data
    assert "phase_label" in data
    assert "progress" in data
    assert "suggestions" in data
    assert "extracted_concepts" in data
    assert "requirement_changes" in data
    assert "stale_documents" in data
    assert "pending_documents" in data


@pytest.mark.asyncio
async def test_generate_document_returns_200(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    with (
        patch(
            "app.routers.v1.agent._ensure_conversation",
            new_callable=AsyncMock,
        ),
        patch(
            "app.routers.v1.agent._agent_core.generate_document",
            new_callable=AsyncMock,
            return_value=("# 领域模型\n\n...", version_id, None),
        ),
    ):
        response = await client.post(
            "/api/v1/agent/generate-document",
            json={"session_id": session_id, "document_type": "DOMAIN_MODEL"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["document_type"] == "DOMAIN_MODEL"
    assert data["content"] == "# 领域模型\n\n..."
    assert data["version_id"] == version_id
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_get_context_returns_200(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())

    from app.agent.context import AgentContext

    mock_ctx = AgentContext(session_id=session_id)

    with patch(
        "app.routers.v1.agent._context_manager.load",
        new_callable=AsyncMock,
        return_value=mock_ctx,
    ):
        response = await client.get(f"/api/v1/agent/context/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["current_phase"] == "ICEBREAK"
    assert data["phase_label"] == "破冰引入"
    assert data["progress"] == 0.0
    assert "domain_knowledge" in data


@pytest.mark.asyncio
async def test_get_requirement_changes_returns_200(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())

    from app.agent.context import AgentContext

    mock_ctx = AgentContext(session_id=session_id)

    with patch(
        "app.routers.v1.agent._context_manager.load",
        new_callable=AsyncMock,
        return_value=mock_ctx,
    ):
        response = await client.get(
            f"/api/v1/agent/requirement-changes/{session_id}"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert "changes" in data
    assert "stale_documents" in data


@pytest.mark.asyncio
async def test_get_phase_document_returns_200(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())

    from app.agent.context import AgentContext, Phase

    mock_ctx = AgentContext(session_id=session_id)
    mock_ctx.current_phase = Phase.REQUIREMENT

    with patch(
        "app.routers.v1.agent._context_manager.load",
        new_callable=AsyncMock,
        return_value=mock_ctx,
    ):
        response = await client.get(
            f"/api/v1/agent/phase-document/{session_id}/REQUIREMENT"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["phase"] == "REQUIREMENT"
    assert "content" in data
    assert "业务需求草稿" in data["title"]


@pytest.mark.asyncio
async def test_get_phase_document_invalid_phase(auth_client):
    client, mock_user = auth_client
    session_id = str(uuid.uuid4())

    from app.agent.context import AgentContext

    mock_ctx = AgentContext(session_id=session_id)

    with patch(
        "app.routers.v1.agent._context_manager.load",
        new_callable=AsyncMock,
        return_value=mock_ctx,
    ):
        response = await client.get(
            f"/api/v1/agent/phase-document/{session_id}/INVALID_PHASE"
        )

    assert response.status_code == 400
