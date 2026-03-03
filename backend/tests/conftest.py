import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database.session import get_db
from app.main import app


def make_user(**overrides) -> SimpleNamespace:
    """Return a SimpleNamespace that mimics a User ORM row.

    Pydantic v2 with ``from_attributes = True`` reads attributes off the
    object, so SimpleNamespace works as a lightweight stand-in for a real
    SQLAlchemy model instance.
    """
    defaults = dict(
        id=uuid.uuid4(),
        email="test@example.com",
        username="testuser",
        full_name="Test User",
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
async def client():
    """AsyncClient pointing at the ASGI app with the DB dependency stubbed out."""

    async def mock_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = mock_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
