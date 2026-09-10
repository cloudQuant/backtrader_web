"""Migration contract for server-authorized, immutable research approval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.exc import DatabaseError

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PREVIOUS = "20260908_ai_research_holdout_executions"
_HEAD = "20260908_ai_research_approval_authority"
_INTEGRATED_HEAD = "20260910_market_data_shared_source_payloads"
_GRANT_TABLE = "ai_research_approval_grants"
_GRANT_AUDIT_TABLE = "ai_research_approval_grant_audits"
_PROFILE_TABLE = "ai_research_capability_profiles"
_REQUEST_TABLE = "ai_research_approval_requests"
_DECISION_TABLE = "ai_research_human_decisions"
_FENCE_TABLE = "ai_research_approval_denial_fences"
_REQUEST_INDEX_NAME = "ix_ai_research_approval_request_run_candidate_status"
_PRINCIPAL_CHECK = "ck_users_principal_kind"
_GRANT_COLUMNS = {
    "id",
    "actor_id",
    "run_id",
    "workspace_id",
    "permission",
    "subject_kind",
    "issuer_id",
    "issuer_kind",
    "grant_hash",
    "issued_at",
    "expires_at",
    "revoked_at",
    "revoked_by",
    "revocation_reason",
    "created_at",
}
_GRANT_AUDIT_COLUMNS = {
    "id",
    "grant_id",
    "event_type",
    "actor_id",
    "run_id",
    "workspace_id",
    "subject_id",
    "permission",
    "policy_version",
    "policy_material_hash",
    "idempotency_key",
    "command_material_hash",
    "reason_hash",
    "occurred_at",
}
_REQUEST_COLUMNS = {
    "run_id",
    "workspace_id",
    "evidence_package_id",
    "policy_material_hash",
    "approval_mode",
    "capability_profile_id",
    "capability_profile_version",
    "capability_evidence_hash",
    "request_material_hash",
}
_DECISION_COLUMNS = {
    "run_id",
    "workspace_id",
    "approval_request_id",
    "evidence_package_id",
    "policy_material_hash",
    "capability_profile_id",
    "capability_profile_version",
    "capability_evidence_hash",
    "grant_id",
    "grant_hash",
    "challenge_hash",
    "risk_acknowledgement_hash",
    "reason_hash",
    "gate_input_evidence_hash",
    "decision_material_hash",
}
_FENCE_COLUMNS = {
    "id",
    "candidate_id",
    "run_id",
    "evidence_package_id",
    "decision_id",
    "decision",
    "promotion_policy_version",
    "approval_policy_version",
    "approval_policy_material_hash",
    "gate_input_evidence_hash",
    "evidence_package_hash",
    "approval_binding_hash",
    "fence_scope_hash",
    "created_at",
}
_INDEXES = {
    _GRANT_TABLE: {"ix_ai_research_approval_grant_scope"},
    _GRANT_AUDIT_TABLE: {"ix_ai_research_approval_grant_audit_scope"},
    _REQUEST_TABLE: {"ix_ai_research_approval_request_run_candidate_status"},
    _DECISION_TABLE: {
        "ix_ai_research_human_decision_run_candidate_decided",
        "uq_ai_research_human_decision_approval_request",
    },
    _FENCE_TABLE: {"ix_ai_research_approval_denial_fence_run_candidate"},
}
_TRIGGERS = {
    "trg_ai_research_capability_profile_update_guard",
    "trg_ai_research_capability_profile_delete_guard",
    "trg_ai_research_approval_grant_update_guard",
    "trg_ai_research_approval_grant_delete_guard",
    "trg_ai_research_approval_grant_audit_update_guard",
    "trg_ai_research_approval_grant_audit_delete_guard",
    "trg_ai_research_approval_request_update_guard",
    "trg_ai_research_approval_request_delete_guard",
    "trg_ai_research_human_decision_update_guard",
    "trg_ai_research_human_decision_delete_guard",
    "trg_ai_research_approval_denial_fence_update_guard",
    "trg_ai_research_approval_denial_fence_delete_guard",
}


def _migration_module():
    return ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module


class _CatalogBind:
    """Small dialect-aware catalog double for migration reflection tests."""

    def __init__(
        self,
        dialect: str,
        *,
        trigger_rows: list[list[Any]] | None = None,
        function_rows: list[list[Any]] | None = None,
        server_version_info: tuple[int, ...] | None = None,
        statistics_columns: list[str] | None = None,
        statistics_rows: list[list[Any]] | None = None,
    ) -> None:
        self.dialect = SimpleNamespace(
            name=dialect,
            server_version_info=server_version_info,
        )
        self.trigger_rows = trigger_rows or []
        self.function_rows = function_rows or []
        self.statistics_columns = statistics_columns or []
        self.statistics_rows = statistics_rows or []
        self.queries: list[str] = []

    def execute(self, statement, _params=None):
        rendered = str(statement)
        self.queries.append(rendered)
        if "FROM pg_proc AS procedure" in rendered:
            return [tuple(row) for row in self.function_rows]
        if "FROM pg_trigger AS trigger" in rendered:
            return [tuple(row) for row in self.trigger_rows]
        if "FROM information_schema.COLUMNS" in rendered:
            return [(name,) for name in self.statistics_columns]
        if "FROM information_schema.STATISTICS" in rendered:
            return [tuple(row) for row in self.statistics_rows]
        return []


class _IndexInspector:
    """Inspector double that preserves SQLAlchemy's reflected index/UQ shapes."""

    def __init__(
        self,
        *,
        indexes: list[dict[str, Any]],
        unique_constraints: list[dict[str, Any]] | None = None,
    ) -> None:
        self.indexes = indexes
        self.unique_constraints = unique_constraints or []

    def get_indexes(self, _table_name: str) -> list[dict[str, Any]]:
        return self.indexes

    def get_unique_constraints(self, _table_name: str) -> list[dict[str, Any]]:
        return self.unique_constraints


def _postgresql_guard_rows(
    *,
    table_name: str = _GRANT_AUDIT_TABLE,
    trigger_name: str = "trg_ai_research_approval_grant_audit_delete_guard",
    function_name: str = "deny_ai_research_approval_grant_audit_delete",
    operation: str = "DELETE",
    error: str = "APPROVAL_GRANT_AUDIT_IMMUTABLE",
    references: int = 1,
    target_references: int = 1,
) -> tuple[list[Any], list[Any]]:
    event_bit = {"UPDATE": 19, "DELETE": 11}[operation]
    return_value = "OLD" if operation == "DELETE" else "NEW"
    body = f"BEGIN RAISE EXCEPTION '{error}'; RETURN {return_value}; END;"
    function_ddl = (
        f"CREATE OR REPLACE FUNCTION public.{function_name}() RETURNS trigger "
        f"LANGUAGE plpgsql AS $function$ {body} $function$"
    )
    trigger_row = [
        trigger_name,
        f"{event_bit} {function_name} {body}",
        "public",
        "public",
        42,
        42,
        "public",
        "O",
        None,
        "",
        f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON public.{table_name} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{function_name}()",
        function_ddl,
    ]
    function_row = [
        "public",
        "public",
        73,
        73,
        function_ddl,
        references,
        target_references,
    ]
    return trigger_row, function_row


