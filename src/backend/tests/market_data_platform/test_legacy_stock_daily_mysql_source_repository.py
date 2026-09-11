"""Offline contracts for the injected MySQL legacy-source reader.

No test in this module opens MySQL, reads environment configuration, invokes a
route, writes canonical data, or calls AkShare/OpenBB.  The structural fake
engine makes query binding, snapshot cleanup, and manifest sequencing directly
auditable without treating a fixture as production-source evidence.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from app.services.market_data.legacy_stock_daily_mysql_source_repository import (
    LEGACY_STOCK_DAILY_MYSQL_SOURCE_COLUMNS,
    LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
    LegacyStockDailyMySQLSourceRepository,
    LegacyStockDailyMySQLSourceRepositoryError,
    inspect_legacy_stock_daily_mysql_source_schema,
)

UTC = timezone.utc
_SOURCE_SCHEMA = "legacy_market"
_FIXED_COLUMNS = LEGACY_STOCK_DAILY_MYSQL_SOURCE_COLUMNS


class _Result:
    """Minimal SQLAlchemy result double exposing ``mappings().all()``."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, object]]:
        return [dict(row) for row in self._rows]


class _FakeSourceConnection:
    """Captures driver SQL and bound statement inputs without parsing SQL."""

    def __init__(
        self,
        *,
        table_rows: list[dict[str, object]],
        schema_rows: list[dict[str, object]],
        data_rows: list[dict[str, object]],
    ) -> None:
        self._default_table_rows = table_rows
        self._default_schema_rows = schema_rows
        self._table_batches: deque[list[dict[str, object]]] = deque()
        self._schema_batches: deque[list[dict[str, object]]] = deque()
        self._data_rows = data_rows
        self._execute_failures: dict[str, BaseException] = {}
        self.rollback_exception: BaseException | None = None
        self.driver_sql: list[str] = []
        self.executed: list[tuple[str, str, dict[str, object]]] = []
        self.rollback_calls = 0
        self.context_exit_calls = 0

    def queue_schema_batches(self, *batches: list[dict[str, object]]) -> None:
        self._schema_batches = deque(batches)

    def queue_table_batches(self, *batches: list[dict[str, object]]) -> None:
        self._table_batches = deque(batches)

    def fail_execute(self, query_kind: str, exception: BaseException) -> None:
        self._execute_failures[query_kind] = exception

    async def exec_driver_sql(self, statement: str) -> None:
        self.driver_sql.append(statement)

    async def execute(self, statement: Any, parameters: dict[str, object] | None = None) -> _Result:
        query = str(statement)
        bound = dict(parameters or {})
        self.executed.append(("execute", query, bound))
        query_kind = _query_kind(query)
        if failure := self._execute_failures.get(query_kind):
            raise failure
        if query_kind == "table_manifest":
            rows = (
                self._table_batches.popleft() if self._table_batches else self._default_table_rows
            )
            return _Result(rows)
        if query_kind == "column_manifest":
            rows = (
                self._schema_batches.popleft()
                if self._schema_batches
                else self._default_schema_rows
            )
            return _Result(rows)
        if query_kind == "projection":
            return _Result(self._data_rows)
        raise AssertionError(f"unexpected source-reader statement: {query}")

    async def rollback(self) -> None:
        self.rollback_calls += 1
        if self.rollback_exception:
            raise self.rollback_exception


