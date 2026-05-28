from collections.abc import Awaitable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import backtest_enhanced
from app.main import app
from app.schemas.backtest import BacktestResponse, TaskStatus
from app.services.backtest.manager import BacktestExecutionManager
from app.services.backtest_service import BacktestService

pytest.importorskip("pytest_benchmark")

TEST_PASSWORD = "Test12345678"
STRATEGY_IDS = [
    "000_premium_rate",
    "001_multi_extend_data",
    "002_dual_ma",
    "003_rsi_reversion",
    "004_boll_breakout",
]


class NoopBacktestExecutionRunner:
    def schedule(self, task_id: str, execution: Awaitable[None]) -> None:
        del task_id
        close = getattr(execution, "close", None)
        if callable(close):
            close()

    def cancel_local_execution(self, task_id: str) -> bool:
        del task_id
        return False


class ThroughputBacktestService(BacktestService):
    async def run_backtest(self, user_id: str, request: Any) -> BacktestResponse:
        response = await super().run_backtest(user_id, request)
        await self.task_manager.update_task_status(response.task_id, TaskStatus.COMPLETED)
        return response


@pytest.fixture
def throughput_client() -> TestClient:
    manager = BacktestExecutionManager()
    manager.MAX_GLOBAL_TASKS = 1000
    manager.MAX_USER_TASKS = 1000
    service = ThroughputBacktestService(
        task_manager=manager,
        task_runner=NoopBacktestExecutionRunner(),
    )
    app.dependency_overrides[backtest_enhanced.get_backtest_service] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(backtest_enhanced.get_backtest_service, None)


@pytest.fixture
def throughput_headers(throughput_client: TestClient) -> dict[str, str]:
    username = "throughput_baseline_user"
    register_response = throughput_client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": TEST_PASSWORD,
        },
    )
    assert register_response.status_code == 200, register_response.text

    login_response = throughput_client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200, login_response.text
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def _backtest_payload(strategy_id: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "symbol": "000300.SH",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-12-31T00:00:00Z",
        "initial_cash": 1000000.0,
        "commission": 0.0003,
        "timeframe": "1d",
        "timeframe_n": 1,
        "params": {},
    }


def _submit_batch(client: TestClient, headers: dict[str, str]) -> list[str]:
    task_ids: list[str] = []
    for strategy_id in STRATEGY_IDS:
        response = client.post(
            "/api/v1/backtests/run",
            headers=headers,
            json=_backtest_payload(strategy_id),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "pending"
        task_ids.append(body["task_id"])
    return task_ids


def _poll_status_batch(client: TestClient, headers: dict[str, str], task_ids: list[str]) -> list[str]:
    statuses: list[str] = []
    for task_id in task_ids:
        response = client.get(f"/api/v1/backtests/{task_id}/status", headers=headers)
        assert response.status_code == 200, response.text
        statuses.append(response.json()["status"])
    return statuses


def _bench(benchmark: Any, func: Any) -> Any:
    return benchmark.pedantic(func, rounds=5, iterations=1)


@pytest.mark.performance
def test_backtest_five_strategy_submission_throughput(
    benchmark: Any,
    throughput_client: TestClient,
    throughput_headers: dict[str, str],
) -> None:
    task_ids = _bench(
        benchmark,
        lambda: _submit_batch(throughput_client, throughput_headers),
    )

    assert len(task_ids) == len(STRATEGY_IDS)


@pytest.mark.performance
def test_backtest_five_task_status_polling_throughput(
    benchmark: Any,
    throughput_client: TestClient,
    throughput_headers: dict[str, str],
) -> None:
    task_ids = _submit_batch(throughput_client, throughput_headers)

    statuses = _bench(
        benchmark,
        lambda: _poll_status_batch(throughput_client, throughput_headers, task_ids),
    )

    assert statuses == ["completed"] * len(STRATEGY_IDS)


@pytest.mark.performance
def test_backtest_submit_and_poll_roundtrip_throughput(
    benchmark: Any,
    throughput_client: TestClient,
    throughput_headers: dict[str, str],
) -> None:
    def submit_and_poll() -> list[str]:
        task_ids = _submit_batch(throughput_client, throughput_headers)
        return _poll_status_batch(throughput_client, throughput_headers, task_ids)

    statuses = _bench(benchmark, submit_and_poll)

    assert statuses == ["completed"] * len(STRATEGY_IDS)