def _config(database_url: str, *, output: StringIO | None = None) -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _run_online(database_url: str, revision: str) -> None:
    config = _config(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
    finally:
        engine.dispose()


def test_approval_authority_revision_has_an_integrated_successor() -> None:
    script = ScriptDirectory.from_config(_config("sqlite://"))
    migration = script.get_revision(_HEAD)

    assert migration is not None
    assert migration.down_revision == _PREVIOUS
    assert script.get_heads() == [_INTEGRATED_HEAD]


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///fixture.db",
        "postgresql://fixture:fixture@127.0.0.1/fixture",
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_approval_authority_offline_sql_is_reviewable(database_url: str) -> None:
    upgrade_output = StringIO()
    command.upgrade(
        _config(database_url, output=upgrade_output),
        f"{_PREVIOUS}:{_HEAD}",
        sql=True,
    )
    rendered_upgrade = upgrade_output.getvalue()

    assert f"CREATE TABLE {_GRANT_TABLE}" in rendered_upgrade
    assert f"CREATE TABLE {_GRANT_AUDIT_TABLE}" in rendered_upgrade
    assert f"CREATE TABLE {_FENCE_TABLE}" in rendered_upgrade
    for column in _GRANT_COLUMNS | _GRANT_AUDIT_COLUMNS | _REQUEST_COLUMNS | _DECISION_COLUMNS:
        assert column in rendered_upgrade
    for column in _FENCE_COLUMNS:
        assert column in rendered_upgrade
    for trigger in _TRIGGERS:
        assert trigger in rendered_upgrade
    assert "APPROVAL_AUTHORITY_PARTIAL_BINDING" in rendered_upgrade
    assert "APPROVAL_AUTHORITY_DATA_CONFLICT" in rendered_upgrade
    assert "APPROVAL_AUTHORITY_ORPHAN" in rendered_upgrade
    assert "APPROVAL_AUTHORITY_IMMUTABLE" in rendered_upgrade
    assert "APPROVAL_REQUEST_TRANSITION_INVALID" in rendered_upgrade
    assert "APPROVAL_GRANT_MUTATION_INVALID" in rendered_upgrade
    assert "principal_kind" in rendered_upgrade
    assert _PRINCIPAL_CHECK in rendered_upgrade
    assert "UNKNOWN" in rendered_upgrade
    if database_url.startswith(("mysql", "mariadb")):
        assert "DELIMITER $$" in rendered_upgrade

    downgrade_output = StringIO()
    command.downgrade(
        _config(database_url, output=downgrade_output),
        f"{_HEAD}:{_PREVIOUS}",
        sql=True,
    )
    rendered_downgrade = downgrade_output.getvalue()
    assert "MANUAL PRECHECK: APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED" in rendered_downgrade
    assert f"DROP TABLE {_GRANT_TABLE}" in rendered_downgrade
    assert f"DROP TABLE {_GRANT_AUDIT_TABLE}" in rendered_downgrade
    assert f"DROP TABLE {_FENCE_TABLE}" in rendered_downgrade
    assert "principal_kind" in rendered_downgrade
    assert _PRINCIPAL_CHECK in rendered_downgrade


def test_approval_authority_sqlite_schema_matches_models(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority.db'}"
    _run_online(database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        principal = {column["name"]: column for column in inspector.get_columns("users")}[
            "principal_kind"
        ]
        assert not principal["nullable"]
        assert "UNKNOWN" in str(principal.get("default"))
        principal_checks = {
            item["name"]: item["sqltext"] for item in inspector.get_check_constraints("users")
        }
        assert "HUMAN" in principal_checks[_PRINCIPAL_CHECK]
        assert "SERVICE" in principal_checks[_PRINCIPAL_CHECK]
        assert "UNKNOWN" in principal_checks[_PRINCIPAL_CHECK]
        assert {column["name"] for column in inspector.get_columns(_GRANT_TABLE)} == (
            _GRANT_COLUMNS
        )
        assert {
            column["name"] for column in inspector.get_columns(_GRANT_AUDIT_TABLE)
        } == _GRANT_AUDIT_COLUMNS
        assert {column["name"] for column in inspector.get_columns(_FENCE_TABLE)} == (
            _FENCE_COLUMNS
        )
        assert _REQUEST_COLUMNS <= {
            column["name"] for column in inspector.get_columns(_REQUEST_TABLE)
        }
        assert _DECISION_COLUMNS <= {
            column["name"] for column in inspector.get_columns(_DECISION_TABLE)
        }
        for table_name in (_REQUEST_TABLE, _DECISION_TABLE):
            candidate_foreign_keys = [
                item
                for item in inspector.get_foreign_keys(table_name)
                if tuple(item.get("constrained_columns") or ()) == ("candidate_id",)
            ]
            assert len(candidate_foreign_keys) == 1
            assert candidate_foreign_keys[0]["name"] == (
                "fk_ai_research_approval_request_candidate"
                if table_name == _REQUEST_TABLE
                else "fk_ai_research_human_decision_candidate"
            )
            assert candidate_foreign_keys[0]["referred_table"] == "ai_research_candidates"
            assert tuple(candidate_foreign_keys[0]["referred_columns"]) == ("id",)
            assert (
                str((candidate_foreign_keys[0].get("options") or {}).get("ondelete")).upper()
                == "RESTRICT"
            )
        expected_new_foreign_keys = {
            _REQUEST_TABLE: {
                "run_id": (
                    "fk_ai_research_approval_request_run",
                    "ai_research_runs",
                ),
                "evidence_package_id": (
                    "fk_ai_research_approval_request_evidence_package",
                    "ai_research_evidence_packages",
                ),
            },
            _DECISION_TABLE: {
                "run_id": ("fk_ai_research_human_decision_run", "ai_research_runs"),
                "approval_request_id": (
                    "fk_ai_research_human_decision_approval_request",
                    _REQUEST_TABLE,
                ),
                "evidence_package_id": (
                    "fk_ai_research_human_decision_evidence_package",
                    "ai_research_evidence_packages",
                ),
                "grant_id": (
                    "fk_ai_research_human_decision_grant",
                    _GRANT_TABLE,
                ),
            },
        }
        for table_name, expected in expected_new_foreign_keys.items():
            observed = {
                tuple(item.get("constrained_columns") or ())[0]: item
                for item in inspector.get_foreign_keys(table_name)
                if tuple(item.get("constrained_columns") or ())
                and tuple(item.get("constrained_columns") or ())[0] in expected
            }
            assert set(observed) == set(expected)
            for column_name, (constraint_name, target_table) in expected.items():
                assert observed[column_name]["name"] == constraint_name
                assert observed[column_name]["referred_table"] == target_table
                assert (
                    str((observed[column_name].get("options") or {}).get("ondelete")).upper()
                    == "RESTRICT"
                )
        for table_name, expected in _INDEXES.items():
            observed = {item["name"] for item in inspector.get_indexes(table_name)}
            assert expected <= observed
        grant_checks = {item["name"] for item in inspector.get_check_constraints(_GRANT_TABLE)}
        assert {
            "ck_ai_research_approval_grant_human_identity",
            "ck_ai_research_approval_grant_permission",
            "ck_ai_research_approval_grant_revocation_group",
            "ck_ai_research_approval_grant_expiry",
        } <= grant_checks
        with engine.connect() as connection:
            trigger_rows = connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND name LIKE 'trg_ai_research_%'"
                )
            )
            assert _TRIGGERS <= {str(row[0]) for row in trigger_rows}
    finally:
        engine.dispose()


def test_approval_check_matching_preserves_boolean_grouping() -> None:
    migration = _migration_module()

    expected = "(a = 1 AND b = 1) OR (c = 1 AND d = 1)"
    grouping_collision = "a = 1 AND (b = 1 OR c = 1) AND d = 1"
    literal_collision = "(a = 1 AND b = 1) OR (c = 1 AND label = 'D')"
    literal_expected = "(a = 1 AND b = 1) OR (c = 1 AND label = 'd')"

    assert migration._sql_matches(expected, expected)
    assert not migration._sql_matches(grouping_collision, expected)
    assert not migration._sql_matches(literal_collision, literal_expected)


def test_approval_check_matching_is_quote_aware() -> None:
    migration = _migration_module()

    assert migration._sql_matches(
        "\"approval_mode\" = 'single_actor'",
        "approval_mode = 'single_actor'",
    )
    assert migration._sql_matches(
        "label = 'single_''actor'",
        "label = 'single_''actor'",
    )
    assert not migration._sql_matches(
        "approval_mode = 'single_\"actor'",
        "approval_mode = 'single_actor'",
    )
    assert not migration._sql_matches(
        "label = 'single_''actor'",
        "label = 'single_actor'",
    )


def test_approval_check_matching_accepts_postgresql_in_any_reflection() -> None:
    migration = _migration_module()

    expected = "approval_mode IS NULL OR approval_mode IN ('single_actor', 'multi_actor')"
    reflected = (
        "(approval_mode IS NULL) OR ((approval_mode)::text = ANY "
        "((ARRAY['single_actor'::character varying, "
        "'multi_actor'::character varying])::text[]))"
    )

    assert migration._sql_matches(reflected, expected)
    assert not migration._sql_matches(reflected.replace("::text[]", "::citext[]"), expected)
    assert not migration._sql_matches(
        reflected.replace("(approval_mode)::text", "(approval_mode)::varchar(1)"),
        expected,
    )


@pytest.mark.parametrize("ondelete", [None, "", "NO ACTION", "CASCADE", "SET NULL"])
def test_approval_foreign_key_matching_requires_explicit_restrict(ondelete: str | None) -> None:
    migration = _migration_module()
    foreign_key = {
        "name": "fk_exact",
        "constrained_columns": ["run_id"],
        "referred_table": "ai_research_runs",
        "referred_columns": ["id"],
        "options": {} if ondelete is None else {"ondelete": ondelete},
    }

    assert not migration._foreign_key_matches(foreign_key, "ai_research_runs")


@pytest.mark.parametrize(
    "drift",
    ["columns", "unique", "partial", "include", "invisible", "mysql_type"],
)
def test_approval_index_matching_rejects_semantic_drift(drift: str) -> None:
    migration = _migration_module()
    dialect = "mysql" if drift in {"invisible", "mysql_type"} else "postgresql"
    index: dict[str, Any] = {
        "name": "ix_scope",
        "column_names": ["run_id", "candidate_id"],
        "unique": False,
        "dialect_options": {},
    }
    if drift == "columns":
        index["column_names"] = ["candidate_id", "run_id"]
    elif drift == "unique":
        index["unique"] = True
    elif drift == "partial":
        index["dialect_options"] = {"postgresql_where": "status = 'PENDING'"}
    elif drift == "include":
        index["include_columns"] = ["status"]
    elif drift == "invisible":
        index["dialect_options"] = {"mysql_visible": False}
    elif drift == "mysql_type":
        index["type"] = "HASH"

    assert not migration._index_matches(
        index,
        columns=("run_id", "candidate_id"),
        unique=False,
        dialect_name=dialect,
    )


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql", "mysql", "mariadb"])
def test_approval_exact_index_contract_accepts_each_supported_dialect(dialect: str) -> None:
    migration = _migration_module()
    index: dict[str, Any] = {
        "name": "ix_scope",
        "column_names": ["run_id", "candidate_id"],
        "unique": False,
        "dialect_options": {},
    }
    assert migration._index_matches(
        index,
        columns=("run_id", "candidate_id"),
        unique=False,
        dialect_name=dialect,
    )


@pytest.mark.parametrize(
    ("dialect", "version", "capability", "visibility", "ignored"),
    [
        ("mysql", (8, 0, 36), "IS_VISIBLE", "YES", None),
        ("mariadb", (10, 11, 8), "IGNORED", None, "NO"),
    ],
)
def test_mysql_family_index_uses_catalog_for_physical_contract(
    monkeypatch,
    dialect: str,
    version: tuple[int, ...],
    capability: str,
    visibility: str | None,
    ignored: str | None,
) -> None:
    migration = _migration_module()
    inspector = _IndexInspector(
        indexes=[
            {
                "name": "ix_scope",
                "column_names": ["run_id", "candidate_id"],
                "unique": False,
            }
        ]
    )
    bind = _CatalogBind(
        dialect,
        server_version_info=version,
        statistics_columns=[capability],
        statistics_rows=[
            ["ix_scope", 1, 1, "run_id", "BTREE", visibility, ignored],
            ["ix_scope", 1, 2, "candidate_id", "BTREE", visibility, ignored],
        ],
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration._assert_index_exact(
        bind,
        table_name="example_table",
        name="ix_scope",
        columns=("run_id", "candidate_id"),
        unique=False,
    )

    assert any("information_schema.STATISTICS" in query for query in bind.queries)


@pytest.mark.parametrize(
    ("drift", "rows", "capabilities"),
    [
        (
            "index type",
            [["ix_scope", 1, 1, "run_id", "HASH", "YES", None]],
            ["IS_VISIBLE"],
        ),
        (
            "column order",
            [["ix_scope", 1, 2, "run_id", "BTREE", "YES", None]],
            ["IS_VISIBLE"],
        ),
        (
            "uniqueness",
            [["ix_scope", 0, 1, "run_id", "BTREE", "YES", None]],
            ["IS_VISIBLE"],
        ),
        (
            "visibility",
            [["ix_scope", 1, 1, "run_id", "BTREE", "NO", None]],
            ["IS_VISIBLE"],
        ),
        (
            "missing capability",
            [["ix_scope", 1, 1, "run_id", "BTREE", None, None]],
            [],
        ),
    ],
)
def test_mysql_catalog_index_drift_fails_closed(
    monkeypatch,
    drift: str,
    rows: list[list[Any]],
    capabilities: list[str],
) -> None:
    migration = _migration_module()
    inspector = _IndexInspector(
        indexes=[{"name": "ix_scope", "column_names": ["run_id"], "unique": False}]
    )
    bind = _CatalogBind(
        "mysql",
        server_version_info=(8, 0, 36),
        statistics_columns=capabilities,
        statistics_rows=rows,
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        migration._assert_index_exact(
            bind,
            table_name="example_table",
            name="ix_scope",
            columns=("run_id",),
            unique=False,
        )


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql", "mysql", "mariadb"])
def test_cross_dialect_unique_constraint_pairing_accepts_real_reflection_shapes(
    monkeypatch,
    dialect: str,
) -> None:
    migration = _migration_module()
    name = "uq_example_scope"
    columns = ["run_id", "candidate_id"]
    indexes: list[dict[str, Any]] = []
    unique: dict[str, Any] = {"name": name, "column_names": columns}
    bind = _CatalogBind(dialect)
    if dialect == "postgresql":
        unique["comment"] = None
        indexes = [
            {
                "name": name,
                "column_names": columns,
                "unique": True,
                "duplicates_constraint": name,
                "include_columns": [],
                "dialect_options": {"postgresql_include": []},
            }
        ]
    elif dialect in {"mysql", "mariadb"}:
        unique["duplicates_index"] = name
        indexes = [
            {
                "name": name,
                "column_names": columns,
                "unique": True,
                "type": "UNIQUE",
            }
        ]
        bind = _CatalogBind(
            dialect,
            server_version_info=(8, 0, 36) if dialect == "mysql" else (10, 11, 8),
            statistics_columns=["IS_VISIBLE" if dialect == "mysql" else "IGNORED"],
            statistics_rows=[
                [
                    name,
                    0,
                    1,
                    "run_id",
                    "BTREE",
                    "YES" if dialect == "mysql" else None,
                    "NO" if dialect == "mariadb" else None,
                ],
                [
                    name,
                    0,
                    2,
                    "candidate_id",
                    "BTREE",
                    "YES" if dialect == "mysql" else None,
                    "NO" if dialect == "mariadb" else None,
                ],
            ],
        )
    inspector = _IndexInspector(indexes=indexes, unique_constraints=[unique])
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    migration._assert_unique_constraint_exact(
        bind,
        table_name="example_table",
        name=name,
        columns=tuple(columns),
    )


@pytest.mark.parametrize(
    ("dialect", "index_patch", "unique_patch"),
    [
        ("postgresql", {"duplicates_constraint": "uq_other"}, {}),
        ("postgresql", {"duplicates_constraint": None}, {}),
        ("mysql", {}, {"duplicates_index": "uq_other"}),
        ("mysql", {}, {"duplicates_index": None}),
    ],
)
def test_cross_dialect_unique_constraint_pairing_fails_closed_on_mismatch(
    monkeypatch,
    dialect: str,
    index_patch: dict[str, Any],
    unique_patch: dict[str, Any],
) -> None:
    migration = _migration_module()
    name = "uq_example_scope"
    index: dict[str, Any] = {
        "name": name,
        "column_names": ["run_id"],
        "unique": True,
    }
    unique: dict[str, Any] = {"name": name, "column_names": ["run_id"]}
    if dialect == "postgresql":
        index["duplicates_constraint"] = name
        unique["comment"] = None
    else:
        index["type"] = "UNIQUE"
        unique["duplicates_index"] = name
    index.update(index_patch)
    unique.update(unique_patch)
    inspector = _IndexInspector(indexes=[index], unique_constraints=[unique])
    bind = _CatalogBind(
        dialect,
        server_version_info=(8, 0, 36),
        statistics_columns=["IS_VISIBLE"],
        statistics_rows=[[name, 0, 1, "run_id", "BTREE", "YES", None]],
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        migration._assert_unique_constraint_exact(
            bind,
            table_name="example_table",
            name=name,
            columns=("run_id",),
        )


@pytest.mark.parametrize(
    ("dialect", "indexes", "uniques"),
    [
        (
            "postgresql",
            [
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "unique": True,
                    "duplicates_constraint": "uq_scope",
                }
            ],
            [],
        ),
        (
            "postgresql",
            [],
            [{"name": "uq_scope", "column_names": ["run_id"], "comment": None}],
        ),
        (
            "mysql",
            [
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "unique": True,
                    "type": "UNIQUE",
                }
            ],
            [],
        ),
        (
            "mysql",
            [],
            [
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "duplicates_index": "uq_scope",
                }
            ],
        ),
        (
            "postgresql",
            [
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "unique": True,
                    "duplicates_constraint": "uq_scope",
                },
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "unique": True,
                    "duplicates_constraint": "uq_scope",
                },
            ],
            [{"name": "uq_scope", "column_names": ["run_id"], "comment": None}],
        ),
        (
            "mysql",
            [
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "unique": True,
                    "type": "UNIQUE",
                }
            ],
            [
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "duplicates_index": "uq_scope",
                },
                {
                    "name": "uq_scope",
                    "column_names": ["run_id"],
                    "duplicates_index": "uq_scope",
                },
            ],
        ),
    ],
)
def test_cross_dialect_unique_constraint_pairing_rejects_missing_or_duplicate_halves(
    monkeypatch,
    dialect: str,
    indexes: list[dict[str, Any]],
    uniques: list[dict[str, Any]],
) -> None:
    migration = _migration_module()
    inspector = _IndexInspector(indexes=indexes, unique_constraints=uniques)
    bind = _CatalogBind(
        dialect,
        server_version_info=(8, 0, 36),
        statistics_columns=["IS_VISIBLE"],
        statistics_rows=[["uq_scope", 0, 1, "run_id", "BTREE", "YES", None]],
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        migration._assert_unique_constraint_exact(
            bind,
            table_name="example_table",
            name="uq_scope",
            columns=("run_id",),
        )


def test_mariadb_ignored_index_fails_closed(monkeypatch) -> None:
    migration = _migration_module()
    inspector = _IndexInspector(
        indexes=[{"name": "ix_scope", "column_names": ["run_id"], "unique": False}]
    )
    bind = _CatalogBind(
        "mariadb",
        server_version_info=(10, 11, 8),
        statistics_columns=["IGNORED"],
        statistics_rows=[["ix_scope", 1, 1, "run_id", "BTREE", None, "YES"]],
    )
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        migration._assert_index_exact(
            bind,
            table_name="example_table",
            name="ix_scope",
            columns=("run_id",),
            unique=False,
        )


def test_approval_same_name_partial_index_fails_closed_on_reentry(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-partial-index.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP INDEX {_REQUEST_INDEX_NAME}"))
            connection.execute(
                text(
                    f"CREATE INDEX {_REQUEST_INDEX_NAME} ON {_REQUEST_TABLE} "
                    "(run_id, candidate_id, status, requested_at) WHERE status = 'PENDING'"
                )
            )
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PREVIOUS},
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        _run_online(database_url, _HEAD)


def test_approval_capability_profile_index_drift_fails_closed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-profile-index.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP INDEX ix_ai_research_capability_profile_expiry"))
            connection.execute(
                text(
                    "CREATE INDEX ix_ai_research_capability_profile_expiry "
                    "ON ai_research_capability_profiles (profile_id, expires_at) "
                    "WHERE actor_mode = 'single_actor'"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        _run_online(database_url, _HEAD)


def test_approval_upgrade_performs_final_full_schema_reread(monkeypatch) -> None:
    migration = _migration_module()
    calls: list[str] = []
    bind = _CatalogBind("sqlite")
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration, "_upgrade_online", lambda _bind: calls.append("ddl"))
    monkeypatch.setattr(migration, "_create_guards", lambda _bind: calls.append("guards"))
    monkeypatch.setattr(
        migration,
        "_assert_upgrade_schema_exact",
        lambda _bind: calls.append("reread"),
    )

    migration.upgrade()

    assert calls == ["ddl", "guards", "reread"]


def test_approval_capability_profile_contract_covers_complete_hash_material() -> None:
    migration = _migration_module()

    assert migration._PROFILE_MATERIAL_COLUMNS == (
        "id",
        "profile_id",
        "version",
        "topology",
        "actor_mode",
        "db_engine",
        "service_identities",
        "queue_capabilities",
        "storage_boundaries",
        "network_capabilities",
        "sandbox_capabilities",
        "approval_capabilities",
        "evidence_hash",
        "verified_at",
        "expires_at",
        "created_at",
    )


def test_approval_history_preflight_covers_parent_and_material_bindings() -> None:
    migration = _migration_module()
    rendered = "\n".join((*migration._integrity_queries(), *migration._orphan_queries())).lower()

    for marker in (
        "audit.subject_id != grant.actor_id",
        "audit.run_id != grant.run_id",
        "audit.permission != grant.permission",
        "audit.actor_id != grant.issuer_id",
        "audit.actor_id != grant.revoked_by",
        "subject.principal_kind != 'human'",
        "issuer.principal_kind != 'human'",
        "decision_actor.principal_kind != 'human'",
        "request.capability_profile_id",
        "profile.profile_id",
        "profile.evidence_hash != request.capability_evidence_hash",
        "profile.evidence_hash != decision.capability_evidence_hash",
        "package.candidate_id != request.candidate_id",
        "decision.approval_request_id",
        "decision.grant_id",
        "grant.issued_at > decision.decided_at",
        "grant.expires_at <= decision.decided_at",
        "grant.revoked_at <= decision.decided_at",
        "fence.decision_id",
    ):
        assert marker in rendered


def test_approval_postgresql_guard_creation_never_replaces_existing_function(monkeypatch) -> None:
    migration = _migration_module()
    emitted: list[str] = []
    bind = _CatalogBind("postgresql")
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._create_deny_guard(
        bind,
        table_name=_GRANT_AUDIT_TABLE,
        trigger_name="trg_ai_research_approval_grant_audit_delete_guard",
        function_name="deny_ai_research_approval_grant_audit_delete",
        operation="DELETE",
        error="APPROVAL_GRANT_AUDIT_IMMUTABLE",
    )

    assert emitted[0].startswith("CREATE FUNCTION ")
    assert "OR REPLACE" not in emitted[0]


@pytest.mark.parametrize("drift", ["body", "schema", "oid", "external_reference"])
def test_approval_postgresql_guard_rejects_conflicting_orphan_function(
    monkeypatch,
    drift: str,
) -> None:
    migration = _migration_module()
    trigger_row, function_row = _postgresql_guard_rows(references=0, target_references=0)
    if drift == "body":
        function_row[4] = str(function_row[4]).replace("RETURN OLD", "RETURN NEW")
    elif drift == "schema":
        function_row[0] = "shadow"
    elif drift == "oid":
        function_row[2] = 74
    elif drift == "external_reference":
        function_row[5] = 1
    bind = _CatalogBind("postgresql", function_rows=[function_row])
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_GUARD_CONFLICT"):
        migration._create_deny_guard(
            bind,
            table_name=_GRANT_AUDIT_TABLE,
            trigger_name=str(trigger_row[0]),
            function_name="deny_ai_research_approval_grant_audit_delete",
            operation="DELETE",
            error="APPROVAL_GRANT_AUDIT_IMMUTABLE",
        )

    assert emitted == []


def test_approval_postgresql_guard_reflection_is_current_schema_oid_exact(monkeypatch) -> None:
    migration = _migration_module()
    trigger_row, function_row = _postgresql_guard_rows()
    bind = _CatalogBind(
        "postgresql",
        trigger_rows=[trigger_row],
        function_rows=[function_row],
    )
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    assert migration._guard_exists_exact(
        bind,
        _GRANT_AUDIT_TABLE,
        str(trigger_row[0]),
        str(trigger_row[1]),
        function_name="deny_ai_research_approval_grant_audit_delete",
    )
    assert "relation_namespace.nspname = current_schema()" in bind.queries[0]
    assert "to_regclass" in bind.queries[0]
    assert "to_regprocedure" in bind.queries[1]


@pytest.mark.parametrize(
    "drift",
    [
        "relation_schema",
        "relation_oid",
        "resolved_relation_oid",
        "function_schema",
        "disabled",
        "when_clause",
        "update_columns",
        "trigger_definition",
        "function_definition",
        "external_reference",
    ],
)
def test_approval_postgresql_guard_reentry_rejects_catalog_drift(
    monkeypatch,
    drift: str,
) -> None:
    migration = _migration_module()
    trigger_row, function_row = _postgresql_guard_rows()
    if drift == "relation_schema":
        trigger_row[2] = "shadow"
    elif drift == "relation_oid":
        trigger_row[4] = 84
    elif drift == "resolved_relation_oid":
        trigger_row[5] = 84
    elif drift == "function_schema":
        trigger_row[6] = "shadow"
    elif drift == "disabled":
        trigger_row[7] = "D"
    elif drift == "when_clause":
        trigger_row[8] = "{CONST :consttype 16 :constvalue false}"
    elif drift == "update_columns":
        trigger_row[9] = "2"
    elif drift == "trigger_definition":
        trigger_row[10] = str(trigger_row[10]).replace("BEFORE DELETE", "AFTER DELETE")
    elif drift == "function_definition":
        trigger_row[11] = str(trigger_row[11]).replace("RETURN OLD", "RETURN NEW")
    elif drift == "external_reference":
        function_row[5] = 2
    bind = _CatalogBind(
        "postgresql",
        trigger_rows=[trigger_row],
        function_rows=[function_row],
    )
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_GUARD_CONFLICT"):
        migration._guard_exists_exact(
            bind,
            _GRANT_AUDIT_TABLE,
            str(trigger_row[0]),
            str(trigger_row[1]),
            function_name="deny_ai_research_approval_grant_audit_delete",
        )


def test_approval_postgresql_guard_reuses_exact_unused_orphan_function(monkeypatch) -> None:
    migration = _migration_module()
    trigger_row, function_row = _postgresql_guard_rows(references=0, target_references=0)
    bind = _CatalogBind("postgresql", function_rows=[function_row])
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._create_deny_guard(
        bind,
        table_name=_GRANT_AUDIT_TABLE,
        trigger_name=str(trigger_row[0]),
        function_name="deny_ai_research_approval_grant_audit_delete",
        operation="DELETE",
        error="APPROVAL_GRANT_AUDIT_IMMUTABLE",
    )

    assert len(emitted) == 1
    assert emitted[0].startswith(f"CREATE TRIGGER {trigger_row[0]}")


def test_approval_postgresql_guard_drop_revalidates_pair_without_if_exists(monkeypatch) -> None:
    migration = _migration_module()
    trigger_row, function_row = _postgresql_guard_rows()
    bind = _CatalogBind(
        "postgresql",
        trigger_rows=[trigger_row],
        function_rows=[function_row],
    )
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._drop_guard(
        bind,
        table_name=_GRANT_AUDIT_TABLE,
        trigger_name=str(trigger_row[0]),
        function_name="deny_ai_research_approval_grant_audit_delete",
        expected=str(trigger_row[1]),
    )

    assert emitted == [
        f"DROP TRIGGER {trigger_row[0]} ON {_GRANT_AUDIT_TABLE}",
        "DROP FUNCTION deny_ai_research_approval_grant_audit_delete()",
    ]
    assert all("IF EXISTS" not in statement for statement in emitted)


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_approval_downgrade_write_fence_is_acquired_before_validation(
    monkeypatch,
    dialect: str,
) -> None:
    migration = _migration_module()
    bind = _CatalogBind(dialect)
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    migration._acquire_downgrade_write_fence(bind)

    rendered = "\n".join(bind.queries)
    if dialect == "postgresql":
        assert "LOCK TABLE" in rendered
        assert "ACCESS EXCLUSIVE" in rendered
    else:
        assert f"UPDATE {_REQUEST_TABLE} SET id = id WHERE 0" in rendered


@pytest.mark.parametrize("dialect", ["mysql", "mariadb"])
def test_approval_online_mysql_family_downgrade_fails_before_destructive_ddl(
    monkeypatch,
    dialect: str,
) -> None:
    migration = _migration_module()
    bind = _CatalogBind(dialect)
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    with pytest.raises(
        RuntimeError,
        match="APPROVAL_AUTHORITY_DOWNGRADE_REQUIRES_EXCLUSIVE_MAINTENANCE",
    ):
        migration.downgrade()

    assert emitted == []


def test_approval_denial_fence_rows_are_database_immutable(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-denial-fence-immutable.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(
                text(
                    f"INSERT INTO {_FENCE_TABLE} ("
                    "id, candidate_id, run_id, evidence_package_id, decision_id, decision, "
                    "promotion_policy_version, approval_policy_version, "
                    "approval_policy_material_hash, gate_input_evidence_hash, "
                    "evidence_package_hash, approval_binding_hash, fence_scope_hash, created_at"
                    ") VALUES ("
                    "'fence-1', 'candidate-1', 'run-1', 'package-1', 'decision-1', 'REJECTED', "
                    "'promotion-v1', 'approval-multi-v2', :hash, :hash, :hash, :hash, :hash, :now"
                    ")"
                ),
                {"hash": "a" * 64, "now": datetime.now(timezone.utc)},
            )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_DENIAL_FENCE_IMMUTABLE"):
                connection.execute(
                    text(f"UPDATE {_FENCE_TABLE} SET decision = 'REQUESTED_CHANGES'")
                )
            with pytest.raises(DatabaseError, match="APPROVAL_DENIAL_FENCE_IMMUTABLE"):
                connection.execute(text(f"DELETE FROM {_FENCE_TABLE}"))
    finally:
        engine.dispose()


def test_approval_grant_audit_rows_are_database_append_only(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-grant-audit-immutable.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _insert_grant(connection, grant_id="grant-audit-1", now=now)
            connection.execute(
                text(
                    f"INSERT INTO {_GRANT_AUDIT_TABLE} ("
                    "id, grant_id, event_type, actor_id, run_id, workspace_id, subject_id, "
                    "permission, policy_version, policy_material_hash, idempotency_key, "
                    "command_material_hash, reason_hash, occurred_at) VALUES ("
                    "'audit-1', 'grant-audit-1', 'ISSUED', 'owner-1', 'run-1', "
                    "'workspace-1', 'reviewer-1', 'research:approve', "
                    "'approval-grant-authority-v1', :hash, 'audit-key', :hash, NULL, :now)"
                ),
                {"hash": "a" * 64, "now": now},
            )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_GRANT_AUDIT_IMMUTABLE"):
                connection.execute(text(f"UPDATE {_GRANT_AUDIT_TABLE} SET event_type = 'REVOKED'"))
            with pytest.raises(DatabaseError, match="APPROVAL_GRANT_AUDIT_IMMUTABLE"):
                connection.execute(text(f"DELETE FROM {_GRANT_AUDIT_TABLE}"))
    finally:
        engine.dispose()


def test_capability_profile_rows_are_database_append_only(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-profile-immutable.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"INSERT INTO {_PROFILE_TABLE} ("
                    "id, profile_id, version, topology, actor_mode, db_engine, "
                    "service_identities, queue_capabilities, storage_boundaries, "
                    "network_capabilities, sandbox_capabilities, approval_capabilities, "
                    "evidence_hash, verified_at, expires_at, created_at) VALUES ("
                    "'profile-1', 'topology-1', 'v1', 'topology-1', 'multi_actor', NULL, "
                    "'{}', '{}', '{}', '{}', '{}', '{}', :hash, :now, :expires, :now)"
                ),
                {"hash": "a" * 64, "now": now, "expires": now + timedelta(hours=1)},
            )
        with engine.begin() as connection:
            with pytest.raises(
                DatabaseError,
                match="APPROVAL_CAPABILITY_PROFILE_IMMUTABLE",
            ):
                connection.execute(text(f"UPDATE {_PROFILE_TABLE} SET actor_mode = 'single_actor'"))
            with pytest.raises(
                DatabaseError,
                match="APPROVAL_CAPABILITY_PROFILE_IMMUTABLE",
            ):
                connection.execute(text(f"DELETE FROM {_PROFILE_TABLE}"))
    finally:
        engine.dispose()


def test_approval_authority_sqlite_exact_rerun_is_idempotent(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority-rerun.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PREVIOUS},
            )
    finally:
        engine.dispose()

    _run_online(database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
                _HEAD
            )
    finally:
        engine.dispose()


def test_approval_authority_partial_schema_conflict_fails_closed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority-partial.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {_REQUEST_TABLE} ADD COLUMN run_id INTEGER"))
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        _run_online(database_url, _HEAD)


@pytest.mark.parametrize(
    ("table_name", "source", "replacement"),
    [
        (_GRANT_TABLE, "actor_id VARCHAR(36) NOT NULL", "actor_id CHAR(36) NOT NULL"),
        (_GRANT_TABLE, "issuer_id VARCHAR(36) NOT NULL", "issuer_id NVARCHAR(36) NOT NULL"),
        (_GRANT_TABLE, "issued_at DATETIME NOT NULL", "issued_at VARCHAR(32) NOT NULL"),
        (_GRANT_TABLE, "expires_at DATETIME NOT NULL", "expires_at TIMESTAMP NOT NULL"),
        (_GRANT_TABLE, "revocation_reason TEXT", "revocation_reason VARCHAR(64)"),
        (
            _GRANT_TABLE,
            "created_at DATETIME NOT NULL",
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
        ),
        (
            _GRANT_AUDIT_TABLE,
            "occurred_at DATETIME NOT NULL",
            "occurred_at VARCHAR(32) NOT NULL",
        ),
        (_FENCE_TABLE, "created_at DATETIME NOT NULL", "created_at VARCHAR(32) NOT NULL"),
    ],
)
def test_approval_partial_table_reentry_rejects_full_column_contract_drift(
    tmp_path: Path,
    table_name: str,
    source: str,
    replacement: str,
) -> None:
    database_url = f"sqlite:///{tmp_path / ('approval-column-drift-' + table_name + '.db')}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            create_sql = connection.scalar(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
                {"table_name": table_name},
            )
            assert isinstance(create_sql, str) and source in create_sql
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(text(f"DROP TABLE {table_name}"))
            connection.execute(text(create_sql.replace(source, replacement, 1)))
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PREVIOUS},
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        _run_online(database_url, _HEAD)