class _FakeConnectionContext:
    def __init__(self, connection: _FakeSourceConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeSourceConnection:
        return self._connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self._connection.context_exit_calls += 1
        return False


class _FakeSourceEngine:
    """An explicitly injected source engine with a configurable dialect name."""

    def __init__(
        self,
        *,
        dialect_name: str = "mysql",
        table_rows: list[dict[str, object]] | None = None,
        schema_rows: list[dict[str, object]] | None = None,
        data_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.dialect = SimpleNamespace(name=dialect_name)
        self.connection = _FakeSourceConnection(
            table_rows=table_rows if table_rows is not None else _table_rows(),
            schema_rows=schema_rows if schema_rows is not None else _schema_rows(),
            data_rows=data_rows if data_rows is not None else _data_rows(),
        )
        self.connect_calls = 0

    def connect(self) -> _FakeConnectionContext:
        self.connect_calls += 1
        return _FakeConnectionContext(self.connection)


def _query_kind(query: str) -> str:
    """Recognize only the three reviewed read statements in the fake source."""
    if "INFORMATION_SCHEMA.TABLES" in query:
        return "table_manifest"
    if "INFORMATION_SCHEMA.COLUMNS" in query:
        return "column_manifest"
    if f"FROM `{_SOURCE_SCHEMA}`.`{LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE}`" in query:
        return "projection"
    return "unexpected"


def _table_rows(
    *,
    table_type: str = "BASE TABLE",
    storage_engine: str | None = "InnoDB",
) -> list[dict[str, object]]:
    return [{"table_type": table_type, "storage_engine": storage_engine}]


def _schema_rows(
    *,
    close_column_type: str = "DECIMAL(12,4)",
    open_column_default: str | None = None,
    symbol_column_default: str | None = None,
) -> list[dict[str, object]]:
    """Return realistic MySQL information-schema rows for the fixed projection."""
    definitions = (
        (
            "symbol",
            "CHAR(6)",
            "PRI",
            symbol_column_default,
            None,
            "utf8mb4_bin",
            "utf8mb4",
        ),
        ("data_date", "DATE", "PRI", None, None, None, None),
        ("开盘", "DECIMAL(12,4)", "", open_column_default, None, None, None),
        ("最高", "DECIMAL(12,4)", "", None, None, None, None),
        ("最低", "DECIMAL(12,4)", "", None, None, None, None),
        ("收盘", close_column_type, "", None, None, None, None),
        ("成交量", "BIGINT", "", None, None, None, None),
        ("涨跌幅", "DECIMAL(12,4)", "", None, None, None, None),
    )
    return [
        {
            "column_name": name,
            "ordinal_position": ordinal,
            "column_type": column_type,
            "is_nullable": "NO",
            "column_key": column_key,
            "column_default": default,
            "extra": extra,
            "collation_name": collation,
            "character_set_name": character_set,
        }
        for ordinal, (
            name,
            column_type,
            column_key,
            default,
            extra,
            collation,
            character_set,
        ) in enumerate(
            definitions,
            start=1,
        )
    ]


def _data_rows() -> list[dict[str, object]]:
    """Source rows include an unreviewed extra key which must be discarded."""
    return [
        {
            "symbol": "600000",
            "data_date": date(2026, 9, 7),
            "开盘": "10.00",
            "最高": "10.70",
            "最低": "9.80",
            "收盘": "10.50",
            "成交量": 123_400,
            "涨跌幅": "2.94",
            "unreviewed_extra": "must-not-escape-fixed-projection",
        }
    ]


async def _candidate_digest(engine: _FakeSourceEngine) -> str:
    schema = await inspect_legacy_stock_daily_mysql_source_schema(
        engine,
        source_schema=_SOURCE_SCHEMA,
    )
    return schema.schema_sha256


@pytest.mark.asyncio
async def test_inspect_returns_stable_candidate_digest_from_fixed_information_schema_projection() -> (
    None
):
    """Candidate inspection is read-only and hashes only the eight reviewed fields."""
    first = _FakeSourceEngine()
    second = _FakeSourceEngine()

    first_schema = await inspect_legacy_stock_daily_mysql_source_schema(
        first,
        source_schema=_SOURCE_SCHEMA,
    )
    second_schema = await inspect_legacy_stock_daily_mysql_source_schema(
        second,
        source_schema=_SOURCE_SCHEMA,
    )

    assert first_schema.schema_sha256 == second_schema.schema_sha256
    assert first_schema.source_schema == _SOURCE_SCHEMA
    assert first_schema.table_name == LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE
    assert first_schema.table_type == "BASE TABLE"
    assert first_schema.storage_engine == "INNODB"
    assert first_schema.source_columns == _FIXED_COLUMNS
    assert first.connection.driver_sql == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY",
    ]
    assert first.connection.rollback_calls == 1
    table_query, schema_query = first.connection.executed
    assert "INFORMATION_SCHEMA.TABLES" in table_query[1]
    assert table_query[2] == {
        "source_schema": _SOURCE_SCHEMA,
        "table_name": LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
    }
    assert "INFORMATION_SCHEMA.COLUMNS" in schema_query[1]
    assert schema_query[2] == {
        "source_schema": _SOURCE_SCHEMA,
        "table_name": LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
        "source_columns": _FIXED_COLUMNS,
    }


@pytest.mark.asyncio
async def test_non_innodb_or_non_base_table_is_rejected_before_any_projection_can_run() -> None:
    """A view or nontransactional table cannot make the snapshot claim true."""
    invalid_tables = (
        _table_rows(table_type="VIEW", storage_engine="InnoDB"),
        _table_rows(table_type="BASE TABLE", storage_engine="MyISAM"),
    )
    for table_rows in invalid_tables:
        engine = _FakeSourceEngine(table_rows=table_rows)
        with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as rejected:
            await inspect_legacy_stock_daily_mysql_source_schema(
                engine,
                source_schema=_SOURCE_SCHEMA,
            )
        assert rejected.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_STORAGE_UNSUPPORTED"
        assert [_query_kind(statement) for _, statement, _ in engine.connection.executed] == [
            "table_manifest",
        ]
        assert engine.connection.rollback_calls == 1


@pytest.mark.asyncio
async def test_schema_digest_preserves_semantic_default_text_without_case_or_whitespace_collision() -> (
    None
):
    """Physical defaults form part of the reviewed source definition verbatim."""
    lowercase_spaced = _FakeSourceEngine(
        schema_rows=_schema_rows(symbol_column_default="a  b"),
    )
    uppercase_single_spaced = _FakeSourceEngine(
        schema_rows=_schema_rows(symbol_column_default="A b"),
    )

    first_digest = await _candidate_digest(lowercase_spaced)
    second_digest = await _candidate_digest(uppercase_single_spaced)

    assert first_digest != second_digest


def test_non_mysql_and_unsafe_schema_are_rejected_before_any_source_connection_is_opened() -> None:
    """The reader cannot silently become a SQLite/PostgreSQL or injected-SQL reader."""
    non_mysql = _FakeSourceEngine(dialect_name="sqlite")
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as rejected_engine:
        LegacyStockDailyMySQLSourceRepository(
            non_mysql,
            source_schema=_SOURCE_SCHEMA,
            approved_schema_sha256="a" * 64,
        )
    assert rejected_engine.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_ENGINE_UNSUPPORTED"
    assert non_mysql.connect_calls == 0

    unsafe_schema = _FakeSourceEngine()
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as rejected_schema:
        LegacyStockDailyMySQLSourceRepository(
            unsafe_schema,
            source_schema="legacy_market`; DROP TABLE STOCK_ZH_A_HIST; --",
            approved_schema_sha256="a" * 64,
        )
    assert rejected_schema.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
    assert unsafe_schema.connect_calls == 0


@pytest.mark.asyncio
async def test_read_projection_uses_bound_values_fixed_columns_and_a_single_read_only_snapshot() -> (
    None
):
    """The result cannot expose unreviewed fields or interpolate query input into SQL."""
    engine = _FakeSourceEngine()
    digest = await _candidate_digest(engine)
    engine.connection.driver_sql.clear()
    engine.connection.executed.clear()
    repository = LegacyStockDailyMySQLSourceRepository(
        engine,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=digest,
    )

    batch = await repository.read_projection(
        symbols=("600000", "000001", "600000"),
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        source_schema_sha256=digest,
    )

    assert batch.symbols == ("000001", "600000")
    assert batch.source_schema.schema_sha256 == digest
    assert tuple(batch.rows[0]) == _FIXED_COLUMNS
    assert "unreviewed_extra" not in batch.rows[0]
    with pytest.raises(TypeError):
        batch.rows[0]["symbol"] = "mutate"  # type: ignore[index]

    projection_queries = [
        statement
        for kind, statement, _ in engine.connection.executed
        if kind == "execute"
        and f"FROM `{_SOURCE_SCHEMA}`.`{LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE}`" in statement
    ]
    assert len(projection_queries) == 1
    projection_sql = projection_queries[0]
    assert "SELECT *" not in projection_sql.upper()
    assert "600000" not in projection_sql
    assert "000001" not in projection_sql
    assert "IN (__[POSTCOMPILE_symbols])" in projection_sql
    projection_parameters = next(
        parameters
        for kind, statement, parameters in engine.connection.executed
        if kind == "execute" and statement == projection_sql
    )
    assert projection_parameters == {
        "symbols": ("000001", "600000"),
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 30),
        "row_limit": 5_001,
    }
    assert engine.connection.driver_sql == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY",
    ]
    assert engine.connection.rollback_calls == 2
    assert engine.connection.context_exit_calls == 2
    assert [_query_kind(statement) for _, statement, _ in engine.connection.executed] == [
        "table_manifest",
        "column_manifest",
        "projection",
        "table_manifest",
        "column_manifest",
    ]
    assert all(
        statement.lstrip().upper().startswith("SELECT")
        for _, statement, _ in engine.connection.executed
    )


