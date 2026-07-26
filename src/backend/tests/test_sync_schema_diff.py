"""Unit tests for the extracted ``app.services.sync.schema_diff`` module.

These cover the pure schema-diff / SQL-building half of ``SyncService`` that
was pulled out of ``sync_service.py`` (P1#5). The goal is to lock the behavior
of the data-replication SQL synthesis so future refactors of the (high-risk)
transport layer can't silently change generated DDL/DML.
"""

import json

import pytest

from app.services.sync import schema_diff as sd


class TestQuoting:
    def test_quote_sql_string_escapes_single_quotes(self):
        assert sd.quote_sql_string("a'b") == "'a''b'"

    def test_quote_identifier_escapes_backticks(self):
        assert sd.quote_identifier("a`b") == "`a``b`"


class TestIdentifierValidation:
    def test_validate_mysql_identifier_accepts_expected_names(self):
        assert (
            sd.validate_mysql_identifier("ai_for_investor_01", "database") == "ai_for_investor_01"
        )

    def test_validate_mysql_identifier_rejects_shell_sql_metacharacters(self):
        with pytest.raises(ValueError, match="非法 MySQL database"):
            sd.validate_mysql_identifier("prod;DROP_TABLE", "database")

    def test_sql_builders_reject_invalid_database_name(self):
        with pytest.raises(ValueError):
            sd.build_database_exists_sql("bad`name")

    def test_metadata_parser_rejects_invalid_table_name(self):
        payload = _summary([["TABLE", "bad;table", "BASE TABLE", "InnoDB", ""]])
        with pytest.raises(ValueError):
            sd.parse_schema_summary(payload)

    def test_missing_where_builder_rejects_invalid_column_name(self):
        with pytest.raises(ValueError):
            sd.build_missing_keys_where_sql(("id;DROP",), [("1",)])


class TestSummarySql:
    def test_database_info_sql_in_clause(self):
        sql = sd.build_database_info_sql(["a", "b"])
        assert "TABLE_SCHEMA IN ('a', 'b')" in sql
        assert "GROUP BY TABLE_SCHEMA" in sql

    def test_database_exists_sql(self):
        assert sd.build_database_exists_sql("db1").endswith("LIMIT 1")
        assert "SCHEMA_NAME = 'db1'" in sd.build_database_exists_sql("db1")

    def test_ensure_database_sql_uses_utf8mb4(self):
        sql = sd.build_ensure_database_sql("db1")
        assert sql.startswith("CREATE DATABASE IF NOT EXISTS `db1`")
        assert "utf8mb4" in sql

    def test_summary_sql_list_has_four_entries(self):
        items = sd.build_schema_summary_sql_list("db1")
        assert len(items) == 4
        assert all("'db1'" in entry for entry in items)

    def test_row_hash_expression(self):
        expr = sd.build_row_hash_expression(("id", "name"))
        assert expr == "SHA2(CAST(JSON_ARRAY(`id`, `name`) AS CHAR), 256)"

    def test_table_key_values_sql(self):
        sql = sd.build_table_key_values_sql("db", "t", ("id",))
        assert sql == "SELECT `id` FROM `db`.`t`"


class TestIncrementalKeyHelpers:
    def test_select_incremental_key_columns_prefers_primary(self):
        stdout = "\n".join(
            [
                "PRIMARY\t0\t1\tid",
                "idx_name\t0\t1\tname",
            ]
        )
        assert sd.select_incremental_key_columns(stdout) == ("id",)

    def test_select_incremental_key_columns_falls_back_to_first_index(self):
        stdout = "idx_name\t0\t2\tb\nidx_name\t0\t1\ta"
        # parts must order by seq_in_index
        assert sd.select_incremental_key_columns(stdout) == ("a", "b")

    def test_select_incremental_key_columns_empty(self):
        assert sd.select_incremental_key_columns("") == ()

    def test_parse_table_columns_raises_when_empty(self):
        with pytest.raises(RuntimeError):
            sd.parse_table_columns("\n  \n", "db", "t")

    def test_parse_table_columns_ok(self):
        assert sd.parse_table_columns("id\nname\n", "db", "t") == ("id", "name")

    def test_build_missing_rows_multiset_semantics(self):
        source = [("a",), ("a",), ("b",)]
        target = [("a",)]
        assert sd.build_missing_rows(source, target) == [("a",), ("b",)]

    def test_parse_key_rows_null_token(self):
        rows = sd.parse_key_rows("1\\tx\n2\\t\\N".replace("\\t", "\t"), 2)
        assert rows == [("1", "x"), ("2", None)]

    def test_parse_key_rows_skips_wrong_arity(self):
        rows = sd.parse_key_rows("1\t2\n3", 2)
        assert rows == [("1", "2")]

    def test_chunk_keys(self):
        keys = [("1",), ("2",), ("3",)]
        assert sd.chunk_keys(keys, 2) == [[("1",), ("2",)], [("3",)]]

    def test_build_missing_keys_where_sql_null_and_value(self):
        where = sd.build_missing_keys_where_sql(("id", "name"), [("1", None)])
        assert where == "(`id` = '1' AND `name` IS NULL)"

    def test_build_missing_keys_where_sql_empty(self):
        assert sd.build_missing_keys_where_sql(("id",), []) == "1 = 0"

    def test_build_missing_row_hashes_where_sql_empty(self):
        assert sd.build_missing_row_hashes_where_sql(("id",), []) == "1 = 0"

    def test_build_missing_row_hashes_where_sql_values(self):
        out = sd.build_missing_row_hashes_where_sql(("id",), [("abc",)])
        assert "IN ('abc')" in out


