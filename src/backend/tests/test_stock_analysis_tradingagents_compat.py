import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_call_log import AICallLog
from app.models.stock_analysis import (
    StockAnalysisExportModel,
    StockAnalysisReportModel,
    StockAnalysisTaskModel,
)
from app.models.user import User
from app.schemas.stock_analysis import StockAnalysisParams
from app.services.ai_router.router import ChatCompletionResponse
from app.services.stock_analysis.analysis_engine import StockAnalysisEngine
from app.services.stock_analysis.exporter import StockAnalysisExporter
from app.services.stock_analysis.report_builder import StockAnalysisReportBuilder
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


def _capture_pending_task_schedule(monkeypatch: pytest.MonkeyPatch):
    """Replace detached task execution with a deterministic test-controlled runner."""
    scheduled: list[tuple[str, str]] = []
    run_pending_task = StockAnalysisTaskService.run_pending_task

    async def fake_run_pending_task(*, task_id: str, user_id: str) -> None:
        scheduled.append((task_id, user_id))

    monkeypatch.setattr(StockAnalysisTaskService, "run_pending_task", fake_run_pending_task)
    return run_pending_task, scheduled


async def _user_id_for_username(username: str) -> str:
    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one()
        return user.id


@pytest.mark.asyncio
async def test_stock_analysis_task_can_be_created_from_dedicated_endpoint(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _, scheduled = _capture_pending_task_schedule(monkeypatch)
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


@pytest.mark.asyncio
async def test_stock_analysis_latest_report_returns_the_most_recent_completed_result(
    client: AsyncClient,
):
    username = "stock_latest_report_user"
    _, headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    now = datetime.now(timezone.utc)

    async with async_session_maker() as session:
        service = StockAnalysisTaskService(session)
        older_task = await service.create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol="000001.SZ"),
            request_text="分析 000001.SZ",
        )
        latest_task = await service.create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol="600000.SH"),
            request_text="分析 600000.SH",
        )
        older_report = StockAnalysisReportModel(
            task_id=older_task.id,
            user_id=user_id,
            symbol=older_task.symbol,
            market_type=older_task.market_type,
            analysis_date=older_task.analysis_date,
            title="旧报告",
            summary="旧报告摘要",
            report_json={"meta": {"symbol": older_task.symbol}},
            created_at=now - timedelta(minutes=1),
        )
        latest_report = StockAnalysisReportModel(
            task_id=latest_task.id,
            user_id=user_id,
            symbol=latest_task.symbol,
            market_type=latest_task.market_type,
            analysis_date=latest_task.analysis_date,
            title="最新报告",
            summary="最新报告摘要",
            report_json={"meta": {"symbol": latest_task.symbol}},
            created_at=now,
        )
        session.add_all([older_report, latest_report])
        await session.flush()
        for task, report in ((older_task, older_report), (latest_task, latest_report)):
            task.status = "completed"
            task.progress = 100
            task.current_step = "completed"
            task.report_id = report.id
            task.completed_at = report.created_at
        await session.commit()

    response = await client.get("/api/v1/stock-analysis/reports/latest", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["task"]["task_id"] == latest_task.id
    assert payload["task"]["report_id"] == latest_report.id
    assert payload["report"] == {"meta": {"symbol": "600000.SH"}}


def test_stock_analysis_exporter_sanitizes_file_name():
    exporter = StockAnalysisExporter()
    file_name = exporter.build_file_name(
        {"meta": {"symbol": "../000001/SZ", "analysis_date": "2026/06/15"}},
        "markdown",
    )

    assert file_name == "000001_SZ_分析报告_2026_06_15.md"
    assert "/" not in file_name
    assert "\\" not in file_name


def test_stock_analysis_report_builder_removes_markdown_controls_from_summary():
    raw_decision = (
        "# 平安银行最终交易决策\n\n---\n\n**最终交易建议：持有**\n\n"
        "## 决策依据\n\n当前处于震荡区间。"
    )

    report = StockAnalysisReportBuilder().build(
        symbol="000001.SZ",
        symbol_name="平安银行",
        market_type="A股",
        analysis_date="2026-07-24",
        research_depth="标准",
        snapshot={"data_quality": {"status": "ok"}},
        pipeline_output={
            "final_trade_decision": raw_decision,
            "decision": {"action": "持有", "reasoning": raw_decision},
            "scores": {},
        },
    )

    assert "最终交易建议：持有" in report["executive_summary"]
    assert not any(token in report["executive_summary"] for token in ("#", "**", "---"))
    assert not any(token in report["decision"]["reasoning"] for token in ("#", "**", "---"))


def test_stock_analysis_exporter_nests_ai_markdown_under_localized_stage_titles():
    exporter = StockAnalysisExporter()
    markdown = exporter.render_markdown(
        {
            "meta": {"symbol": "000001.SZ", "analysis_date": "2026-07-24"},
            "decision": {},
            COMPAT_REPORT_KEY: {
                "market_report": "# 盘面概览\n\n**趋势：** 区间震荡。",
            },
            "limitations": [],
        }
    )
    lines = markdown.splitlines()

    assert "## 技术与市场分析" in lines
    assert "## market_report" not in lines
    assert "### 盘面概览" in lines
    assert lines.count("# 000001 股票分析报告") == 1


def test_stock_analysis_html_export_renders_nested_ai_headings():
    exporter = StockAnalysisExporter()
    html = exporter.render_html(
        {
            "meta": {"symbol": "000001.SZ", "analysis_date": "2026-07-24"},
            "decision": {},
            COMPAT_REPORT_KEY: {
                "market_report": "# 盘面概览\n\n## 趋势判断\n\n区间震荡。",
            },
            "limitations": [],
        }
    )

    assert "<h3>盘面概览</h3>" in html
    assert "<h4>趋势判断</h4>" in html
    assert "<p>#### 趋势判断</p>" not in html


def test_stock_analysis_html_export_renders_ai_markdown_structures():
    exporter = StockAnalysisExporter()
    html = exporter.render_html(
        {
            "meta": {"symbol": "000001.SZ", "analysis_date": "2026-07-24"},
            "decision": {},
            COMPAT_REPORT_KEY: {
                "market_report": (
                    "**趋势：** 区间震荡。\n\n"
                    "- 支撑位：10.20\n"
                    "- 阻力位：10.80\n\n"
                    "| 指标 | 数值 |\n"
                    "| --- | --- |\n"
                    "| MACD | 金叉 |\n\n"
                    "```text\n风险控制：9.80\n```"
                ),
            },
            "limitations": [],
        }
    )

    assert "<strong>趋势：</strong>" in html
    assert "<ul>" in html
    assert "<li>支撑位：10.20</li>" in html
    assert "<table>" in html
    assert "<th>指标</th>" in html
    assert '<pre><code class="language-text">风险控制：9.80' in html
    assert "**趋势：**" not in html
    assert "| 指标 | 数值 |" not in html


def test_stock_analysis_html_export_declares_cjk_font_stack():
    html = StockAnalysisExporter().render_html(
        {"meta": {"symbol": "000001.SZ"}, "decision": {}, "limitations": []}
    )

    assert '"PingFang SC"' in html
    assert '"Hiragino Sans GB"' in html


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


class _TimeoutStockAIRouter:
    def __init__(self) -> None:
        self.calls = 0

    async def chat_completion(self, **kwargs):
        del kwargs
        self.calls += 1
        raise asyncio.TimeoutError()


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
async def test_stock_analysis_engine_stops_ai_stages_after_provider_timeout(
    client: AsyncClient,
):
    username = "stock_engine_timeout_user"
    _, _headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    timeout_router = _TimeoutStockAIRouter()
    settings = SimpleNamespace(
        AI_CHAT_ENABLED=True,
        AI_CHAT_BASE_URL="http://ai.local",
        AI_CHAT_API_KEY="test-key",
        AI_CHAT_MODEL="test-model",
        AI_CHAT_TIMEOUT=1,
        AI_CHAT_TEMPERATURE=0.2,
    )

    async with async_session_maker() as session:
        engine = StockAnalysisEngine(
            session,
            ai_router=timeout_router,
            model_preference_service=_NoModelPreference(),
            budget_checker=_no_budget_limit,
            settings=settings,
        )
        enhanced = await engine.enhance(
            task_id="task-engine-timeout",
            user_id=user_id,
            model_id=None,
            symbol="000001.SZ",
            market_type="A股",
            research_depth="标准",
            selected_modules=["market"],
            snapshot={"quote": {"price": 10.0}, "data_quality": {"status": "ok"}},
            pipeline_output={"scores": {}},
        )

    assert timeout_router.calls == 1
    assert enhanced["ai_stage_generation"]["degraded"] is True
    assert enhanced["ai_stage_generation"]["stages"] == [
        {
            "stage": "market",
            "status": "failed",
            "error_code": "TimeoutError",
            "message": "",
        }
    ]


@pytest.mark.asyncio
async def test_stock_analysis_reconciles_orphaned_active_tasks_after_restart(
    client: AsyncClient,
):
    username = "stock_reconcile_user"
    _, _headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    async with async_session_maker() as session:
        task = await StockAnalysisTaskService(session).create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol="000001.SZ"),
            request_text="分析 000001.SZ",
        )
        task_id = task.id
        await session.commit()

    assert await StockAnalysisTaskService.reconcile_orphaned_tasks() == 1

    async with async_session_maker() as session:
        task = (
            await session.execute(select(StockAnalysisTaskModel).where(StockAnalysisTaskModel.id == task_id))
        ).scalar_one()
        assert task.status == "failed"
        assert task.progress == 100
        assert task.current_step == "failed"
        assert task.error_message == "Task interrupted because the stock analysis service restarted"