@pytest.mark.parametrize(
    ("dialect", "observed_type"),
    [
        ("postgresql", postgresql.TIMESTAMP(timezone=False)),
        ("postgresql", postgresql.TIMESTAMP(timezone=True, precision=6)),
        ("mysql", mysql.TIMESTAMP()),
        ("mysql", mysql.DATETIME(fsp=6)),
        ("mariadb", mysql.DATETIME(fsp=6)),
    ],
    ids=[
        "postgresql-without-timezone",
        "postgresql-nondefault-precision",
        "mysql-timestamp",
        "mysql-fsp-6",
        "mariadb-fsp-6",
    ],
)
def test_approval_datetime_type_contract_rejects_dialect_specific_drift(
    dialect: str,
    observed_type: Any,
) -> None:
    migration = _migration_module()

    assert not migration._datetime_type_matches(
        {"type": observed_type},
        dialect_name=dialect,
    )


@pytest.mark.parametrize(
    ("dialect", "observed_type"),
    [
        ("sqlite", sa.CHAR(36)),
        ("sqlite", sa.NVARCHAR(36)),
        ("postgresql", postgresql.CHAR(36)),
        ("postgresql", sa.NVARCHAR(36)),
        ("mysql", mysql.CHAR(36)),
        ("mysql", mysql.NVARCHAR(36)),
        ("mariadb", mysql.CHAR(36)),
        ("mariadb", mysql.NVARCHAR(36)),
    ],
)
def test_approval_string_type_contract_rejects_non_varchar_families(
    dialect: str,
    observed_type: Any,
) -> None:
    migration = _migration_module()

    assert not migration._string_type_matches(
        {"type": observed_type},
        36,
        dialect_name=dialect,
    )


