from datetime import datetime

import pandas as pd
import pytest

from app.data_fetch.core.mysql_base import MysqlBase
from app.data_fetch.providers.akshare_to_mysql import FuncThread
from app.data_fetch.utils.common_utils import retry_on_exception


def test_func_thread_preserves_exception_type():
    def always_timeout():
        raise TimeoutError("slow upstream")

    thread = FuncThread(always_timeout)
    thread.daemon = True
    thread.start()

    status, result = thread.get_result(timeout=1)

    assert status == "error"
    assert isinstance(result, TimeoutError)


def test_retry_on_exception_stops_on_configured_exception():
    attempts = 0

    @retry_on_exception(max_retries=3, retry_delay=0, stop_exceptions=(TimeoutError,))
    def always_timeout():
        nonlocal attempts
        attempts += 1
        raise TimeoutError("slow upstream")

    with pytest.raises(TimeoutError):
        always_timeout()

    assert attempts == 1


def test_insert_data_converts_pandas_missing_values_to_none(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = None

        def executemany(self, sql, data):
            self.executed = (sql, data)

    class FakeConnection:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    service = MysqlBase({})
    cursor = FakeCursor()
    connection = FakeConnection()
    service.cursor = cursor
    service.connection = connection
    monkeypatch.setattr(service, "connect_db", lambda: None)
    monkeypatch.setattr(service, "disconnect_db", lambda: None)

    df = pd.DataFrame(
        {
            "A": [float("nan")],
            "B": [pd.NA],
            "C": [pd.NaT],
            "D": [1.25],
        }
    )

    assert service.insert_data(df, "SOME_TABLE", ["A", "B", "C", "D"]) is True
    assert cursor.executed == (
        "INSERT INTO `SOME_TABLE` (`A`, `B`, `C`, `D`) VALUES (%s, %s, %s, %s)",
        [[None, None, None, 1.25]],
    )
    assert connection.committed is True


def test_insert_data_converts_pandas_timestamp_to_datetime(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = None

        def executemany(self, sql, data):
            self.executed = (sql, data)

    class FakeConnection:
        def commit(self):
            pass

        def rollback(self):
            pass

    service = MysqlBase({})
    cursor = FakeCursor()
    service.cursor = cursor
    service.connection = FakeConnection()
    monkeypatch.setattr(service, "connect_db", lambda: None)
    monkeypatch.setattr(service, "disconnect_db", lambda: None)

    df = pd.DataFrame({"FETCHED_AT": [pd.Timestamp("2026-06-22 00:00:01")]})

    assert service.insert_data(df, "SOME_TABLE", ["FETCHED_AT"]) is True
    assert cursor.executed == (
        "INSERT INTO `SOME_TABLE` (`FETCHED_AT`) VALUES (%s)",
        [[datetime(2026, 6, 22, 0, 0, 1)]],
    )


def test_insert_data_quotes_keyword_column_names(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = None

        def executemany(self, sql, data):
            self.executed = (sql, data)

    class FakeConnection:
        def commit(self):
            pass

        def rollback(self):
            pass

    service = MysqlBase({})
    cursor = FakeCursor()
    service.cursor = cursor
    service.connection = FakeConnection()
    monkeypatch.setattr(service, "connect_db", lambda: None)
    monkeypatch.setattr(service, "disconnect_db", lambda: None)

    df = pd.DataFrame({"condition": ["小于7天"], "fee_rate": [1.5]})

    assert service.insert_data(df, "FUND_TRADING_RULES_XQ", ["condition", "fee_rate"]) is True
    assert cursor.executed == (
        "INSERT INTO `FUND_TRADING_RULES_XQ` (`condition`, `fee_rate`) VALUES (%s, %s)",
        [["小于7天", 1.5]],
    )


def test_save_data_adds_missing_columns_before_insert(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.table_columns = [("R_ID",), ("data_date",)]
            self.fetchone_value = None
            self.executed_sql = []
            self.inserted = None

        def execute(self, sql):
            self.executed_sql.append(sql)
            if sql.startswith("SHOW TABLES LIKE"):
                self.fetchone_value = ("OPTION_SSE_CODES_SINA",)
            elif sql.startswith("SHOW COLUMNS FROM"):
                self.fetchone_value = None
            elif sql.startswith("ALTER TABLE") and "期权代码" in sql:
                self.table_columns.append(("期权代码",))

        def fetchone(self):
            value = self.fetchone_value
            self.fetchone_value = None
            return value

        def fetchall(self):
            return self.table_columns

        def executemany(self, sql, data):
            self.inserted = (sql, data)

    class FakeConnection:
        def commit(self):
            pass

        def rollback(self):
            pass

    service = MysqlBase({})
    cursor = FakeCursor()
    service.cursor = cursor
    service.connection = FakeConnection()
    monkeypatch.setattr(service, "connect_db", lambda: None)
    monkeypatch.setattr(service, "disconnect_db", lambda: None)

    df = pd.DataFrame({"期权代码": ["10000001"], "data_date": ["2026-06-21"]})

    assert service.save_data(df, "OPTION_SSE_CODES_SINA", ignore_duplicates=True) == 1
    assert any(
        sql == "ALTER TABLE `OPTION_SSE_CODES_SINA` ADD COLUMN `期权代码` TEXT NULL"
        for sql in cursor.executed_sql
    )
    assert cursor.inserted == (
        "INSERT IGNORE INTO `OPTION_SSE_CODES_SINA` (`期权代码`, `data_date`) VALUES (%s, %s)",
        [["10000001", "2026-06-21"]],
    )


def test_save_data_drops_columns_that_failed_auto_add(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.table_columns = [("R_ID",), ("data_date",)]
            self.fetchone_value = None
            self.executed_sql = []
            self.inserted = None

        def execute(self, sql):
            self.executed_sql.append(sql)
            if sql.startswith("SHOW TABLES LIKE"):
                self.fetchone_value = ("WIDE_TABLE",)
            elif sql.startswith("SHOW COLUMNS FROM"):
                self.fetchone_value = None
            elif sql.startswith("ALTER TABLE") and "known_new" in sql:
                self.table_columns.append(("known_new",))
            elif sql.startswith("ALTER TABLE") and "too_wide" in sql:
                raise RuntimeError("row size too large")

        def fetchone(self):
            value = self.fetchone_value
            self.fetchone_value = None
            return value

        def fetchall(self):
            return self.table_columns

        def executemany(self, sql, data):
            self.inserted = (sql, data)

    class FakeConnection:
        def commit(self):
            pass

        def rollback(self):
            pass

    service = MysqlBase({})
    cursor = FakeCursor()
    service.cursor = cursor
    service.connection = FakeConnection()
    monkeypatch.setattr(service, "connect_db", lambda: None)
    monkeypatch.setattr(service, "disconnect_db", lambda: None)

    df = pd.DataFrame(
        {
            "known_new": ["ok"],
            "too_wide": ["drop me"],
            "data_date": ["2026-06-21"],
        }
    )

    assert service.save_data(df, "WIDE_TABLE", ignore_duplicates=True) == 1
    assert cursor.inserted == (
        "INSERT IGNORE INTO `WIDE_TABLE` (`known_new`, `data_date`) VALUES (%s, %s)",
        [["ok", "2026-06-21"]],
    )
