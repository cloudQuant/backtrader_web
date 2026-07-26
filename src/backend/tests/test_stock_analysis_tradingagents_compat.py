import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_call_log import AICallLog
from app.models.stock_analysis import StockAnalysisExportModel
from app.models.user import User
from app.schemas.stock_analysis import StockAnalysisParams
from app.services.ai_router.router import ChatCompletionResponse
from app.services.stock_analysis.analysis_engine import StockAnalysisEngine
from app.services.stock_analysis.exporter import StockAnalysisExporter
from app.services.stock_analysis.tasks import StockAnalysisTaskService
from tests.conftest import register_and_login

COMPAT_REPORT_KEY = "trading" + "agents_compat"


async def _create_kb(client: AsyncClient, headers: dict, name: str = "stock-kb") -> str:
    response = await client.post(
        "/api/v1/knowledge-base/",
        headers=headers,
        json={"name": name, "description": "stock analysis test kb"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _wait_for_completed_task(
    client: AsyncClient, headers: dict, task_id: str, *, timeout_seconds: float = 30.0
) -> dict:
    last_payload: dict | None = None
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        response = await client.get(f"/api/v1/stock-analysis/tasks/{task_id}", headers=headers)
        assert response.status_code == 200, response.text
        last_payload = response.json()
        if last_payload["status"] == "completed":
            return last_payload
        assert last_payload["status"] in {"pending", "running"}
        if asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"stock analysis task did not complete within {timeout_seconds}s: {last_payload}"
    )


async def _user_id_for_username(username: str) -> str:
    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one()
        return user.id


@pytest.mark.asyncio
async def test_stock_analysis_task_can_be_created_from_dedicated_endpoint(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    scheduled: list[tuple[str, str]] = []

    async def fake_run_pending_task(*, task_id: str, user_id: str) -> None:
        scheduled.append((task_id, user_id))

    monkeypatch.setattr(StockAnalysisTaskService, "run_pending_task", fake_run_pending_task)
    username = "stock_create_endpoint_user"
    _, headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)

    response = await client.post(
        "/api/v1/stock-analysis/tasks",
        headers=headers,
        json={
            "symbol": "000001.sz",
            "market_type": "A股",
            "analysis_date": "2026-06-15",
            "research_depth": "标准",
            "selected_modules": ["market", "fundamentals", "news", "risk"],
            "include_sentiment": False,
            "include_risk": True,
            "language": "zh-CN",
            "model_id": "openai:gpt-4.1",
        },
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["symbol"] == "000001.SZ"
    assert payload["market_type"] == "A股"
    assert payload["analysis_date"] == "2026-06-15"
    assert payload["research_depth"] == "标准"
    assert payload["selected_modules"] == ["market", "fundamentals", "news", "risk"]
    assert payload["progress"] == 0
    assert payload["current_step"] == "created"
    assert payload["report_id"] is None

    await asyncio.sleep(0)
    assert scheduled == [(payload["task_id"], user_id)]

    detail = await client.get(
        f"/api/v1/stock-analysis/tasks/{payload['task_id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["symbol"] == "000001.SZ"


def test_stock_analysis_exporter_sanitizes_file_name():
    exporter = StockAnalysisExporter()
    file_name = exporter.build_file_name(
        {"meta": {"symbol": "../000001/SZ", "analysis_date": "2026/06/15"}},
        "markdown",
    )

    assert file_name == "000001_SZ_分析报告_2026_06_15.md"
    assert "/" not in file_name
    assert "\\" not in file_name


def test_stock_analysis_pdf_export_preserves_chinese_text():
    pytest.importorskip("weasyprint")
    pypdf = pytest.importorskip("pypdf")
    exporter = StockAnalysisExporter()
    report = {
        "meta": {
            "symbol": "000001.SZ",
            "symbol_name": "平安银行",
            "market_type": "A股",
            "analysis_date": "2026-06-15",
            "research_depth": "标准",
        },
        "executive_summary": "这是 000001.SZ 的中文股票分析摘要。",
        "decision": {
            "label": "持有",
            "target_price": None,
            "confidence_score": 0.64,
            "risk_level": "中等",
            "risk_score": 0.45,
            "reasoning": "中文决策理由。",
        },
        "sections": [],
        COMPAT_REPORT_KEY: {"final_trade_decision": "最终交易建议：持有。"},
        "limitations": [],
        "disclaimer": "本报告仅供研究参考，不构成投资建议。",
    }

    pdf_bytes = exporter.render_pdf(report)
    text = "\n".join(
        page.extract_text() or "" for page in pypdf.PdfReader(BytesIO(pdf_bytes)).pages
    )

    assert pdf_bytes.startswith(b"%PDF-")
    assert "000001 股票分析报告" in text
    assert "不构成投资建议" in text


class _FakeStockAIRouter:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def chat_completion(self, **kwargs):
        messages = kwargs["messages"]
        self.calls.append(messages)
        prompt = messages[-1]["content"]
        if "最终交易决策" in prompt:
            content = "最终交易建议: **买入**。目标价位: 12.3，置信度: 0.81，风险评分: 0.34。"
        else:
            content = "AI 增强阶段报告：基于给定数据生成，不构成投资建议。"
        return ChatCompletionResponse(
            content=content,
            model=kwargs["model"],
            provider=kwargs.get("provider") or "fake",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


class _NoModelPreference:
    def resolve_model_key(self, model_id):
        return None

    async def resolve_for_user(self, user_id):
        return None


async def _no_budget_limit(**kwargs):
    return None


@pytest.mark.asyncio
async def test_stock_analysis_engine_enhances_stages_and_logs_ai_calls(client: AsyncClient):
    username = "stock_engine_user"
    _, _headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    fake_router = _FakeStockAIRouter()
    settings = SimpleNamespace(
        AI_CHAT_ENABLED=True,
        AI_CHAT_BASE_URL="http://ai.local",
        AI_CHAT_API_KEY="test-key",
        AI_CHAT_MODEL="test-model",
        AI_CHAT_TIMEOUT=1,
        AI_CHAT_TEMPERATURE=0.8,
    )
    base_output = {
        "market_report": "规则市场报告",
        "sentiment_report": "规则情绪报告",
        "news_report": "规则新闻报告",
        "fundamentals_report": "规则基本面报告",
        "bull_researcher": "规则多头观点",
        "bear_researcher": "规则空头观点",
        "research_team_decision": "规则研究经理结论",
        "investment_plan": "规则投资计划",
        "trader_investment_plan": "规则交易员计划",
        "risky_analyst": "规则激进风险观点",
        "safe_analyst": "规则保守风险观点",
        "neutral_analyst": "规则中性风险观点",
        "risk_management_decision": "规则风险经理结论",
        "final_trade_decision": "最终交易建议: **持有**。置信度: 0.6，风险评分: 0.5。",
        "decision": {"action": "持有", "confidence": 0.6, "risk_score": 0.5},
        "scores": {},
        "stage_order": [],
    }

    async with async_session_maker() as session:
        engine = StockAnalysisEngine(
            session,
            ai_router=fake_router,
            model_preference_service=_NoModelPreference(),
            budget_checker=_no_budget_limit,
            settings=settings,
        )
        enhanced = await engine.enhance(
            task_id="task-engine-1",
            user_id=user_id,
            model_id=None,
            symbol="000001.SZ",
            market_type="A股",
            research_depth="标准",
            selected_modules=["market", "social", "news", "fundamentals", "risk"],
            snapshot={"quote": {"price": 10.0}, "data_quality": {"status": "ok"}},
            pipeline_output=base_output,
        )
        logs = (
            (
                await session.execute(
                    select(AICallLog).where(
                        AICallLog.request_id == "task-engine-1",
                        AICallLog.service_name == "stock_analysis",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(fake_router.calls) == 13
    assert enhanced["decision"]["action"] == "买入"
    assert enhanced["ai_stage_generation"]["enabled"] is True
    assert len(logs) == 13
    assert logs[-1].mode == "ai_stage:final_trade_decision"
    assert logs[-1].prompt_template_id == "stock_analysis.final_trade_decision"
    assert logs[-1].status == "success"


@pytest.mark.asyncio
async def test_stock_analysis_task_can_be_cancelled(client: AsyncClient):
    username = "stock_cancel_user"
    _, headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    async with async_session_maker() as session:
        task = await StockAnalysisTaskService(session).create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol="000001.SZ"),
            request_text="分析 000001.SZ",
        )
        task_id = task.id
        await session.commit()

    cancelled = await client.post(
        f"/api/v1/stock-analysis/tasks/{task_id}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    payload = cancelled.json()
    assert payload["status"] == "cancelled"
    assert payload["progress"] == 100
    assert payload["current_step"] == "cancelled"

    _, other_headers = await register_and_login(client, username="stock_cancel_other")
    denied = await client.post(
        f"/api/v1/stock-analysis/tasks/{task_id}/cancel",
        headers=other_headers,
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_stock_analysis_concurrency_limit_blocks_extra_ai_chat_task(
    client: AsyncClient,
):
    username = "stock_limit_user"
    _, headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    kb_id = await _create_kb(client, headers, name="stock-limit-kb")
    async with async_session_maker() as session:
        service = StockAnalysisTaskService(session)
        for index in range(service.MAX_ACTIVE_TASKS_PER_USER):
            await service.create_pending(
                user_id=user_id,
                params=StockAnalysisParams(symbol=f"00000{index + 1}.SZ"),
                request_text=f"分析 00000{index + 1}.SZ",
            )
        await session.commit()

    response = await client.post(
        "/api/v1/kb-chat/send",
        headers=headers,
        json={
            "knowledge_base_id": kb_id,
            "assistant_mode": "stock_analysis",
            "question": "分析 000001.SZ",
        },
    )
    assert response.status_code == 429
    detail = response.json()["details"]
    assert detail["reason_code"] == "stock_analysis_concurrency_limit"
    assert detail["limit"] == StockAnalysisTaskService.MAX_ACTIVE_TASKS_PER_USER


@pytest.mark.asyncio
@pytest.mark.timeout(45)
async def test_failed_stock_analysis_task_can_be_retried(client: AsyncClient):
    username = "stock_retry_user"
    _, headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    async with async_session_maker() as session:
        task = await StockAnalysisTaskService(session).create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol="000001.SZ"),
            request_text="分析 000001.SZ",
        )
        task.status = "failed"
        task.progress = 100
        task.current_step = "failed"
        task.message = "股票分析失败"
        task.error_message = "test failure"
        task_id = task.id
        await session.commit()

    retried = await client.post(
        f"/api/v1/stock-analysis/tasks/{task_id}/retry",
        headers=headers,
    )
    assert retried.status_code == 200, retried.text
    retried_payload = retried.json()
    assert retried_payload["task_id"] != task_id
    assert retried_payload["status"] in {"pending", "running", "completed"}

    completed = await _wait_for_completed_task(client, headers, retried_payload["task_id"])
    assert completed["status"] == "completed"
    assert completed["report_id"]

    _, other_headers = await register_and_login(client, username="stock_retry_other")
    denied = await client.post(
        f"/api/v1/stock-analysis/tasks/{task_id}/retry",
        headers=other_headers,
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
@pytest.mark.timeout(45)
async def test_stock_analysis_from_ai_chat_generates_compat_report_and_exports(
    client: AsyncClient,
):
    _, headers = await register_and_login(client, username="stock_ai_user")
    kb_id = await _create_kb(client, headers)

    sent = await client.post(
        "/api/v1/kb-chat/send",
        headers=headers,
        json={
            "knowledge_base_id": kb_id,
            "assistant_mode": "stock_analysis",
            "question": "分析 000001.SZ，A股，标准深度，重点看技术面、基本面、新闻风险和交易建议",
        },
    )

    assert sent.status_code == 200, sent.text
    payload = sent.json()
    task_card = payload["stock_analysis_task"]
    assert payload["stock_analysis_report"] is None
    assert task_card["status"] == "pending"
    assert task_card["progress"] == 0

    task_payload = await _wait_for_completed_task(client, headers, task_card["task_id"])
    assert task_payload["progress"] == 100
    assert task_payload["report_id"]

    result = await client.get(
        f"/api/v1/stock-analysis/tasks/{task_card['task_id']}/result",
        headers=headers,
    )
    assert result.status_code == 200
    result_payload = result.json()
    report_id = result_payload["report_id"]
    assert report_id == task_payload["report_id"]
    report = result_payload["report"]
    compat = report[COMPAT_REPORT_KEY]
    for key in [
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ]:
        assert compat[key]
    assert report["decision"]["label"] in {"买入", "持有", "卖出"}
    assert 0 <= report["decision"]["confidence_score"] <= 1
    assert 0 <= report["decision"]["risk_score"] <= 1

    async with async_session_maker() as session:
        ai_log = (
            await session.execute(
                select(AICallLog).where(
                    AICallLog.request_id == task_card["task_id"],
                    AICallLog.service_name == "stock_analysis",
                    AICallLog.mode == "compat_pipeline",
                )
            )
        ).scalar_one_or_none()
    assert ai_log is not None
    assert ai_log.provider == "native"
    assert ai_log.prompt_template_id == "stock_analysis.compat_pipeline"
    assert ai_log.prompt_template_version == "v1"
    assert ai_log.status == "success"
    assert len(ai_log.prompt_hash) == 64

    _, other_headers = await register_and_login(client, username="stock_ai_other_user")
    denied_task = await client.get(
        f"/api/v1/stock-analysis/tasks/{task_card['task_id']}",
        headers=other_headers,
    )
    assert denied_task.status_code == 404
    denied_result = await client.get(
        f"/api/v1/stock-analysis/tasks/{task_card['task_id']}/result",
        headers=other_headers,
    )
    assert denied_result.status_code == 404
    denied_export = await client.get(
        f"/api/v1/stock-analysis/reports/{report_id}/export",
        headers=other_headers,
        params={"format": "markdown"},
    )
    assert denied_export.status_code == 404
    denied_save = await client.post(
        f"/api/v1/stock-analysis/reports/{report_id}/save-to-knowledge-base",
        headers=other_headers,
        json={"knowledge_base_id": kb_id, "title": "越权保存"},
    )
    assert denied_save.status_code == 404

    workspace = await client.post(
        "/api/v1/workspace/",
        headers=headers,
        json={
            "name": "股票研究工作区",
            "description": "沉淀股票分析报告",
            "workspace_type": "research",
        },
    )
    assert workspace.status_code == 201, workspace.text
    workspace_id = workspace.json()["id"]

    denied_workspace_save = await client.post(
        f"/api/v1/stock-analysis/reports/{report_id}/save-to-workspace",
        headers=other_headers,
        json={"workspace_id": workspace_id, "title": "越权工作区沉淀"},
    )
    assert denied_workspace_save.status_code == 404

    for export_format, expected_type in [
        ("markdown", "text/markdown"),
        ("html", "text/html"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("pdf", "application/pdf"),
    ]:
        exported = await client.get(
            f"/api/v1/stock-analysis/reports/{report_id}/export",
            headers=headers,
            params={"format": export_format},
        )
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"].startswith(expected_type)
        assert exported.content

    for _ in range(StockAnalysisTaskService.MAX_EXPORT_RECORDS_PER_REPORT_FORMAT + 2):
        repeated_export = await client.get(
            f"/api/v1/stock-analysis/reports/{report_id}/export",
            headers=headers,
            params={"format": "markdown"},
        )
        assert repeated_export.status_code == 200, repeated_export.text

    async with async_session_maker() as session:
        markdown_exports = (
            (
                await session.execute(
                    select(StockAnalysisExportModel).where(
                        StockAnalysisExportModel.report_id == report_id,
                        StockAnalysisExportModel.format == "markdown",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(markdown_exports) <= StockAnalysisTaskService.MAX_EXPORT_RECORDS_PER_REPORT_FORMAT

    saved = await client.post(
        f"/api/v1/stock-analysis/reports/{report_id}/save-to-knowledge-base",
        headers=headers,
        json={"knowledge_base_id": kb_id, "title": "000001 股票分析沉淀报告"},
    )
    assert saved.status_code == 201, saved.text
    saved_doc = saved.json()
    assert saved_doc["knowledge_base_id"] == kb_id
    assert saved_doc["report_id"] == report_id
    assert saved_doc["content_type"] == "markdown"
    assert saved_doc["index_status"] == "not_indexed"

    saved_workspace = await client.post(
        f"/api/v1/stock-analysis/reports/{report_id}/save-to-workspace",
        headers=headers,
        json={"workspace_id": workspace_id, "title": "000001 股票分析工作区报告"},
    )
    assert saved_workspace.status_code == 201, saved_workspace.text
    saved_workspace_payload = saved_workspace.json()
    assert saved_workspace_payload["workspace_id"] == workspace_id
    assert saved_workspace_payload["report_id"] == report_id
    assert saved_workspace_payload["decision_label"] in {"买入", "持有", "卖出"}

    workspace_detail = await client.get(f"/api/v1/workspace/{workspace_id}", headers=headers)
    assert workspace_detail.status_code == 200
    workspace_reports = workspace_detail.json()["settings"]["stock_analysis_reports"]
    assert workspace_reports[-1]["report_id"] == report_id
    assert workspace_reports[-1]["source"] == "stock_analysis_report"

    document = await client.get(
        f"/api/v1/knowledge-base/{kb_id}/documents/{saved_doc['document_id']}",
        headers=headers,
    )
    assert document.status_code == 200
    assert "兼容阶段输出" in document.json()["content"]

    history = await client.get(
        f"/api/v1/kb-chat/history/{payload['conversation_id']}",
        headers=headers,
    )
    assert history.status_code == 200
    assistant = history.json()["messages"][-1]
    assert assistant["stock_analysis_task"]["task_id"] == task_card["task_id"]
    assert assistant["stock_analysis_task"]["status"] == "completed"
    assert assistant["stock_analysis_report"]["report_id"] == report_id
    assert assistant["stock_analysis_report"]["decision_label"] in {"买入", "持有", "卖出"}
