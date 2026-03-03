"""Tests for the user registration, login, and profile endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_user

# ---------------------------------------------------------------------------
# POST /api/v1/users/register
# ---------------------------------------------------------------------------

REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "username": "alice",
    "full_name": "Alice",
    "password": "securepass",
}


@pytest.mark.asyncio
async def test_register_success(client):
    user = make_user(email="alice@example.com", username="alice", full_name="Alice")
    with patch("app.routers.v1.users.user_crud") as mock_crud:
        mock_crud.get_by_email = AsyncMock(return_value=None)
        mock_crud.get_by_username = AsyncMock(return_value=None)
        mock_crud.create = AsyncMock(return_value=user)

        response = await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["username"] == "alice"
    assert "id" in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client):
    existing = make_user(email="alice@example.com")
    with patch("app.routers.v1.users.user_crud") as mock_crud:
        mock_crud.get_by_email = AsyncMock(return_value=existing)

        response = await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_duplicate_username_returns_409(client):
    existing = make_user(username="alice")
    with patch("app.routers.v1.users.user_crud") as mock_crud:
        mock_crud.get_by_email = AsyncMock(return_value=None)
        mock_crud.get_by_username = AsyncMock(return_value=existing)

        response = await client.post("/api/v1/users/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client):
    payload = {**REGISTER_PAYLOAD, "password": "short"}
    response = await client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client):
    payload = {**REGISTER_PAYLOAD, "email": "not-an-email"}
    response = await client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/users/login
# ---------------------------------------------------------------------------

LOGIN_PAYLOAD = {"email": "alice@example.com", "password": "securepass"}


@pytest.mark.asyncio
async def test_login_success(client):
    user = make_user(email="alice@example.com")
    with patch("app.routers.v1.users.user_crud") as mock_crud:
        mock_crud.authenticate = AsyncMock(return_value=user)

        response = await client.post("/api/v1/users/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data


@pytest.mark.asyncio
async def test_login_wrong_credentials_returns_401(client):
    with patch("app.routers.v1.users.user_crud") as mock_crud:
        mock_crud.authenticate = AsyncMock(return_value=None)

        response = await client.post("/api/v1/users/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(client):
    user = make_user(is_active=False)
    with patch("app.routers.v1.users.user_crud") as mock_crud:
        mock_crud.authenticate = AsyncMock(return_value=user)

        response = await client.post("/api/v1/users/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/users/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_without_token_returns_403(client):
    # No Authorization header → HTTPBearer returns 403
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_me_with_invalid_token_returns_401(client):
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client):
    from app.core.security import create_access_token

    user = make_user()
    token = create_access_token(subject=user.id)

    with patch("app.core.dependencies.user_crud") as mock_crud:
        mock_crud.get_by_id = AsyncMock(return_value=user)

        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user.email
    assert data["username"] == user.username