@pytest.mark.parametrize(
    ("dialect", "observed_type"),
    [
        ("sqlite", sa.VARCHAR(36)),
        ("postgresql", postgresql.VARCHAR(36)),
        ("mysql", mysql.VARCHAR(36)),
        ("mariadb", mysql.VARCHAR(36)),
    ],
)
def test_approval_string_type_contract_accepts_plain_varchar(
    dialect: str,
    observed_type: Any,
) -> None:
    migration = _migration_module()

    assert migration._string_type_matches(
        {"type": observed_type},
        36,
        dialect_name=dialect,
    )


@pytest.mark.parametrize(
    ("dialect", "observed_type"),
    [
        ("sqlite", sa.DATETIME()),
        ("postgresql", postgresql.TIMESTAMP(timezone=True)),
        ("mysql", mysql.DATETIME()),
        ("mariadb", mysql.DATETIME()),
    ],
)
def test_approval_datetime_type_contract_accepts_exact_dialect_type(
    dialect: str,
    observed_type: Any,
) -> None:
    migration = _migration_module()

    assert migration._datetime_type_matches(
        {"type": observed_type},
        dialect_name=dialect,
    )


@pytest.mark.parametrize(
    ("dialect", "observed_type"),
    [
        ("sqlite", sa.TEXT()),
        ("postgresql", postgresql.TEXT()),
        ("mysql", mysql.TEXT()),
        ("mariadb", mysql.TEXT()),
    ],
)
def test_approval_text_type_contract_accepts_exact_dialect_type(
    dialect: str,
    observed_type: Any,
) -> None:
    migration = _migration_module()

    assert migration._text_type_matches(
        {"type": observed_type},
        dialect_name=dialect,
    )