@pytest.mark.asyncio
async def test_scope_digest_mismatch_and_invalid_query_inputs_fail_before_connecting() -> None:
    """A stale scope or unsafe source selection cannot even open the injected engine."""
    engine = _FakeSourceEngine()
    repository = LegacyStockDailyMySQLSourceRepository(
        engine,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256="a" * 64,
    )
    invalid_cases = (
        {
            "symbols": ("600000",),
            "start_date": date(2026, 9, 1),
            "end_date": date(2026, 9, 2),
            "source_schema_sha256": "b" * 64,
            "code": "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_APPROVAL_MISMATCH",
        },
        {
            "symbols": ("600000 OR 1=1",),
            "start_date": date(2026, 9, 1),
            "end_date": date(2026, 9, 2),
            "source_schema_sha256": "a" * 64,
            "code": "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID",
        },
        {
            "symbols": ("600000",),
            "start_date": datetime(2026, 9, 1, tzinfo=UTC),
            "end_date": date(2026, 9, 2),
            "source_schema_sha256": "a" * 64,
            "code": "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID",
        },
        {
            "symbols": ("600000",),
            "start_date": date(2026, 9, 3),
            "end_date": date(2026, 9, 2),
            "source_schema_sha256": "a" * 64,
            "code": "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID",
        },
        {
            "symbols": ("600000",),
            "start_date": date(2026, 9, 1),
            "end_date": date(2026, 10, 2),
            "source_schema_sha256": "a" * 64,
            "code": "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID",
        },
    )

    for invalid_case in invalid_cases:
        with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as rejected:
            await repository.read_projection(
                symbols=invalid_case["symbols"],  # type: ignore[arg-type]
                start_date=invalid_case["start_date"],  # type: ignore[arg-type]
                end_date=invalid_case["end_date"],  # type: ignore[arg-type]
                source_schema_sha256=invalid_case["source_schema_sha256"],  # type: ignore[arg-type]
            )
        assert rejected.value.code == invalid_case["code"]

    assert engine.connect_calls == 0


