"""Unit tests for custom HTTP exception classes."""

import pytest
from fastapi import status

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)


class TestNotFoundException:
    def test_default_status_code(self):
        exc = NotFoundException()
        assert exc.status_code == status.HTTP_404_NOT_FOUND

    def test_default_detail(self):
        exc = NotFoundException()
        assert exc.detail == "Resource not found"

    def test_custom_detail(self):
        exc = NotFoundException("User not found")
        assert exc.detail == "User not found"


class TestUnauthorizedException:
    def test_status_code(self):
        exc = UnauthorizedException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED

    def test_www_authenticate_header(self):
        exc = UnauthorizedException()
        assert exc.headers is not None
        assert exc.headers.get("WWW-Authenticate") == "Bearer"

    def test_custom_detail(self):
        exc = UnauthorizedException("Token expired")
        assert exc.detail == "Token expired"


class TestForbiddenException:
    def test_status_code(self):
        exc = ForbiddenException()
        assert exc.status_code == status.HTTP_403_FORBIDDEN

    def test_default_detail(self):
        exc = ForbiddenException()
        assert exc.detail == "Forbidden"


class TestConflictException:
    def test_status_code(self):
        exc = ConflictException()
        assert exc.status_code == status.HTTP_409_CONFLICT

    def test_default_detail(self):
        exc = ConflictException()
        assert exc.detail == "Resource already exists"

    def test_custom_detail(self):
        exc = ConflictException("Email already registered")
        assert exc.detail == "Email already registered"


class TestBadRequestException:
    def test_status_code(self):
        exc = BadRequestException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST

    def test_default_detail(self):
        exc = BadRequestException()
        assert exc.detail == "Bad request"