def test_approval_mysql_text_contract_rejects_longtext() -> None:
    migration = _migration_module()

    assert not migration._text_type_matches(
        {"type": mysql.LONGTEXT()},
        dialect_name="mysql",
    )


def test_existing_users_are_backfilled_unknown_not_human(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-principal-backfill.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            _insert_user(connection, user_id="legacy-user")
    finally:
        engine.dispose()

    _run_online(database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT principal_kind FROM users WHERE id = 'legacy-user'"))
                == "UNKNOWN"
            )
    finally:
        engine.dispose()


def test_principal_kind_nullable_partial_reentry_finishes_strictly(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-principal-partial.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN principal_kind VARCHAR(16) DEFAULT 'UNKNOWN'")
            )
            _insert_user(connection, user_id="partial-user")
            connection.execute(
                text("UPDATE users SET principal_kind = NULL WHERE id = 'partial-user'")
            )
    finally:
        engine.dispose()

    _run_online(database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        principal = {column["name"]: column for column in inspect(engine).get_columns("users")}[
            "principal_kind"
        ]
        assert not principal["nullable"]
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT principal_kind FROM users WHERE id = 'partial-user'")
                )
                == "UNKNOWN"
            )
    finally:
        engine.dispose()


def test_principal_kind_partial_reentry_rejects_unclassified_dirty_value(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-principal-dirty.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN principal_kind VARCHAR(16) DEFAULT 'UNKNOWN'")
            )
            _insert_user(connection, user_id="dirty-user", principal_kind="ROBOT")
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_PRINCIPAL_KIND_DATA_CONFLICT"):
        _run_online(database_url, _HEAD)


