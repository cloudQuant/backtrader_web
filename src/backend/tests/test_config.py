"""
配置模块测试
"""
from app.config import get_settings, Settings


class TestConfig:
    """配置测试"""

    def test_get_settings_returns_settings(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_default_values(self):
        settings = get_settings()
        assert settings.APP_NAME == "backtrader_web"
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.JWT_EXPIRE_MINUTES > 0
        assert settings.PORT == 8000

    def test_settings_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # lru_cache should return same instance
