"""Prometheus contracts for multi-asset research observability."""

import pytest

from app.api.metrics import metrics_status
from app.middleware import metrics as metrics_module
from app.middleware.metrics import (
    get_metrics_output,
    is_metrics_available,
    record_asset_research_llm_cost_usd,
    record_asset_research_llm_fallback,
    record_asset_research_llm_tokens,
    record_asset_research_migration_reconciliation,
    record_asset_research_source,
    record_asset_research_task,
    set_asset_research_queue_depth,
)


@pytest.mark.skipif(not is_metrics_available(), reason="prometheus_client is optional")
def test_asset_research_metrics_expose_bounded_task_and_source_labels() -> None:
    """Asset metrics must be scrapeable without leaking an arbitrary identifier label."""
    record_asset_research_task(
        asset_type="futures",
        status="SUCCEEDED",
        duration_seconds=0.125,
    )
    record_asset_research_source(
        source_id="CFFEX_FIXTURE",
        result="AUTHORIZED",
        duration_seconds=0.05,
        registered=True,
    )
    record_asset_research_source(
        source_id="unregistered-source",
        result="BLOCKED",
        duration_seconds=0.01,
    )

    output = get_metrics_output()

    assert 'asset_research_task_total{asset_type="futures",status="SUCCEEDED"}' in output
    assert 'asset_research_task_duration_seconds_bucket{asset_type="futures"' in output
    assert 'asset_research_source_request_total{result="AUTHORIZED",source_id="CFFEX_FIXTURE"}' in output
    assert 'source_id="UNREGISTERED"' in output
    assert "unregistered-source" not in output


@pytest.mark.asyncio
@pytest.mark.skipif(not is_metrics_available(), reason="prometheus_client is optional")
async def test_metrics_status_advertises_asset_research_series() -> None:
    """The status endpoint must not hide registered asset-research series."""
    status = await metrics_status()

    assert "asset_research_task_total" in status["metrics"]
    assert "asset_research_source_request_total" in status["metrics"]
    assert "asset_research_outcome_total" in status["metrics"]
    assert "asset_research_queue_depth" in status["metrics"]
    assert "asset_research_llm_tokens_total" in status["metrics"]
    assert "asset_research_migration_reconciliation_total" in status["metrics"]
    assert "asset_research_export_total" in status["metrics"]
    assert "asset_research_publication_total" in status["metrics"]


@pytest.mark.skipif(not is_metrics_available(), reason="prometheus_client is optional")
def test_asset_research_artifact_metrics_use_only_bounded_format_and_target_labels() -> None:
    """Exports and publications must be observable without IDs, paths or user labels."""
    metrics_module.record_asset_research_export(export_format="MARKDOWN", status="SUCCEEDED")
    metrics_module.record_asset_research_export(export_format="../../private", status="FAILED")
    metrics_module.record_asset_research_publication(
        target_type="KNOWLEDGE_BASE",
        status="SUCCEEDED",
    )
    metrics_module.record_asset_research_publication(
        target_type="tenant-private-target",
        status="FAILED",
    )

    output = get_metrics_output()

    assert 'asset_research_export_total{format="MARKDOWN",status="SUCCEEDED"}' in output
    assert 'asset_research_export_total{format="UNKNOWN",status="FAILED"}' in output
    assert 'asset_research_publication_total{status="SUCCEEDED",target="KNOWLEDGE_BASE"}' in output
    assert 'asset_research_publication_total{status="FAILED",target="UNKNOWN"}' in output
    assert "tenant-private-target" not in output


@pytest.mark.skipif(not is_metrics_available(), reason="prometheus_client is optional")
def test_asset_research_llm_and_migration_metrics_use_bounded_labels() -> None:
    """LLM and reconciliation metrics must not accept arbitrary stage/tier/version labels."""
    record_asset_research_llm_tokens(
        asset_type="bond",
        stage="REPORT",
        model_tier="DEFAULT",
        tokens=1200,
    )
    record_asset_research_llm_tokens(
        asset_type="bond",
        stage="../../private",
        model_tier="tenant-model",
        tokens=1,
    )
    record_asset_research_llm_cost_usd(
        asset_type="futures",
        stage="REPORT",
        model_tier="ECONOMY",
        cost_usd=0.02,
    )
    record_asset_research_llm_fallback(
        asset_type="option",
        fallback_stage="REPORT",
        reason="BUDGET",
    )
    record_asset_research_migration_reconciliation(
        mapping_version="stock-legacy-map-v1",
        classification="DEFECT",
    )
    record_asset_research_migration_reconciliation(
        mapping_version="../../private",
        classification="UNKNOWN_CLASS",
    )
    set_asset_research_queue_depth(asset_type="crypto", count=7)

    output = get_metrics_output()

    assert 'asset_research_llm_tokens_total{asset_type="bond",model_tier="DEFAULT",stage="REPORT"}' in output
    assert 'asset_research_llm_cost_usd_total{asset_type="futures",model_tier="ECONOMY",stage="REPORT"}' in output
    assert 'asset_research_llm_fallback_total{asset_type="option",fallback_stage="REPORT",reason="BUDGET"}' in output
    assert 'asset_research_migration_reconciliation_total{classification="DEFECT",mapping_version="stock-legacy-map-v1"}' in output
    assert 'asset_research_queue_depth{asset_type="crypto"} 7.0' in output
    assert "tenant-model" not in output
    assert "UNKNOWN_CLASS" not in output