def test_principal_kind_partial_reentry_rejects_wrong_column_contract(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-principal-schema-drift.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN principal_kind INTEGER DEFAULT 0")
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
        _run_online(database_url, _HEAD)


@pytest.mark.parametrize(
    ("definition", "error"),
    [
        (
            "VARCHAR(16) DEFAULT 'HUMAN'",
            "APPROVAL_AUTHORITY_SCHEMA_CONFLICT",
        ),
        (
            "VARCHAR(16) DEFAULT 'UNKNOWN' CONSTRAINT ck_users_principal_kind "
            "CHECK (principal_kind != 'ROBOT')",
            "APPROVAL_AUTHORITY_SCHEMA_CONFLICT",
        ),
    ],
)
def test_principal_kind_partial_reentry_rejects_default_or_check_drift(
    tmp_path: Path,
    definition: str,
    error: str,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-principal-contract-drift.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN principal_kind {definition}"))
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match=error):
        _run_online(database_url, _HEAD)


def test_principal_kind_downgrade_rejects_unexpected_column_dependency(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-principal-dependency.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    config = _config(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE INDEX ix_users_principal_kind_drift ON users (principal_kind)")
            )
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
                command.downgrade(config, _PREVIOUS)

        inspector = inspect(engine)
        assert inspector.has_table(_GRANT_TABLE)
        assert "principal_kind" in {column["name"] for column in inspector.get_columns("users")}
    finally:
        engine.dispose()


def test_approval_authority_partial_data_fails_closed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority-partial-data.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(text(f"ALTER TABLE {_REQUEST_TABLE} ADD COLUMN run_id VARCHAR(36)"))
            _insert_legacy_request(connection, request_id="partial-request", run_id="run-1")
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_PARTIAL_BINDING"):
        _run_online(database_url, _HEAD)


@pytest.mark.parametrize("table_name", [_REQUEST_TABLE, _DECISION_TABLE])
def test_approval_authority_orphan_candidate_fails_closed(
    tmp_path: Path,
    table_name: str,
) -> None:
    database_url = f"sqlite:///{tmp_path / ('approval-orphan-' + table_name + '.db')}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            if table_name == _REQUEST_TABLE:
                _insert_legacy_request(connection, request_id="orphan-request")
            else:
                _insert_legacy_decision(connection, decision_id="orphan-decision")
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_ORPHAN"):
        _run_online(database_url, _HEAD)


@pytest.mark.parametrize(
    ("issued_delta", "expires_delta", "revoked_delta"),
    [
        (timedelta(minutes=1), timedelta(hours=2), None),
        (timedelta(hours=-2), timedelta(minutes=-1), None),
        (timedelta(hours=-2), timedelta(hours=2), timedelta(minutes=-1)),
    ],
    ids=["not-yet-issued", "expired", "revoked-before-decision"],
)
def test_approval_history_rejects_decision_outside_grant_authority_window(
    tmp_path: Path,
    issued_delta: timedelta,
    expires_delta: timedelta,
    revoked_delta: timedelta | None,
) -> None:
    database_url = f"sqlite:///{tmp_path / ('approval-grant-window-' + str(issued_delta) + '.db')}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    decided_at = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _insert_complete_approval_history(
                connection,
                decided_at=decided_at,
                issued_at=decided_at + issued_delta,
                expires_at=decided_at + expires_delta,
                revoked_at=(decided_at + revoked_delta if revoked_delta is not None else None),
            )
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PREVIOUS},
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_DATA_CONFLICT"):
        _run_online(database_url, _HEAD)


def test_human_decision_rows_are_database_immutable(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-decision-immutable.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _insert_legacy_decision(connection, decision_id="decision-1")
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_AUTHORITY_IMMUTABLE"):
                connection.execute(
                    text(
                        f"UPDATE {_DECISION_TABLE} SET comment = 'changed' WHERE id = 'decision-1'"
                    )
                )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_AUTHORITY_IMMUTABLE"):
                connection.execute(text(f"DELETE FROM {_DECISION_TABLE} WHERE id = 'decision-1'"))
    finally:
        engine.dispose()


def test_approval_request_only_allows_one_terminal_transition(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-request-transition.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _insert_legacy_request(connection, request_id="request-1")
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_REQUEST_TRANSITION_INVALID"):
                connection.execute(
                    text(
                        f"UPDATE {_REQUEST_TABLE} SET policy_version = 'changed' "
                        "WHERE id = 'request-1'"
                    )
                )
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"UPDATE {_REQUEST_TABLE} SET status = 'DECIDED', "
                    "decided_at = CURRENT_TIMESTAMP WHERE id = 'request-1'"
                )
            )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_REQUEST_TRANSITION_INVALID"):
                connection.execute(
                    text(f"UPDATE {_REQUEST_TABLE} SET status = 'REVOKED' WHERE id = 'request-1'")
                )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_AUTHORITY_IMMUTABLE"):
                connection.execute(text(f"DELETE FROM {_REQUEST_TABLE} WHERE id = 'request-1'"))
    finally:
        engine.dispose()


