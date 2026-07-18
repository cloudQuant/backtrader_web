"""
Configuration module tests.
"""

from app.config import Settings, get_settings


class TestConfig:
    """Configuration tests."""

    def test_get_settings_returns_settings(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_default_values(self, monkeypatch):
        """Defaults do not inherit a developer's dotenv schema flags."""
        monkeypatch.delenv("DB_AUTO_CREATE_SCHEMA", raising=False)
        monkeypatch.delenv("DB_AUTO_CREATE_DEFAULT_ADMIN", raising=False)
        settings = Settings(_env_file=None, DEBUG=True)
        assert settings.APP_NAME == "ai-for-investor"
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.JWT_EXPIRE_MINUTES > 0
        assert settings.PORT == 8000
        assert settings.DB_AUTO_CREATE_SCHEMA is False
        assert settings.DB_AUTO_CREATE_DEFAULT_ADMIN is False
        assert "openai" in settings.AI_PROVIDERS
        assert "ollama" in settings.AI_PROVIDERS
        assert "volcengine_ark" in settings.AI_PROVIDERS
        assert "siliconflow" in settings.AI_PROVIDERS

    def test_settings_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # lru_cache should return same instance

    def test_ai_providers_can_be_loaded_from_json_string(self):
        settings = Settings(
            AI_PROVIDERS=(
                '{"local": {"base_url": "http://localhost:11434", '
                '"api_key_env": null, "models": ["ollama/qwen2.5-coder:7b"]}}'
            )
        )

        assert settings.AI_PROVIDERS["local"]["base_url"] == "http://localhost:11434"
        assert settings.AI_PROVIDERS["local"]["models"] == ["ollama/qwen2.5-coder:7b"]