@pytest.mark.asyncio
async def test_stock_analysis_interrupts_active_tasks_during_graceful_shutdown(
    client: AsyncClient,
):
    username = "stock_shutdown_user"
    _, _headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    async with async_session_maker() as session:
        task = await StockAnalysisTaskService(session).create_pending(
            user_id=user_id,
            params=StockAnalysisParams(symbol="000001.SZ"),
            request_text="分析 000001.SZ",
        )
        task_id = task.id
        await session.commit()

    assert await StockAnalysisTaskService.interrupt_active_tasks() == 1

    async with async_session_maker() as session:
        task = (
            await session.execute(select(StockAnalysisTaskModel).where(StockAnalysisTaskModel.id == task_id))
        ).scalar_one()
        assert task.status == "cancelled"
        assert task.progress == 100
        assert task.current_step == "cancelled"
        assert task.error_message == "Task cancelled due to application shutdown (graceful stop)"


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
async def test_failed_stock_analysis_task_can_be_retried(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
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

    run_pending_task, scheduled = _capture_pending_task_schedule(monkeypatch)
    retried = await client.post(
        f"/api/v1/stock-analysis/tasks/{task_id}/retry",
        headers=headers,
    )
    assert retried.status_code == 200, retried.text
    retried_payload = retried.json()
    assert retried_payload["task_id"] != task_id
    assert retried_payload["status"] in {"pending", "running", "completed"}
    await asyncio.sleep(0)
    assert scheduled == [(retried_payload["task_id"], user_id)]
    await run_pending_task(task_id=retried_payload["task_id"], user_id=user_id)

    completed_response = await client.get(
        f"/api/v1/stock-analysis/tasks/{retried_payload['task_id']}",
        headers=headers,
    )
    assert completed_response.status_code == 200, completed_response.text
    completed = completed_response.json()
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
    monkeypatch: pytest.MonkeyPatch,
):
    username = "stock_ai_user"
    _, headers = await register_and_login(client, username=username)
    user_id = await _user_id_for_username(username)
    kb_id = await _create_kb(client, headers)

    run_pending_task, scheduled = _capture_pending_task_schedule(monkeypatch)
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
    await asyncio.sleep(0)
    assert scheduled == [(task_card["task_id"], user_id)]
    await run_pending_task(task_id=task_card["task_id"], user_id=user_id)

    task_response = await client.get(
        f"/api/v1/stock-analysis/tasks/{task_card['task_id']}",
        headers=headers,
    )
    assert task_response.status_code == 200, task_response.text
    task_payload = task_response.json()
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
    document_content = document.json()["content"]
    assert "技术与市场分析" in document_content
    assert "## market_report" not in document_content

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