def _summary(payload_rows: list[list]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in payload_rows)


class TestSchemaSummaryAndDelta:
    def test_parse_schema_summary_roundtrip(self):
        payload = _summary(
            [
                ["TABLE", "t1", "BASE TABLE", "InnoDB", "utf8mb4_unicode_ci"],
                ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "auto_increment", "", ""],
                ["INDEX", "t1", "PRIMARY", 0, 1, "id", -1, "", "BTREE"],
                ["VIEW", "v1", "select 1", "", "YES", "DEFINER"],
            ]
        )
        summary = sd.parse_schema_summary(payload)
        assert summary["tables"]["t1"]["engine"] == "InnoDB"
        assert "id" in summary["columns"]["t1"]
        assert "signature" in summary["indexes"]["t1"]["PRIMARY"]
        assert "v1" in summary["views"]

    def test_parse_schema_summary_ignores_malformed_lines(self):
        payload = "not-json\n" + _summary([["TABLE", "t1", "BASE TABLE", "InnoDB", ""]])
        summary = sd.parse_schema_summary(payload)
        assert "t1" in summary["tables"]

    def test_build_schema_delta_missing_table(self):
        source = sd.parse_schema_summary(_summary([["TABLE", "t1", "BASE TABLE", "InnoDB", ""]]))
        target = sd.parse_schema_summary(_summary([]))
        delta = sd.build_schema_delta(source, target)
        assert delta["missing_tables"] == ["t1"]
        assert sd.schema_delta_is_empty(delta) is False

    def test_build_schema_delta_add_column(self):
        source = sd.parse_schema_summary(
            _summary(
                [
                    ["TABLE", "t1", "BASE TABLE", "InnoDB", ""],
                    ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "", "", ""],
                    ["COLUMN", "t1", 2, "name", "varchar(10)", "YES", "__SYNC_NULL__", "", "", ""],
                ]
            )
        )
        target = sd.parse_schema_summary(
            _summary(
                [
                    ["TABLE", "t1", "BASE TABLE", "InnoDB", ""],
                    ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "", "", ""],
                ]
            )
        )
        delta = sd.build_schema_delta(source, target)
        assert delta["table_changes"]["t1"]["add_columns"] == ["name"]

    def test_build_schema_delta_empty_when_identical(self):
        payload = _summary(
            [
                ["TABLE", "t1", "BASE TABLE", "InnoDB", ""],
                ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "", "", ""],
            ]
        )
        summary = sd.parse_schema_summary(payload)
        # parse twice to avoid shared-mutable aliasing
        delta = sd.build_schema_delta(summary, sd.parse_schema_summary(payload))
        assert sd.schema_delta_is_empty(delta) is True


