"""Unit tests for security helpers: password hashing and JWT tokens."""

import uuid
from datetime import timedelta

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_plain_text(self):
        hashed = get_password_hash("mypassword")
        assert hashed != "mypassword"

    def test_hash_starts_with_bcrypt_prefix(self):
        hashed = get_password_hash("mypassword")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_verify_correct_password(self):
        hashed = get_password_hash("correcthorse")
        assert verify_password("correcthorse", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("correcthorse")
        assert verify_password("wronghorse", hashed) is False

    def test_same_password_produces_different_hashes(self):
        # bcrypt uses a random salt each time
        h1 = get_password_hash("same")
        h2 = get_password_hash("same")
        assert h1 != h2


class TestJWT:
    def test_create_and_decode_token(self):
        user_id = uuid.uuid4()
        token = create_access_token(subject=user_id)
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == str(user_id)

    def test_create_token_with_string_subject(self):
        token = create_access_token(subject="user@example.com")
        payload = decode_access_token(token)
        assert payload["sub"] == "user@example.com"

    def test_create_token_with_custom_expiry(self):
        token = create_access_token(subject="test", expires_delta=timedelta(hours=1))
        payload = decode_access_token(token)
        assert payload is not None

    def test_expired_token_returns_none(self):
        token = create_access_token(
            subject="test", expires_delta=timedelta(seconds=-1)
        )
        payload = decode_access_token(token)
        assert payload is None

    def test_invalid_token_returns_none(self):
        payload = decode_access_token("this.is.not.a.valid.jwt")
        assert payload is None

    def test_tampered_token_returns_none(self):
        token = create_access_token(subject="test")
        # Append garbage to signature to invalidate it
        tampered = token + "tampered"
        payload = decode_access_token(tampered)
        assert payload is None
