from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import backtest_enhanced
from app.main import app
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestResponse,
    BacktestResult,
    TaskStatus,
)

pytest.importorskip("pytest_benchmark")

SAMPLE_CODE = "import backtrader as bt\nclass BaselineStrategy(bt.Strategy): pass"
TEST_PASSWORD = "Test12345678"


class FakeBacktestService:
    def __init__(self) -> None:
        self.result = BacktestResult(
            task_id="perf-task-001",
            strategy_id="001_ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
            status=TaskStatus.COMPLETED,
            total_return=1.25,
            annual_return=15.0,
            sharpe_ratio=1.1,
            max_drawdown=-2.0,
            win_rate=55.0,
            total_trades=8,
            profitable_trades=5,
            losing_trades=3,
            equity_curve=[100000.0, 101250.0],
            equity_dates=["2024-01-01", "2024-01-31"],
            drawdown_curve=[0.0, -1.0],
            trades=[],
            created_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        )

    async def run_backtest(self, user_id: str, request: Any) -> BacktestResponse:
        return BacktestResponse(
            task_id="perf-task-001",
            status=TaskStatus.PENDING,
            message=f"queued for {user_id}:{request.strategy_id}",
        )

    async def get_result(self, task_id: str, user_id: str | None = None) -> BacktestResult | None:
        if task_id != self.result.task_id or not user_id:
            return None
        return self.result

    async def list_results(
        self,
        user_id: str,
        limit: int,
        offset: int,
        sort_by: str,
        sort_desc: bool,
    ) -> BacktestListResponse:
        del user_id, limit, offset, sort_by, sort_desc
        return BacktestListResponse(total=1, items=[self.result])


@dataclass(frozen=True)
class ApiPerformanceContext:
    headers: dict[str, str]
    username: str
    password: str
    knowledge_base_id: str
    document_id: str


@pytest.fixture
def api_client() -> TestClient:
    fake_service = FakeBacktestService()
    app.dependency_overrides[backtest_enhanced.get_backtest_service] = lambda: fake_service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(backtest_enhanced.get_backtest_service, None)


@pytest.fixture
def api_baseline_context(api_client: TestClient) -> ApiPerformanceContext:
    username = "perf_baseline_user"
    register_response = api_client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": TEST_PASSWORD,
        },
    )
    assert register_response.status_code == 200, register_response.text

    login_response = api_client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200, login_response.text
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    strategy_response = api_client.post(
        "/api/v1/strategy/",
        headers=headers,
        json={
            "name": "Performance Baseline Strategy",
            "description": "Performance baseline fixture strategy",
            "code": SAMPLE_CODE,
            "params": {},
            "category": "custom",
        },
    )
    assert strategy_response.status_code == 200, strategy_response.text

    kb_response = api_client.post(
        "/api/v1/knowledge-base/",
        headers=headers,
        json={"name": "性能基线知识库", "description": "用于 API 性能基线", "is_public": False},
    )
    assert kb_response.status_code == 201, kb_response.text
    knowledge_base_id = kb_response.json()["id"]

    document_response = api_client.post(
        f"/api/v1/knowledge-base/{knowledge_base_id}/documents/",
        headers=headers,
        json={
            "title": "双均线策略",
            "content": "双均线策略在短期均线上穿长期均线时开仓，在下穿时平仓。",
            "content_type": "markdown",
            "is_folder": False,
        },
    )
    assert document_response.status_code == 201, document_response.text
    document_id = document_response.json()["id"]

    index_response = api_client.post(
        "/api/v1/rag/index",
        headers=headers,
        json={
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "force_reindex": False,
        },
    )
    assert index_response.status_code == 200, index_response.text

    return ApiPerformanceContext(
        headers=headers,
        username=username,
        password=TEST_PASSWORD,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )


def _bench(benchmark: Any, func: Any) -> Any:
    return benchmark.pedantic(func, rounds=3, iterations=1)


@pytest.mark.performance
def test_login_api_baseline(
    benchmark: Any,
    api_client: TestClient,
    api_baseline_context: ApiPerformanceContext,
) -> None:
    response = _bench(
        benchmark,
        lambda: api_client.post(
            "/api/v1/auth/login",
            json={
                "username": api_baseline_context.username,
                "password": api_baseline_context.password,
            },
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


@pytest.mark.performance
def test_strategy_list_api_baseline(
    benchmark: Any,
    api_client: TestClient,
    api_baseline_context: ApiPerformanceContext,
) -> None:
    response = _bench(
        benchmark,
        lambda: api_client.get("/api/v1/strategy/", headers=api_baseline_context.headers),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"]


@pytest.mark.performance
def test_backtest_submit_api_baseline(
    benchmark: Any,
    api_client: TestClient,
    api_baseline_context: ApiPerformanceContext,
) -> None:
    response = _bench(
        benchmark,
        lambda: api_client.post(
            "/api/v1/backtests/run",
            headers=api_baseline_context.headers,
            json={
                "strategy_id": "001_ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T00:00:00Z",
                "initial_cash": 100000.0,
                "commission": 0.001,
                "timeframe": "1d",
                "timeframe_n": 1,
                "params": {},
            },
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["task_id"] == "perf-task-001"


@pytest.mark.performance
def test_backtest_result_api_baseline(
    benchmark: Any,
    api_client: TestClient,
    api_baseline_context: ApiPerformanceContext,
) -> None:
    response = _bench(
        benchmark,
        lambda: api_client.get(
            "/api/v1/backtests/perf-task-001",
            headers=api_baseline_context.headers,
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["task_id"] == "perf-task-001"


@pytest.mark.performance
def test_knowledge_base_search_api_baseline(
    benchmark: Any,
    api_client: TestClient,
    api_baseline_context: ApiPerformanceContext,
) -> None:
    response = _bench(
        benchmark,
        lambda: api_client.post(
            "/api/v1/rag/search",
            headers=api_baseline_context.headers,
            json={
                "knowledge_base_id": api_baseline_context.knowledge_base_id,
                "query": "开仓条件",
                "top_k": 5,
                "min_similarity": 0.0,
                "search_mode": "keyword",
            },
        ),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["results"][0]["document_id"] == api_baseline_context.document_id


@pytest.mark.performance
def test_kb_chat_roundtrip_api_baseline(
    benchmark: Any,
    api_client: TestClient,
    api_baseline_context: ApiPerformanceContext,
) -> None:
    response = _bench(
        benchmark,
        lambda: api_client.post(
            "/api/v1/kb-chat/send",
            headers=api_baseline_context.headers,
            json={
                "knowledge_base_id": api_baseline_context.knowledge_base_id,
                "question": "双均线策略的开仓条件是什么？",
            },
        ),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["context_chunks_used"] >= 1
