#!/usr/bin/env python3
"""Verify the native stock-analysis AI assistant acceptance flow."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient, Response

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
COMPAT_REPORT_KEY = "trading" + "agents_compat"

COMPAT_KEYS = [
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "bull_researcher",
    "bear_researcher",
    "research_team_decision",
    "investment_plan",
    "trader_investment_plan",
    "risky_analyst",
    "safe_analyst",
    "neutral_analyst",
    "risk_management_decision",
    "final_trade_decision",
]

EXPORT_CONTENT_TYPES = {
    "markdown": "text/markdown",
    "html": "text/html",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}

FORBIDDEN_SOURCE_TERMS = [
    "TradingAgentsGraph",
    "SingleAnalysis",
    "/analysis/single",
    "MongoClient",
    "RedisProgressTracker",
    "pypandoc",
    "pdfkit",
    "wkhtmltopdf",
]

SOURCE_SCAN_ROOTS = [
    REPO_ROOT / "src" / "backend" / "app" / "services" / "stock_analysis",
    REPO_ROOT / "src" / "backend" / "app" / "api" / "stock_analysis.py",
    REPO_ROOT / "src" / "backend" / "app" / "services" / "kb_chat_service.py",
    REPO_ROOT / "src" / "frontend" / "src" / "components" / "aichat",
    REPO_ROOT / "src" / "frontend" / "src" / "views" / "AIChatPage.vue",
    REPO_ROOT / "src" / "frontend" / "src" / "api" / "stockAnalysis.ts",
]


class AcceptanceFailure(RuntimeError):
    """Raised when an acceptance gate cannot continue."""


def emit(message: str = "") -> None:
    sys.stdout.write(f"{message}\n")


class Recorder:
    """Print and collect acceptance checks."""

    def __init__(self) -> None:
        self.failed: list[str] = []

    def check(self, name: str, passed: bool, evidence: str) -> None:
        status = "PASS" if passed else "FAIL"
        emit(f"{status} {name}: {evidence}")
        if not passed:
            self.failed.append(name)

    def require(self, name: str, passed: bool, evidence: str) -> None:
        self.check(name, passed, evidence)
        if not passed:
            raise AcceptanceFailure(f"{name}: {evidence}")


def configure_backend_env(db_path: Path) -> None:
    """Configure an isolated backend process before importing app modules."""

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    os.environ.setdefault("DATABASE_TYPE", "sqlite")
    os.environ.setdefault("SQL_ECHO", "false")
    os.environ.setdefault("ADMIN_PASSWORD", "TestAdmin@12345")
    os.environ.setdefault("AI_CHAT_ENABLED", "false")
    os.environ.setdefault("DB_AUTO_CREATE_SCHEMA", "false")
    os.environ.setdefault("DB_AUTO_CREATE_DEFAULT_ADMIN", "false")
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))


def load_backend_app() -> tuple[Any, Any]:
    """Import the FastAPI app and database module after env setup."""

    importlib.import_module("app.models")
    db_module = importlib.import_module("app.db.database")
    app = importlib.import_module("app.main").app

    limiter = importlib.import_module("app.rate_limit").limiter
    limiter.reset()
    response_cache = importlib.import_module("app.utils.response_cache")
    response_cache._cache_backend = response_cache.MemoryCacheBackend()
    return app, db_module


async def create_schema(db_module: Any) -> None:
    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)


async def register_and_login(
    client: AsyncClient,
    *,
    username: str,
    password: str = "Test12345678",
) -> tuple[dict[str, Any], dict[str, str]]:
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": password,
        },
    )
    require_response("register user", registration, 200)
    user = registration.json()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    require_response("login user", login, 200)
    return user, {"Authorization": f"Bearer {login.json()['access_token']}"}


def require_response(name: str, response: Response, expected_status: int) -> None:
    if response.status_code != expected_status:
        raise AcceptanceFailure(
            f"{name}: expected {expected_status}, got {response.status_code}: {response.text}"
        )


async def wait_for_completed_task(
    client: AsyncClient,
    headers: dict[str, str],
    task_id: str,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = await client.get(f"/api/v1/stock-analysis/tasks/{task_id}", headers=headers)
        require_response("poll stock-analysis task", response, 200)
        last_payload = response.json()
        if last_payload["status"] == "completed":
            return last_payload
        if last_payload["status"] not in {"pending", "running"}:
            raise AcceptanceFailure(f"task {task_id} ended as {last_payload}")
        await asyncio.sleep(0.1)
    raise AcceptanceFailure(f"task {task_id} did not complete before timeout: {last_payload}")


def scan_for_forbidden_sources(recorder: Recorder) -> None:
    matches: list[str] = []
    for root in SOURCE_SCAN_ROOTS:
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in files:
            if not path.is_file() or path.suffix not in {".py", ".ts", ".vue"}:
                continue
            text = path.read_text(encoding="utf-8")
            for term in FORBIDDEN_SOURCE_TERMS:
                if term in text:
                    matches.append(f"{path.relative_to(REPO_ROOT)}:{term}")
    recorder.require(
        "clean-room source scan",
        not matches,
        "no forbidden TradingAgents-CN runtime/export terms"
        if not matches
        else ", ".join(matches[:8]),
    )


async def create_pending_task_directly(
    db_module: Any,
    *,
    user_id: str,
    symbol: str,
    request_text: str,
) -> str:
    from app.schemas.stock_analysis import StockAnalysisParams
    from app.services.stock_analysis.tasks import StockAnalysisTaskService

    async with db_module.async_session_maker() as session:
        task = await StockAnalysisTaskService(session).create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol=symbol),
            request_text=request_text,
        )
        task_id = task.id
        await session.commit()
        return task_id


async def create_failed_task_directly(
    db_module: Any,
    *,
    user_id: str,
    symbol: str,
) -> str:
    from app.schemas.stock_analysis import StockAnalysisParams
    from app.services.stock_analysis.tasks import StockAnalysisTaskService

    async with db_module.async_session_maker() as session:
        task = await StockAnalysisTaskService(session).create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol=symbol),
            request_text=f"acceptance failed task {symbol}",
        )
        task.status = "failed"
        task.progress = 100
        task.current_step = "failed"
        task.message = "acceptance failure fixture"
        task.error_message = "acceptance fixture"
        task_id = task.id
        await session.commit()
        return task_id


async def verify_api_flow(
    client: AsyncClient,
    db_module: Any,
    recorder: Recorder,
    *,
    timeout_seconds: float,
) -> None:
    main_user, headers = await register_and_login(client, username=f"stock_accept_{int(time.time())}")
    other_user, other_headers = await register_and_login(
        client,
        username=f"stock_accept_other_{int(time.time())}",
    )
    recorder.check("auth isolation users", main_user["id"] != other_user["id"], "two users created")

    kb_response = await client.post(
        "/api/v1/knowledge-base/",
        headers=headers,
        json={"name": "Stock analysis acceptance", "description": "Native AI assistant flow"},
    )
    require_response("create knowledge base", kb_response, 201)
    kb_id = kb_response.json()["id"]
    recorder.check("knowledge base setup", bool(kb_id), f"kb_id={kb_id}")

    sent = await client.post(
        "/api/v1/kb-chat/send",
        headers=headers,
        json={
            "knowledge_base_id": kb_id,
            "assistant_mode": "stock_analysis",
            "question": "分析 000001.SZ，A股，标准深度，重点看技术面、基本面、新闻风险和交易建议",
            "stock_analysis_params": {
                "symbol": "000001.SZ",
                "market_type": "A股",
                "analysis_date": "2026-06-15",
                "research_depth": "标准",
                "selected_modules": ["market", "social", "news", "fundamentals", "risk"],
                "include_sentiment": True,
                "include_risk": True,
                "language": "zh-CN",
            },
        },
    )
    require_response("send stock-analysis chat", sent, 200)
    sent_payload = sent.json()
    task_card = sent_payload["stock_analysis_task"]
    recorder.require(
        "AI chat task card",
        bool(task_card and task_card["status"] == "pending" and task_card["progress"] == 0),
        f"task_id={task_card['task_id']}, status={task_card['status']}",
    )

    task_payload = await wait_for_completed_task(
        client,
        headers,
        task_card["task_id"],
        timeout_seconds=timeout_seconds,
    )
    report_id = task_payload["report_id"]
    recorder.require(
        "task completion",
        task_payload["progress"] == 100 and bool(report_id),
        f"status={task_payload['status']}, report_id={report_id}",
    )

    result = await client.get(
        f"/api/v1/stock-analysis/tasks/{task_card['task_id']}/result",
        headers=headers,
    )
    require_response("get stock-analysis result", result, 200)
    report = result.json()["report"]
    compat = report[COMPAT_REPORT_KEY]
    missing_keys = [key for key in COMPAT_KEYS if not compat.get(key)]
    recorder.require(
        "TradingAgents-compatible fields",
        not missing_keys,
        "all compatible stage outputs present" if not missing_keys else str(missing_keys),
    )
    decision = report["decision"]
    recorder.require(
        "structured decision contract",
        decision["label"] in {"买入", "持有", "卖出"}
        and 0 <= decision["confidence_score"] <= 1
        and 0 <= decision["risk_score"] <= 1,
        (
            f"label={decision['label']}, confidence={decision['confidence_score']}, "
            f"risk={decision['risk_score']}"
        ),
    )
    recorder.check(
        "research disclaimer",
        "不构成投资建议" in report["disclaimer"],
        report["disclaimer"],
    )

    for export_format, expected_content_type in EXPORT_CONTENT_TYPES.items():
        exported = await client.get(
            f"/api/v1/stock-analysis/reports/{report_id}/export",
            headers=headers,
            params={"format": export_format},
        )
        require_response(f"export {export_format}", exported, 200)
        recorder.check(
            f"export {export_format}",
            exported.headers["content-type"].startswith(expected_content_type)
            and bool(exported.content),
            f"{exported.headers['content-type']}, {len(exported.content)} bytes",
        )

    saved_kb = await client.post(
        f"/api/v1/stock-analysis/reports/{report_id}/save-to-knowledge-base",
        headers=headers,
        json={"knowledge_base_id": kb_id, "title": "000001 acceptance stock report"},
    )
    require_response("save report to knowledge base", saved_kb, 201)
    saved_doc = saved_kb.json()
    document = await client.get(
        f"/api/v1/knowledge-base/{kb_id}/documents/{saved_doc['document_id']}",
        headers=headers,
    )
    require_response("read saved knowledge-base document", document, 200)
    recorder.check(
        "knowledge-base persistence",
        "兼容阶段输出" in document.json()["content"],
        f"document_id={saved_doc['document_id']}",
    )

    workspace = await client.post(
        "/api/v1/workspace/",
        headers=headers,
        json={
            "name": "Stock research acceptance",
            "description": "Native stock analysis reports",
            "workspace_type": "research",
        },
    )
    require_response("create research workspace", workspace, 201)
    workspace_id = workspace.json()["id"]
    saved_workspace = await client.post(
        f"/api/v1/stock-analysis/reports/{report_id}/save-to-workspace",
        headers=headers,
        json={"workspace_id": workspace_id, "title": "000001 workspace stock report"},
    )
    require_response("save report to research workspace", saved_workspace, 201)
    workspace_detail = await client.get(f"/api/v1/workspace/{workspace_id}", headers=headers)
    require_response("read research workspace", workspace_detail, 200)
    workspace_reports = workspace_detail.json()["settings"].get("stock_analysis_reports") or []
    recorder.check(
        "research workspace persistence",
        bool(workspace_reports and workspace_reports[-1]["report_id"] == report_id),
        f"workspace_id={workspace_id}, reports={len(workspace_reports)}",
    )

    history = await client.get(
        f"/api/v1/kb-chat/history/{sent_payload['conversation_id']}",
        headers=headers,
    )
    require_response("read chat history", history, 200)
    assistant_message = history.json()["messages"][-1]
    history_report = assistant_message["stock_analysis_report"]
    recorder.check(
        "chat history restores report card",
        bool(history_report and history_report["report_id"] == report_id),
        f"report_id={history_report['report_id'] if history_report else 'missing'}",
    )

    denied_task = await client.get(
        f"/api/v1/stock-analysis/tasks/{task_card['task_id']}",
        headers=other_headers,
    )
    denied_export = await client.get(
        f"/api/v1/stock-analysis/reports/{report_id}/export",
        headers=other_headers,
        params={"format": "markdown"},
    )
    recorder.check(
        "owner isolation",
        denied_task.status_code == 404 and denied_export.status_code == 404,
        f"task={denied_task.status_code}, export={denied_export.status_code}",
    )

    cancelled_task_id = await create_pending_task_directly(
        db_module,
        user_id=main_user["id"],
        symbol="000002.SZ",
        request_text="acceptance cancellation",
    )
    cancelled = await client.post(
        f"/api/v1/stock-analysis/tasks/{cancelled_task_id}/cancel",
        headers=headers,
    )
    require_response("cancel pending task", cancelled, 200)
    recorder.check(
        "task cancellation",
        cancelled.json()["status"] == "cancelled",
        f"task_id={cancelled_task_id}",
    )

    failed_task_id = await create_failed_task_directly(
        db_module,
        user_id=main_user["id"],
        symbol="000003.SZ",
    )
    retried = await client.post(
        f"/api/v1/stock-analysis/tasks/{failed_task_id}/retry",
        headers=headers,
    )
    require_response("retry failed task", retried, 200)
    retry_payload = retried.json()
    retry_task = await wait_for_completed_task(
        client,
        headers,
        retry_payload["task_id"],
        timeout_seconds=timeout_seconds,
    )
    recorder.check(
        "task retry",
        retry_payload["task_id"] != failed_task_id and retry_task["status"] == "completed",
        f"old={failed_task_id}, new={retry_payload['task_id']}",
    )

    for index in range(3):
        await create_pending_task_directly(
            db_module,
            user_id=main_user["id"],
            symbol=f"00000{index + 4}.SZ",
            request_text=f"acceptance concurrency {index}",
        )
    limited = await client.post(
        "/api/v1/kb-chat/send",
        headers=headers,
        json={
            "knowledge_base_id": kb_id,
            "assistant_mode": "stock_analysis",
            "question": "分析 000001.SZ",
        },
    )
    recorder.check(
        "concurrency limit",
        limited.status_code == 429
        and limited.json().get("details", {}).get("reason_code")
        == "stock_analysis_concurrency_limit",
        f"status={limited.status_code}, body={limited.text[:160]}",
    )

    unsupported_routes = [
        "/api/v1/analysis/single",
        "/api/analysis/single",
        "/api/v1/analysis/tasks/example/status",
        "/api/v1/analysis/tasks/example/result",
    ]
    unsupported_statuses = [
        (path, (await client.get(path, headers=headers)).status_code) for path in unsupported_routes
    ]
    recorder.check(
        "no legacy analysis routes",
        all(status == 404 for _, status in unsupported_statuses),
        ", ".join(f"{path}={status}" for path, status in unsupported_statuses),
    )


async def run(args: argparse.Namespace) -> int:
    recorder = Recorder()
    with tempfile.TemporaryDirectory(prefix="stock-analysis-acceptance-") as temp_dir:
        temp_root = Path(temp_dir)
        db_path = temp_root / "acceptance.db"
        configure_backend_env(db_path)

        previous_cwd = Path.cwd()
        os.chdir(temp_root)
        app, db_module = load_backend_app()
        try:
            scan_for_forbidden_sources(recorder)
            await create_schema(db_module)
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                timeout=args.http_timeout,
            ) as client:
                await verify_api_flow(
                    client,
                    db_module,
                    recorder,
                    timeout_seconds=args.task_timeout,
                )
            export_files = list((temp_root / "data" / "exports" / "stock-analysis").rglob("*"))
            exported_file_count = len([path for path in export_files if path.is_file()])
            recorder.check(
                "temporary export cleanup boundary",
                exported_file_count >= 4,
                f"temp_export_files={exported_file_count}",
            )
        finally:
            await db_module.engine.dispose()
            os.chdir(previous_cwd)

    if recorder.failed:
        emit("\nStock-analysis AI assistant acceptance failed:")
        for name in recorder.failed:
            emit(f"- {name}")
        return 1
    emit("\nStock-analysis AI assistant acceptance passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for each background stock-analysis task.",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=30.0,
        help="Per-request HTTP timeout for the in-process ASGI client.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        return asyncio.run(run(parse_args()))
    except AcceptanceFailure as exc:
        emit(f"\nStock-analysis AI assistant acceptance failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
