"""Focused proof for the Iteration 197 scope-manifest gate."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.market_data.scope_manifest import (
    ITER196_BASELINE_SCHEMA_VERSION,
    ScopeManifestError,
    build_scope_manifest,
    canonical_sha256,
    inspect_frontend_market_input_surface,
    validate_scope_manifest,
)
from scripts.generate_iteration197_scope_manifest import main

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _frozen_baseline(**changes: object) -> dict[str, object]:
    """Return an explicit fake frozen input without implying a real 196 freeze."""
    baseline: dict[str, object] = {
        "schema_version": ITER196_BASELINE_SCHEMA_VERSION,
        "iteration": 196,
        "status": "frozen",
        "baseline_ref": "a" * 40,
        "baseline_sha256": "b" * 64,
        "artifact_ref": "approved/iter196/frozen-market-data-contract.json",
        "frozen_at": "2026-09-08T12:00:00Z",
    }
    baseline.update(changes)
    return baseline


def _copy_attested_sources(destination_root: Path) -> None:
    """Copy only files whose contents are deliberately hashed by the manifest."""
    for relative_path in (
        "src/backend/app/services/market_data/scope_manifest.py",
        "src/backend/app/services/market_data/dataset_contracts.py",
        "src/backend/app/schemas/market_data_platform.py",
        "src/backend/app/services/market_data/legacy_contract.py",
        "src/frontend/src/views/data/useDataPage.ts",
        "src/frontend/src/api/marketData.ts",
    ):
        source = PROJECT_ROOT / relative_path
        destination = destination_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_scope_manifest_is_deterministic_and_carries_all_twenty_one_family_rows() -> None:
    """Registry, current page inputs, and typed API inputs form one reproducible scope view."""
    baseline = _frozen_baseline()

    first = build_scope_manifest(project_root=PROJECT_ROOT, iter196_baseline=baseline)
    second = build_scope_manifest(project_root=PROJECT_ROOT, iter196_baseline=baseline)

    assert first == second
    assert first["scope_status"] == "provisional"
    assert first["strategy_page_production_status"] == "not_enabled_by_scope_manifest"
    assert first["iter196_baseline"] == baseline
    assert len(first["rows"]) == 21
    assert {row["family_id"] for row in first["rows"]} == {
        "stock.realtime",
        "stock.valuation",
        "stock.liquidity",
        "futures.realtime",
        "futures.settlement",
        "futures.inventory",
        "bond.realtime",
        "bond.orderbook",
        "bond.fixed_income",
        "fund.realtime",
        "fund.liquidity",
        "fund.nav",
        "option.realtime",
        "option.derivative",
        "option.risk_surface",
        "fx.realtime",
        "fx.macro_fx",
        "fx.range",
        "crypto.realtime",
        "crypto.cme_position",
        "crypto.range",
    }
    assert all(
        row["row_sha256"]
        == canonical_sha256({key: value for key, value in row.items() if key != "row_sha256"})
        for row in first["rows"]
    )

    rows = {row["family_id"]: row for row in first["rows"]}
    assert rows["stock.realtime"]["frontend"]["v2_query_periods"] == [
        "daily",
        "weekly",
        "monthly",
    ]
    assert rows["futures.realtime"]["frontend"]["v2_query_periods"] == ["daily"]
    assert rows["stock.liquidity"]["frontend"]["v2_query_periods"] == ["daily"]
    assert rows["fund.liquidity"]["frontend"]["v2_query_periods"] == ["daily"]
    assert rows["fx.range"]["frontend"]["v2_query_periods"] == ["daily"]
    assert rows["stock.realtime"]["frontend"]["v2_query_available"] is True
    assert rows["stock.realtime"]["frontend"]["v2_query_frequencies"] == ["1d", "1w", "1mo"]
    assert rows["crypto.realtime"]["frontend"]["v2_query_periods"] == []
    assert rows["crypto.realtime"]["frontend"]["v2_query_available"] is False
    assert rows["crypto.realtime"]["frontend"]["v2_query_frequencies"] == []
    assert rows["stock.valuation"]["frontend"]["v2_query_periods"] == []
    assert rows["stock.valuation"]["frontend"]["v2_query_available"] is False
    assert rows["option.derivative"]["frontend"]["v2_query_periods"] == []
    assert rows["option.derivative"]["frontend"]["v2_query_available"] is False
    assert rows["option.derivative"]["frontend"]["declared_compatibility_periods"] == []
    validate_scope_manifest(manifest=first, project_root=PROJECT_ROOT)


@pytest.mark.parametrize(
    ("baseline", "expected_code"),
    [
        (None, "ITER196_BASELINE_REQUIRED"),
        (_frozen_baseline(status="draft"), "ITER196_BASELINE_NOT_FROZEN"),
        (_frozen_baseline(baseline_ref="short-ref"), "ITER196_BASELINE_INVALID"),
    ],
)
def test_scope_manifest_refuses_missing_unfrozen_or_mutable_iter196_baselines(
    baseline: dict[str, object] | None,
    expected_code: str,
) -> None:
    """No current working-tree branch or default value can stand in for a freeze."""
    with pytest.raises(ScopeManifestError) as rejected:
        build_scope_manifest(project_root=PROJECT_ROOT, iter196_baseline=baseline)

    assert rejected.value.code == expected_code


def test_scope_manifest_validation_detects_tampered_row_before_global_hash_check() -> None:
    """Every family retains independent evidence, not merely one document checksum."""
    manifest = build_scope_manifest(project_root=PROJECT_ROOT, iter196_baseline=_frozen_baseline())
    tampered = deepcopy(manifest)
    tampered["rows"][0]["dataset_code"] = "market.tampered"

    with pytest.raises(ScopeManifestError) as rejected:
        validate_scope_manifest(manifest=tampered, project_root=PROJECT_ROOT)

    assert rejected.value.code == "SCOPE_MANIFEST_ROW_HASH_MISMATCH"


def test_scope_manifest_detects_frontend_family_drift_from_the_registry(tmp_path: Path) -> None:
    """A page family cannot silently disappear from a 21-family registry export."""
    copied_root = tmp_path / "copied-project"
    _copy_attested_sources(copied_root)
    frontend_path = copied_root / "src/frontend/src/views/data/useDataPage.ts"
    frontend_path.write_text(
        frontend_path.read_text(encoding="utf-8").replace(
            "familyId: 'crypto.range'", "familyId: 'crypto.unregistered'", 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(ScopeManifestError) as rejected:
        build_scope_manifest(project_root=copied_root, iter196_baseline=_frozen_baseline())

    assert rejected.value.code == "SCOPE_MANIFEST_FRONTEND_FAMILY_DRIFT"


def test_frontend_parser_fails_when_the_v2_family_selection_rule_is_no_longer_provable(
    tmp_path: Path,
) -> None:
    """A source hash alone is insufficient if the narrowly reviewed rule vanishes."""
    copied_root = tmp_path / "copied-project"
    _copy_attested_sources(copied_root)
    frontend_path = copied_root / "src/frontend/src/views/data/useDataPage.ts"
    frontend_path.write_text(
        frontend_path.read_text(encoding="utf-8").replace(
            "isMarketDataQueryBundleFamilyExecutable(family)",
            "isMarketDataQueryBundleFamilyExecutable(candidate)",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ScopeManifestError) as rejected:
        inspect_frontend_market_input_surface(copied_root)

    assert rejected.value.code == "SCOPE_MANIFEST_FRONTEND_V2_RULE_UNREADABLE"


def test_frontend_parser_fails_when_the_public_ready_kind_allowlist_drifts(
    tmp_path: Path,
) -> None:
    """A valuation/B2 promotion must update the scope generator explicitly."""
    copied_root = tmp_path / "copied-project"
    _copy_attested_sources(copied_root)
    api_path = copied_root / "src/frontend/src/api/marketData.ts"
    api_path.write_text(
        api_path.read_text(encoding="utf-8").replace(
            "family.data_kind === 'quote_snapshot'",
            "family.data_kind === 'valuation_snapshot'",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ScopeManifestError) as rejected:
        inspect_frontend_market_input_surface(copied_root)

    assert rejected.value.code == "SCOPE_MANIFEST_FRONTEND_V2_RULE_UNREADABLE"


def test_cli_does_not_write_a_manifest_when_a_frozen_baseline_is_absent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command's failure path must not leave a plausible-looking artifact behind."""
    output_path = tmp_path / "scope-manifest.json"

    result = main(["--project-root", str(PROJECT_ROOT), "--output", str(output_path)])

    assert result == 2
    assert not output_path.exists()
    assert json.loads(capsys.readouterr().out) == {
        "code": "ITER196_BASELINE_REQUIRED",
        "status": "error",
    }


def test_cli_generates_and_validates_a_manifest_only_with_a_frozen_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A frozen fixture proves the toolchain without claiming the live 196 branch is frozen."""
    baseline_path = tmp_path / "iter196-baseline.json"
    output_path = tmp_path / "scope-manifest.json"
    baseline_path.write_text(json.dumps(_frozen_baseline()), encoding="utf-8")

    generated = main(
        [
            "--project-root",
            str(PROJECT_ROOT),
            "--iter196-baseline",
            str(baseline_path),
            "--output",
            str(output_path),
        ]
    )

    assert generated == 0
    generated_payload = json.loads(capsys.readouterr().out)
    assert generated_payload["code"] == "SCOPE_MANIFEST_GENERATED"
    assert output_path.is_file()

    validated = main(["--project-root", str(PROJECT_ROOT), "--validate", str(output_path)])

    assert validated == 0
    assert json.loads(capsys.readouterr().out)["code"] == "SCOPE_MANIFEST_VALID"