def test_grant_only_allows_one_complete_revocation(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-grant-revocation.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _insert_grant(connection, grant_id="grant-1", now=now)
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_GRANT_MUTATION_INVALID"):
                connection.execute(
                    text(f"UPDATE {_GRANT_TABLE} SET permission = 'admin' WHERE id = 'grant-1'")
                )
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"UPDATE {_GRANT_TABLE} SET revoked_at = :revoked_at, "
                    "revoked_by = 'owner-1', revocation_reason = 'rotation' "
                    "WHERE id = 'grant-1'"
                ),
                {"revoked_at": now},
            )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_GRANT_MUTATION_INVALID"):
                connection.execute(
                    text(
                        f"UPDATE {_GRANT_TABLE} SET revoked_at = NULL, revoked_by = NULL, "
                        "revocation_reason = NULL WHERE id = 'grant-1'"
                    )
                )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="APPROVAL_AUTHORITY_IMMUTABLE"):
                connection.execute(text(f"DELETE FROM {_GRANT_TABLE} WHERE id = 'grant-1'"))
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("table_name", "approval_mode", "single_actor"),
    [
        (_REQUEST_TABLE, "browser_defined", None),
        (_DECISION_TABLE, "browser_defined", False),
        (_DECISION_TABLE, "multi_actor", True),
        (_DECISION_TABLE, "single_actor", False),
    ],
)
def test_approval_mode_and_single_actor_are_database_invariants(
    tmp_path: Path,
    table_name: str,
    approval_mode: str,
    single_actor: bool | None,
) -> None:
    database_url = f"sqlite:///{tmp_path / ('approval-mode-' + approval_mode + '.db')}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            with pytest.raises(DatabaseError):
                if table_name == _REQUEST_TABLE:
                    _insert_v2_request(
                        connection,
                        request_id="invalid-mode-request",
                        approval_mode=approval_mode,
                    )
                else:
                    _insert_v2_decision(
                        connection,
                        decision_id="invalid-mode-decision",
                        approval_mode=approval_mode,
                        single_actor=bool(single_actor),
                    )
    finally:
        engine.dispose()