@pytest.mark.asyncio
async def test_row_limit_fails_closed_instead_of_buffering_an_unbounded_legacy_range() -> None:
    """The extra row returned by ``LIMIT max+1`` proves the caller must split its batch."""
    engine = _FakeSourceEngine(data_rows=[dict(_data_rows()[0]) for _ in range(5_001)])
    digest = await _candidate_digest(engine)
    repository = LegacyStockDailyMySQLSourceRepository(
        engine,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=digest,
    )
    engine.connection.executed.clear()

    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as rejected:
        await repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=digest,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_ROW_LIMIT_EXCEEDED"
    assert [_query_kind(statement) for _, statement, _ in engine.connection.executed] == [
        "table_manifest",
        "column_manifest",
        "projection",
    ]
    assert engine.connection.rollback_calls == 2


@pytest.mark.asyncio
async def test_unapproved_or_changed_physical_schema_is_never_used_for_data_projection() -> None:
    """A schema mismatch stops before data, while a later change invalidates the batch."""
    engine = _FakeSourceEngine()
    digest = await _candidate_digest(engine)
    repository = LegacyStockDailyMySQLSourceRepository(
        engine,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=digest,
    )
    engine.connection.executed.clear()
    engine.connection.driver_sql.clear()
    engine.connection.queue_schema_batches(_schema_rows(close_column_type="DECIMAL(18,8)"))

    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as mismatched:
        await repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=digest,
        )

    assert mismatched.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_APPROVAL_MISMATCH"
    assert all(
        f"FROM `{_SOURCE_SCHEMA}`.`{LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE}`" not in statement
        for _, statement, _ in engine.connection.executed
    )

    engine.connection.executed.clear()
    engine.connection.driver_sql.clear()
    engine.connection.queue_schema_batches(
        _schema_rows(),
        _schema_rows(close_column_type="DECIMAL(18,8)"),
    )
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as changed:
        await repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=digest,
        )

    assert changed.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_CHANGED_DURING_READ"
    assert (
        sum(
            f"FROM `{_SOURCE_SCHEMA}`.`{LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE}`" in statement
            for _, statement, _ in engine.connection.executed
        )
        == 1
    )
    assert engine.connection.rollback_calls == 3

    engine.connection.executed.clear()
    engine.connection.queue_table_batches(
        _table_rows(),
        _table_rows(table_type="BASE TABLE", storage_engine="MyISAM"),
    )
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as changed_storage:
        await repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=digest,
        )
    assert changed_storage.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_STORAGE_UNSUPPORTED"
    assert [_query_kind(statement) for _, statement, _ in engine.connection.executed] == [
        "table_manifest",
        "column_manifest",
        "projection",
        "table_manifest",
    ]
    assert engine.connection.rollback_calls == 4


