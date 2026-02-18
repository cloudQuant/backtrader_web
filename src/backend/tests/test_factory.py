"""
Database factory tests
"""
import pytest
from unittest.mock import patch
from app.db.factory import get_repository
from app.models.user import User
from app.db.sql_repository import SQLRepository


class TestGetRepository:
    def test_sqlite_returns_sql_repo(self):
        repo = get_repository(User)
        assert isinstance(repo, SQLRepository)

    def test_mongodb_raises(self):
        with patch("app.db.factory.get_settings") as mock_settings:
            mock_settings.return_value.DATABASE_TYPE = "mongodb"
            with pytest.raises(NotImplementedError, match="MongoDB"):
                get_repository(User)

    def test_unknown_raises(self):
        with patch("app.db.factory.get_settings") as mock_settings:
            mock_settings.return_value.DATABASE_TYPE = "unknown_db"
            with pytest.raises(ValueError, match="Unsupported database type"):
                get_repository(User)