class TestCreateTableParsing:
    CREATE_SQL = (
        "CREATE TABLE `t1` (\n"
        "  `id` int NOT NULL AUTO_INCREMENT,\n"
        "  `name` varchar(20) DEFAULT NULL,\n"
        "  PRIMARY KEY (`id`),\n"
        "  UNIQUE KEY `uq_name` (`name`)\n"
        ") ENGINE=InnoDB;"
    )

    def test_extract_create_table_statement(self):
        out = sd.extract_create_table_statement(self.CREATE_SQL, "t1")
        assert out.startswith("CREATE TABLE `t1`")

    def test_extract_create_table_statement_missing(self):
        with pytest.raises(RuntimeError):
            sd.extract_create_table_statement("nothing here", "t1")

    def test_extract_create_table_definitions(self):
        parsed = sd.extract_create_table_definitions(self.CREATE_SQL, "t1")
        assert "id" in parsed["columns"]
        assert "name" in parsed["columns"]
        assert "PRIMARY" in parsed["indexes"]
        assert "uq_name" in parsed["indexes"]

    def test_parenthesized_column_type_not_truncated(self):
        """Regression: a naive non-greedy ``\\(.*?\\)`` stopped at the first
        ``)`` inside ``varchar(20)`` / ``decimal(10,2)``, truncating the column
        definition and dropping all indexes. The balanced-paren scanner must
        keep the full type and still see every index."""
        create_sql = (
            "CREATE TABLE `t2` (\n"
            "  `id` int NOT NULL,\n"
            "  `price` decimal(10,2) DEFAULT NULL,\n"
            "  `label` varchar(64) DEFAULT NULL,\n"
            "  PRIMARY KEY (`id`),\n"
            "  KEY `idx_label` (`label`)\n"
            ") ENGINE=InnoDB;"
        )
        parsed = sd.extract_create_table_definitions(create_sql, "t2")
        assert parsed["columns"]["price"] == "`price` decimal(10,2) DEFAULT NULL"
        assert parsed["columns"]["label"] == "`label` varchar(64) DEFAULT NULL"
        assert "PRIMARY" in parsed["indexes"]
        assert "idx_label" in parsed["indexes"]

    def test_string_default_with_paren_does_not_break_scan(self):
        create_sql = (
            "CREATE TABLE `t3` (\n"
            "  `id` int NOT NULL,\n"
            "  `note` varchar(50) DEFAULT 'a)b',\n"
            "  PRIMARY KEY (`id`)\n"
            ") ENGINE=InnoDB;"
        )
        parsed = sd.extract_create_table_definitions(create_sql, "t3")
        assert parsed["columns"]["note"] == "`note` varchar(50) DEFAULT 'a)b'"
        assert "PRIMARY" in parsed["indexes"]

    def test_build_column_position_clause_after(self):
        clause = sd.build_column_position_clause(["id", "name"], {"id"}, "name")
        assert clause == " AFTER `id`"

    def test_build_column_position_clause_first(self):
        clause = sd.build_column_position_clause(["name", "id"], {"id"}, "name")
        assert clause == " FIRST"

    def test_build_incremental_table_alter_sql_add_column(self):
        source = sd.parse_schema_summary(
            _summary(
                [
                    ["TABLE", "t1", "BASE TABLE", "InnoDB", ""],
                    ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "", "", ""],
                    ["COLUMN", "t1", 2, "name", "varchar(20)", "YES", "__SYNC_NULL__", "", "", ""],
                ]
            )
        )
        target = sd.parse_schema_summary(
            _summary(
                [
                    ["TABLE", "t1", "BASE TABLE", "InnoDB", ""],
                    ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "", "", ""],
                ]
            )
        )
        table_delta = {
            "add_columns": ["name"],
            "modify_columns": [],
            "add_indexes": [],
            "rebuild_indexes": [],
        }
        alter = sd.build_incremental_table_alter_sql(
            "db", "t1", table_delta, source, target, self.CREATE_SQL
        )
        assert alter is not None
        assert "ALTER TABLE `db`.`t1`" in alter
        assert "ADD COLUMN `name` varchar(20) DEFAULT NULL AFTER `id`" in alter

    def test_build_incremental_table_alter_sql_no_changes_returns_none(self):
        source = sd.parse_schema_summary(
            _summary(
                [
                    ["TABLE", "t1", "BASE TABLE", "InnoDB", ""],
                    ["COLUMN", "t1", 1, "id", "int", "NO", "__SYNC_NULL__", "", "", ""],
                ]
            )
        )
        table_delta = {
            "add_columns": [],
            "modify_columns": [],
            "add_indexes": [],
            "rebuild_indexes": [],
        }
        alter = sd.build_incremental_table_alter_sql(
            "db", "t1", table_delta, source, source, self.CREATE_SQL
        )
        assert alter is None


class TestViewAndScopedSql:
    def test_build_show_create_view_sql(self):
        assert sd.build_show_create_view_sql("db", "v1") == "SHOW CREATE VIEW `db`.`v1`"

    def test_normalize_create_view_sql_strips_definer(self):
        payload = "v1\tCREATE ALGORITHM=UNDEFINED DEFINER=`root`@`%` VIEW `v1` AS select 1"
        out = sd.normalize_create_view_sql(payload, "v1")
        assert "DEFINER" not in out
        assert out.startswith("CREATE OR REPLACE")

    def test_normalize_create_view_sql_missing_raises(self):
        with pytest.raises(RuntimeError):
            sd.normalize_create_view_sql("only-one-column", "v1")

    def test_build_database_scoped_sql(self):
        out = sd.build_database_scoped_sql("db", "ALTER TABLE x ADD y int;")
        assert out == "USE `db`; ALTER TABLE x ADD y int;"


class TestProgressMath:
    def test_build_table_step_progress_bounds(self):
        # first table, step 0 -> table_start = 45
        assert sd.build_table_step_progress(index=0, total=4, step=0, step_count=2) == 45
        # last step caps at 90
        assert sd.build_table_step_progress(index=3, total=4, step=2, step_count=2) <= 90

    def test_build_table_step_progress_midway(self):
        val = sd.build_table_step_progress(index=0, total=4, step=1, step_count=2)
        assert 45 <= val <= 90


class TestServiceFacadeDelegation:
    """The SyncService thin facades must return identical values to the module."""

    def test_facade_matches_module(self):
        from app.services.sync_service import get_sync_service

        svc = get_sync_service()
        assert svc._build_database_exists_sql("db") == sd.build_database_exists_sql("db")
        assert svc._quote_identifier("a`b") == sd.quote_identifier("a`b")
        assert svc._build_schema_delta({"tables": {}}, {"tables": {}}) == sd.build_schema_delta(
            {"tables": {}}, {"tables": {}}
        )