@pytest.mark.asyncio
async def test_missing_source_schema_column_or_malformed_projection_row_fails_closed_and_rolls_back() -> (
    None
):
    """The reader never manufacture a batch from incomplete schema or data evidence."""
    malformed_schema_engine = _FakeSourceEngine(schema_rows=_schema_rows()[:-1])
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as malformed_schema:
        await inspect_legacy_stock_daily_mysql_source_schema(
            malformed_schema_engine,
            source_schema=_SOURCE_SCHEMA,
        )
    assert malformed_schema.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
    assert malformed_schema_engine.connection.rollback_calls == 1

    malformed_row = dict(_data_rows()[0])
    malformed_row.pop("成交量")
    row_engine = _FakeSourceEngine(data_rows=[malformed_row])
    digest = await _candidate_digest(row_engine)
    repository = LegacyStockDailyMySQLSourceRepository(
        row_engine,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=digest,
    )
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as malformed_row:
        await repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=digest,
        )
    assert malformed_row.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_ROW_INVALID"
    assert row_engine.connection.rollback_calls == 2


@pytest.mark.asyncio
async def test_source_failure_cancellation_and_cleanup_failure_always_attempt_snapshot_rollback() -> (
    None
):
    """A fault never turns the reader into a leaked transaction or hidden cleanup pass."""
    database_failure = _FakeSourceEngine()
    digest = await _candidate_digest(database_failure)
    failing_repository = LegacyStockDailyMySQLSourceRepository(
        database_failure,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=digest,
    )
    database_failure.connection.fail_execute(
        "projection",
        OperationalError("SELECT", {}, RuntimeError("fixture source failure")),
    )
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as query_rejected:
        await failing_repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=digest,
        )
    assert query_rejected.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_READ_FAILED"
    assert database_failure.connection.rollback_calls == 2

    cancelled = _FakeSourceEngine()
    cancel_digest = await _candidate_digest(cancelled)
    cancelled_repository = LegacyStockDailyMySQLSourceRepository(
        cancelled,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=cancel_digest,
    )
    cancelled.connection.fail_execute("projection", asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await cancelled_repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=cancel_digest,
        )
    assert cancelled.connection.rollback_calls == 2

    cleanup_failure = _FakeSourceEngine()
    cleanup_digest = await _candidate_digest(cleanup_failure)
    cleanup_failure.connection.rollback_exception = OperationalError(
        "ROLLBACK",
        {},
        RuntimeError("fixture rollback failure"),
    )
    cleanup_repository = LegacyStockDailyMySQLSourceRepository(
        cleanup_failure,
        source_schema=_SOURCE_SCHEMA,
        approved_schema_sha256=cleanup_digest,
    )
    with pytest.raises(LegacyStockDailyMySQLSourceRepositoryError) as cleanup_rejected:
        await cleanup_repository.read_projection(
            symbols=("600000",),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            source_schema_sha256=cleanup_digest,
        )
    assert cleanup_rejected.value.code == "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SNAPSHOT_CLEANUP_FAILED"
    assert cleanup_failure.connection.rollback_calls == 2