def test_downgrade_refuses_retained_approval_authority(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority-downgrade.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            _insert_grant(
                connection,
                grant_id="grant-downgrade",
                now=datetime.now(timezone.utc),
            )
    finally:
        engine.dispose()

    config = _config(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED"):
                command.downgrade(config, _PREVIOUS)
    finally:
        engine.dispose()


def test_downgrade_refuses_schema_drift_before_dropping_any_authority(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority-downgrade-drift.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP INDEX {_REQUEST_INDEX_NAME}"))
            connection.execute(
                text(
                    f"CREATE INDEX {_REQUEST_INDEX_NAME} ON {_REQUEST_TABLE} "
                    "(run_id, candidate_id, status, requested_at) WHERE status = 'PENDING'"
                )
            )

        config = _config(database_url)
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            with pytest.raises(RuntimeError, match="APPROVAL_AUTHORITY_SCHEMA_CONFLICT"):
                command.downgrade(config, _PREVIOUS)

        inspector = inspect(engine)
        assert inspector.has_table(_GRANT_TABLE)
        assert inspector.has_table(_GRANT_AUDIT_TABLE)
        assert inspector.has_table(_FENCE_TABLE)
        assert _REQUEST_COLUMNS <= {
            column["name"] for column in inspector.get_columns(_REQUEST_TABLE)
        }
    finally:
        engine.dispose()


def test_approval_authority_clean_downgrade_then_upgrade_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'approval-authority-round-trip.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    config = _config(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, _PREVIOUS)

        inspector = inspect(engine)
        assert not inspector.has_table(_GRANT_TABLE)
        assert not inspector.has_table(_GRANT_AUDIT_TABLE)
        assert not inspector.has_table(_FENCE_TABLE)
        assert not (
            _REQUEST_COLUMNS & {column["name"] for column in inspector.get_columns(_REQUEST_TABLE)}
        )
        assert not (
            _DECISION_COLUMNS
            & {column["name"] for column in inspector.get_columns(_DECISION_TABLE)}
        )
        assert "principal_kind" not in {column["name"] for column in inspector.get_columns("users")}
        assert _PRINCIPAL_CHECK not in {
            item["name"] for item in inspector.get_check_constraints("users")
        }
    finally:
        engine.dispose()

    _run_online(database_url, _HEAD)
    assert inspect(create_engine(database_url)).has_table(_GRANT_TABLE)


def _insert_user(
    connection,
    *,
    user_id: str,
    principal_kind: str | None = None,
) -> None:
    columns = "id, username, email, hashed_password, is_active"
    values = ":id, :username, :email, 'hash', 1"
    params = {
        "id": user_id,
        "username": f"user-{user_id}",
        "email": f"{user_id}@example.test",
    }
    if principal_kind is not None:
        columns += ", principal_kind"
        values += ", :principal_kind"
        params["principal_kind"] = principal_kind
    connection.execute(text(f"INSERT INTO users ({columns}) VALUES ({values})"), params)


def _insert_legacy_request(connection, *, request_id: str, run_id: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    columns = (
        "id, candidate_id, requested_by, policy_version, gate_input_evidence_hash, "
        "evidence_package_hash, idempotency_key, status, requested_at, eligible_at, "
        "expires_at, decided_at"
    )
    values = (
        ":id, 'candidate-1', 'owner-1', 'approval-v1', :gate_hash, :package_hash, "
        ":idempotency_key, 'PENDING', :requested_at, :eligible_at, :expires_at, NULL"
    )
    params = {
        "id": request_id,
        "gate_hash": "a" * 64,
        "package_hash": "b" * 64,
        "idempotency_key": f"key-{request_id}",
        "requested_at": now,
        "eligible_at": now,
        "expires_at": now + timedelta(hours=1),
    }
    if run_id is not None:
        columns += ", run_id"
        values += ", :run_id"
        params["run_id"] = run_id
    connection.execute(
        text(f"INSERT INTO {_REQUEST_TABLE} ({columns}) VALUES ({values})"),
        params,
    )


def _insert_legacy_decision(connection, *, decision_id: str) -> None:
    connection.execute(
        text(
            f"INSERT INTO {_DECISION_TABLE} "
            "(id, candidate_id, decision, actor_id, domain_permissions, policy_version, "
            "approval_mode, single_actor, risk_acknowledgement, comment, challenge_records, "
            "evidence_package_hash, idempotency_key, decided_at) VALUES "
            "(:id, 'candidate-1', 'REJECTED', 'owner-1', '[]', 'approval-v1', "
            "'single_actor', 1, 1, 'original', '[]', :package_hash, :idempotency_key, "
            "CURRENT_TIMESTAMP)"
        ),
        {
            "id": decision_id,
            "package_hash": "b" * 64,
            "idempotency_key": f"key-{decision_id}",
        },
    )


def _insert_grant(connection, *, grant_id: str, now: datetime) -> None:
    connection.execute(
        text(
            f"INSERT INTO {_GRANT_TABLE} "
            "(id, actor_id, run_id, workspace_id, permission, subject_kind, issuer_id, "
            "issuer_kind, grant_hash, issued_at, expires_at, created_at) VALUES "
            "(:id, 'reviewer-1', 'run-1', 'workspace-1', 'research:approve', 'HUMAN', "
            "'owner-1', 'HUMAN', :grant_hash, :issued_at, :expires_at, :created_at)"
        ),
        {
            "id": grant_id,
            "grant_hash": "c" * 64,
            "issued_at": now - timedelta(minutes=1),
            "expires_at": now + timedelta(hours=1),
            "created_at": now,
        },
    )


def _insert_v2_request(connection, *, request_id: str, approval_mode: str) -> None:
    now = datetime.now(timezone.utc)
    connection.execute(
        text(
            f"INSERT INTO {_REQUEST_TABLE} ("
            "id, candidate_id, requested_by, policy_version, gate_input_evidence_hash, "
            "evidence_package_hash, idempotency_key, status, requested_at, eligible_at, "
            "expires_at, decided_at, run_id, workspace_id, evidence_package_id, "
            "policy_material_hash, approval_mode, capability_profile_id, "
            "capability_profile_version, capability_evidence_hash, request_material_hash) "
            "VALUES (:id, 'candidate-1', 'owner-1', 'approval-v2', :hash, :hash, :key, "
            "'PENDING', :now, :now, :expires, NULL, 'run-1', 'workspace-1', 'package-1', "
            ":hash, :mode, 'profile-1', 'v1', :hash, :hash)"
        ),
        {
            "id": request_id,
            "hash": "a" * 64,
            "key": f"key-{request_id}",
            "mode": approval_mode,
            "now": now,
            "expires": now + timedelta(hours=1),
        },
    )


def _insert_v2_decision(
    connection,
    *,
    decision_id: str,
    approval_mode: str,
    single_actor: bool,
) -> None:
    now = datetime.now(timezone.utc)
    connection.execute(
        text(
            f"INSERT INTO {_DECISION_TABLE} ("
            "id, candidate_id, decision, actor_id, domain_permissions, policy_version, "
            "approval_mode, single_actor, risk_acknowledgement, comment, challenge_records, "
            "evidence_package_hash, idempotency_key, requested_at, eligible_at, decided_at, "
            "expires_at, run_id, workspace_id, approval_request_id, evidence_package_id, "
            "policy_material_hash, capability_profile_id, capability_profile_version, "
            "capability_evidence_hash, grant_id, grant_hash, challenge_hash, "
            "risk_acknowledgement_hash, reason_hash, gate_input_evidence_hash, "
            "decision_material_hash) VALUES ("
            ":id, 'candidate-1', 'APPROVED', 'reviewer-1', '[\"research:approve\"]', "
            "'approval-v2', :mode, :single_actor, 0, 'reviewed', '[]', :hash, :key, "
            ":now, :now, :now, :expires, 'run-1', 'workspace-1', 'request-1', "
            "'package-1', :hash, 'profile-1', 'v1', :hash, 'grant-1', :hash, :hash, "
            ":hash, :hash, :hash, :hash)"
        ),
        {
            "id": decision_id,
            "mode": approval_mode,
            "single_actor": single_actor,
            "hash": "a" * 64,
            "key": f"key-{decision_id}",
            "now": now,
            "expires": now + timedelta(hours=1),
        },
    )


def _insert_complete_approval_history(
    connection,
    *,
    decided_at: datetime,
    issued_at: datetime,
    expires_at: datetime,
    revoked_at: datetime | None,
) -> None:
    """Insert an otherwise-valid authority graph around one historical decision."""

    material_hash = "a" * 64
    requested_at = decided_at - timedelta(hours=2)
    request_expires_at = decided_at + timedelta(hours=2)
    for user_id in ("owner-1", "reviewer-1"):
        _insert_user(connection, user_id=user_id, principal_kind="HUMAN")
    connection.execute(
        text(
            "INSERT INTO ai_research_runs ("
            "id, user_id, workspace_id, hypothesis_version_id, protocol_version, status, "
            "stage_cursor, promotion_policy_version, request_hash, capability_profile_id, "
            "capability_profile_version, capability_evidence_hash, trace_id, created_at, "
            "workflow_version) VALUES ("
            "'run-1', 'owner-1', 'workspace-1', 'hypothesis-1', 'v2', 'RUNNING', "
            "'APPROVE', 'promotion-v1', :hash, 'profile-1', 'v1', :hash, 'trace-1', "
            ":created_at, 'generation-v1')"
        ),
        {"hash": material_hash, "created_at": requested_at},
    )
    connection.execute(
        text(
            "INSERT INTO ai_research_candidates ("
            "id, user_id, run_id, experiment_epoch_id, dataset_snapshot_id, code_artifact_id, "
            "dependency_artifact_id, candidate_hash, environment_hash, cost_model_hash, params, "
            "freeze_status, frozen_at, frozen_by, created_at) VALUES ("
            "'candidate-1', 'owner-1', 'run-1', 'epoch-1', 'dataset-1', 'code-1', "
            "'dependency-1', :hash, :hash, :hash, '{}', 'FROZEN', :created_at, "
            "'owner-1', :created_at)"
        ),
        {"hash": material_hash, "created_at": requested_at},
    )
    connection.execute(
        text(
            "INSERT INTO ai_research_evidence_packages ("
            "id, user_id, run_id, candidate_id, promotion_policy_version, "
            "gate_input_evidence_hash, manifest, manifest_hash, approval_binding_hash, status, "
            "created_at) VALUES ("
            "'package-1', 'owner-1', 'run-1', 'candidate-1', 'promotion-v1', :hash, '{}', "
            ":hash, :hash, 'ACTIVE', :created_at)"
        ),
        {"hash": material_hash, "created_at": requested_at},
    )
    connection.execute(
        text(
            f"INSERT INTO {_PROFILE_TABLE} ("
            "id, profile_id, version, topology, actor_mode, db_engine, service_identities, "
            "queue_capabilities, storage_boundaries, network_capabilities, "
            "sandbox_capabilities, approval_capabilities, evidence_hash, verified_at, "
            "expires_at, created_at) VALUES ("
            "'profile-row-1', 'profile-1', 'v1', 'topology-1', 'multi_actor', NULL, '{}', "
            "'{}', '{}', '{}', '{}', '{}', :hash, :verified_at, :expires_at, :verified_at)"
        ),
        {
            "hash": material_hash,
            "verified_at": requested_at,
            "expires_at": request_expires_at,
        },
    )
    grant_values = {
        "hash": material_hash,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "revoked_at": revoked_at,
        "revoked_by": "owner-1" if revoked_at is not None else None,
        "revocation_reason": "rotation" if revoked_at is not None else None,
        "created_at": issued_at,
    }
    connection.execute(
        text(
            f"INSERT INTO {_GRANT_TABLE} ("
            "id, actor_id, run_id, workspace_id, permission, subject_kind, issuer_id, "
            "issuer_kind, grant_hash, issued_at, expires_at, revoked_at, revoked_by, "
            "revocation_reason, created_at) VALUES ("
            "'grant-1', 'reviewer-1', 'run-1', 'workspace-1', 'research:approve', 'HUMAN', "
            "'owner-1', 'HUMAN', :hash, :issued_at, :expires_at, :revoked_at, :revoked_by, "
            ":revocation_reason, :created_at)"
        ),
        grant_values,
    )
    connection.execute(
        text(
            f"INSERT INTO {_GRANT_AUDIT_TABLE} ("
            "id, grant_id, event_type, actor_id, run_id, workspace_id, subject_id, "
            "permission, policy_version, policy_material_hash, idempotency_key, "
            "command_material_hash, reason_hash, occurred_at) VALUES ("
            "'audit-issued-1', 'grant-1', 'ISSUED', 'owner-1', 'run-1', 'workspace-1', "
            "'reviewer-1', 'research:approve', 'approval-grant-authority-v1', :hash, "
            "'audit-issued-key', :hash, NULL, :occurred_at)"
        ),
        {"hash": material_hash, "occurred_at": issued_at},
    )
    if revoked_at is not None:
        connection.execute(
            text(
                f"INSERT INTO {_GRANT_AUDIT_TABLE} ("
                "id, grant_id, event_type, actor_id, run_id, workspace_id, subject_id, "
                "permission, policy_version, policy_material_hash, idempotency_key, "
                "command_material_hash, reason_hash, occurred_at) VALUES ("
                "'audit-revoked-1', 'grant-1', 'REVOKED', 'owner-1', 'run-1', "
                "'workspace-1', 'reviewer-1', 'research:approve', "
                "'approval-grant-authority-v1', :hash, 'audit-revoked-key', :hash, :hash, "
                ":occurred_at)"
            ),
            {"hash": material_hash, "occurred_at": revoked_at},
        )
    connection.execute(
        text(
            f"INSERT INTO {_REQUEST_TABLE} ("
            "id, candidate_id, requested_by, policy_version, gate_input_evidence_hash, "
            "evidence_package_hash, idempotency_key, status, requested_at, eligible_at, "
            "expires_at, decided_at, run_id, workspace_id, evidence_package_id, "
            "policy_material_hash, approval_mode, capability_profile_id, "
            "capability_profile_version, capability_evidence_hash, request_material_hash) "
            "VALUES ('request-1', 'candidate-1', 'owner-1', 'approval-v2', :hash, :hash, "
            "'request-key', 'DECIDED', :requested_at, :requested_at, :expires_at, :decided_at, "
            "'run-1', 'workspace-1', 'package-1', :hash, 'multi_actor', 'profile-1', 'v1', "
            ":hash, :hash)"
        ),
        {
            "hash": material_hash,
            "requested_at": requested_at,
            "expires_at": request_expires_at,
            "decided_at": decided_at,
        },
    )
    connection.execute(
        text(
            f"INSERT INTO {_DECISION_TABLE} ("
            "id, candidate_id, decision, actor_id, domain_permissions, policy_version, "
            "approval_mode, single_actor, risk_acknowledgement, comment, challenge_records, "
            "evidence_package_hash, idempotency_key, requested_at, eligible_at, decided_at, "
            "expires_at, run_id, workspace_id, approval_request_id, evidence_package_id, "
            "policy_material_hash, capability_profile_id, capability_profile_version, "
            "capability_evidence_hash, grant_id, grant_hash, challenge_hash, "
            "risk_acknowledgement_hash, reason_hash, gate_input_evidence_hash, "
            "decision_material_hash) VALUES ("
            "'decision-1', 'candidate-1', 'APPROVED', 'reviewer-1', "
            "'[\"research:approve\"]', 'approval-v2', 'multi_actor', 0, 0, 'reviewed', '[]', "
            ":hash, 'decision-key', :requested_at, :requested_at, :decided_at, :expires_at, "
            "'run-1', 'workspace-1', 'request-1', 'package-1', :hash, 'profile-1', 'v1', "
            ":hash, 'grant-1', :hash, :hash, :hash, :hash, :hash, :hash)"
        ),
        {
            "hash": material_hash,
            "requested_at": requested_at,
            "decided_at": decided_at,
            "expires_at": request_expires_at,
        },
    )
