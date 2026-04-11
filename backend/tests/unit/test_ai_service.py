"""Unit tests for ai_service.get_ai_client()."""

from unittest.mock import patch, MagicMock

import pytest

from app.services.ai_service import get_ai_client


class TestGetAiClientValidation:
    """get_ai_client raises ValueError for unknown providers and empty API keys."""

    def test_unsupported_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            get_ai_client("unknown")

    def test_empty_openai_key_raises_value_error(self):
        mock_settings = MagicMock()
        mock_settings.OPENAI_API_KEY = ""
        with patch("app.services.ai_service.settings", mock_settings):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                get_ai_client("openai")

    def test_empty_deepseek_key_raises_value_error(self):
        mock_settings = MagicMock()
        mock_settings.DEEPSEEK_API_KEY = ""
        with patch("app.services.ai_service.settings", mock_settings):
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
                get_ai_client("deepseek")

    def test_empty_minimax_key_raises_value_error(self):
        mock_settings = MagicMock()
        mock_settings.MINIMAX_API_KEY = ""
        with patch("app.services.ai_service.settings", mock_settings):
            with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
                get_ai_client("minimax")

    def test_valid_minimax_key_returns_client_and_model(self):
        mock_settings = MagicMock()
        mock_settings.MINIMAX_API_KEY = "test-key"
        mock_settings.MINIMAX_BASE_URL = "https://api.minimax.chat/v1"
        mock_settings.MINIMAX_MODEL = "MiniMax-Text-01"
        with patch("app.services.ai_service.settings", mock_settings):
            client, model = get_ai_client("minimax")
        assert model == "MiniMax-Text-01"
        assert client is not None

    def test_minimax_default_base_url_is_domestic(self):
        """Default base URL should point to the domestic China endpoint."""
        from app.config import settings as real_settings
        assert "minimax.chat" in real_settings.MINIMAX_BASE_URL
        assert "minimaxi" not in real_settings.MINIMAX_BASE_URL
