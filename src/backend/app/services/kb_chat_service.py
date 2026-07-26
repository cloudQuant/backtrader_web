"""KB chat service for iteration 129."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, or_, select

from app.db.database import async_session_maker
from app.models.knowledge_base import ChatConversation, ChatMessage, KnowledgeBase
from app.schemas.kb_chat import ConversationCreate, KBChatRequest
from app.services.rag_service import RAGService
from app.services.stock_analysis.tasks import StockAnalysisTaskService
from app.services.strategy_service import build_ai_strategy_draft, render_ai_strategy_draft_answer
from app.utils.datetime_utils import utc_now_naive
from app.utils.knowledge_base_settings import merge_knowledge_base_settings


class KBChatService:
    """Conversation lifecycle service."""

    def __init__(self) -> None:
        self.rag_service = RAGService()

    async def list_conversations(
        self, knowledge_base_id: str | None, user_id: str
    ) -> list[ChatConversation] | None:
        async with async_session_maker() as session:
            if knowledge_base_id is None:
                conversations = (
                    (
                        await session.execute(
                            select(ChatConversation)
                            .where(
                                ChatConversation.knowledge_base_id.is_(None),
                                ChatConversation.user_id == user_id,
                            )
                            .order_by(ChatConversation.updated_at.desc())
                        )
                    )
                    .scalars()
                    .all()
                )
                return list(conversations)

            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == knowledge_base_id,
                        or_(
                            KnowledgeBase.owner_id == user_id,
                            KnowledgeBase.is_public.is_(True),
                        ),
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return None
            conversations = (
                (
                    await session.execute(
                        select(ChatConversation)
                        .where(
                            ChatConversation.knowledge_base_id == knowledge_base_id,
                            ChatConversation.user_id == user_id,
                        )
                        .order_by(ChatConversation.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return list(conversations)

    async def create_conversation(
        self, user_id: str, data: ConversationCreate
    ) -> ChatConversation | None:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == data.knowledge_base_id,
                        or_(
                            KnowledgeBase.owner_id == user_id,
                            KnowledgeBase.is_public.is_(True),
                        ),
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return None
            conversation = ChatConversation(
                knowledge_base_id=data.knowledge_base_id,
                user_id=user_id,
                title=data.title,
                model_id=data.model_id,
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            return conversation

    async def get_history(
        self, conversation_id: str, user_id: str
    ) -> tuple[str, list[ChatMessage | dict]] | None:
        async with async_session_maker() as session:
            messages = (
                (
                    await session.execute(
                        select(ChatMessage)
                        .where(ChatMessage.conversation_id == conversation_id)
                        .order_by(ChatMessage.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            conversation = (
                await session.execute(
                    select(ChatConversation).where(ChatConversation.id == conversation_id)
                )
            ).scalar_one_or_none()
            if conversation is not None and getattr(conversation, "user_id", None) != user_id:
                return None
            if not messages:
                if conversation is None:
                    return None
                return conversation_id, []
            if len(messages) == 1:
                only = messages[0]
                fallback_title = (
                    getattr(conversation, "title", "") if conversation is not None else "用户问题"
                )
                if getattr(only, "role", None) == "assistant":
                    synthetic = {
                        "id": str(uuid.uuid4()),
                        "conversation_id": conversation_id,
                        "role": "user",
                        "content": fallback_title
                        if fallback_title and fallback_title != "新对话"
                        else "用户问题",
                        "citations": None,
                        "tokens_used": None,
                        "model_id": None,
                        "reasoning": None,
                        "created_at": datetime.now(timezone.utc),
                    }
                    return conversation_id, [synthetic, only]
                if getattr(only, "role", None) == "user":
                    synthetic = {
                        "id": str(uuid.uuid4()),
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": "未找到助手回复记录。",
                        "citations": [],
                        "tokens_used": None,
                        "model_id": None,
                        "reasoning": None,
                        "created_at": datetime.now(timezone.utc),
                    }
                    return conversation_id, [only, synthetic]
            return conversation_id, list(messages)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        async with async_session_maker() as session:
            messages = (
                (
                    await session.execute(
                        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                    )
                )
                .scalars()
                .all()
            )
            conversation = (
                await session.execute(
                    select(ChatConversation).where(ChatConversation.id == conversation_id)
                )
            ).scalar_one_or_none()
            if conversation is not None and getattr(conversation, "user_id", None) != user_id:
                return False
            if conversation is None and not messages:
                return False
            await session.execute(
                delete(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
            )
            if conversation is not None:
                await session.delete(conversation)
            await session.commit()
            return True

    async def send(self, user_id: str, data: KBChatRequest) -> dict | None:
        if data.assistant_mode == "stock_analysis":
            return await self._send_stock_analysis(user_id, data)
        if data.assistant_mode != "knowledge_qa":
            return await self._send_standalone_assistant(user_id, data)
        if not data.knowledge_base_id:
            return None

        conversation_history: list[dict] = []
        kb_settings: dict = {}
        knowledge_base_id = data.knowledge_base_id
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == knowledge_base_id,
                        or_(
                            KnowledgeBase.owner_id == user_id,
                            KnowledgeBase.is_public.is_(True),
                        ),
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return None
            kb_settings = merge_knowledge_base_settings(getattr(kb, "settings", None))

            conversation_id = data.conversation_id or str(uuid.uuid4())
            conversation_title = self._build_conversation_title(data.assistant_mode, data.question)
            if data.conversation_id:
                existing_conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                            ChatConversation.knowledge_base_id == knowledge_base_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing_conversation is None:
                    return None
                history_rows = (
                    (
                        await session.execute(
                            select(ChatMessage)
                            .where(ChatMessage.conversation_id == data.conversation_id)
                            .order_by(ChatMessage.created_at.asc())
                        )
                    )
                    .scalars()
                    .all()
                )
                conversation_history = [
                    {
                        "role": message.role,
                        "content": message.content,
                        "citations": message.citations or [],
                    }
                    for message in history_rows
                ]

        rag_result = await self.rag_service.ask(
            knowledge_base_id,
            user_id,
            data.question,
            top_k=int(kb_settings.get("default_top_k") or 8),
            min_similarity=float(kb_settings.get("min_similarity") or 0.0),
            assistant_mode=data.assistant_mode,
            thinking_mode=data.thinking_mode,
            conversation_history=conversation_history,
            model_id=data.model_id,
        )

        async with async_session_maker() as session:
            conversation: ChatConversation | None
            if data.conversation_id:
                conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                            ChatConversation.knowledge_base_id == knowledge_base_id,
                        )
                    )
                ).scalar_one_or_none()
                if conversation is None:
                    return None
                conversation.updated_at = utc_now_naive()
            else:
                conversation = ChatConversation(
                    id=conversation_id,
                    knowledge_base_id=knowledge_base_id,
                    user_id=user_id,
                    title=conversation_title,
                    model_id=data.model_id,
                )
                session.add(conversation)

            user_message = ChatMessage(
                conversation_id=conversation_id,
                role="user",
                content=data.question,
                model_id=data.model_id,
            )
            session.add(user_message)

            assistant_message = ChatMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=rag_result["answer"],
                citations=rag_result["citations"],
                tokens_used=rag_result["tokens_used"],
                model_id=data.model_id,
                reasoning=rag_result["reasoning"],
                metadata_json={
                    "assistant_mode": data.assistant_mode,
                    "strategy_draft": rag_result.get("strategy_draft"),
                    "reason_code": rag_result.get("reason_code"),
                    "diagnostic_message": rag_result.get("diagnostic_message"),
                    "diagnostics": rag_result.get("diagnostics"),
                },
            )
            session.add(assistant_message)
            await session.commit()

            return {
                "conversation_id": conversation_id,
                "answer": rag_result["answer"],
                "citations": rag_result["citations"],
                "context_chunks_used": rag_result["context_chunks_used"],
                "tokens_used": rag_result["tokens_used"],
                "model_id": rag_result["model_id"],
                "assistant_mode": data.assistant_mode,
                "strategy_draft": rag_result.get("strategy_draft"),
                "reasoning": rag_result["reasoning"],
                "reason_code": rag_result.get("reason_code"),
                "diagnostic_message": rag_result.get("diagnostic_message"),
                "diagnostics": rag_result.get("diagnostics"),
            }

    async def _send_standalone_assistant(self, user_id: str, data: KBChatRequest) -> dict | None:
        conversation_history: list[dict[str, Any]] = []
        conversation_id = data.conversation_id or str(uuid.uuid4())
        async with async_session_maker() as session:
            if data.conversation_id:
                existing_conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing_conversation is None:
                    return None
                history_rows = (
                    (
                        await session.execute(
                            select(ChatMessage)
                            .where(ChatMessage.conversation_id == data.conversation_id)
                            .order_by(ChatMessage.created_at.asc())
                        )
                    )
                    .scalars()
                    .all()
                )
                conversation_history = [
                    {
                        "role": message.role,
                        "content": message.content,
                        "citations": message.citations or [],
                    }
                    for message in history_rows
                ]

        generated = await self._generate_standalone_answer(data, user_id, conversation_history)

        async with async_session_maker() as session:
            if data.conversation_id:
                conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                        )
                    )
                ).scalar_one_or_none()
                if conversation is None:
                    return None
                conversation.updated_at = utc_now_naive()
            else:
                conversation = ChatConversation(
                    id=conversation_id,
                    knowledge_base_id=None,
                    user_id=user_id,
                    title=self._build_conversation_title(data.assistant_mode, data.question),
                    model_id=data.model_id,
                )
                session.add(conversation)

            session.add(
                ChatMessage(
                    conversation_id=conversation_id,
                    role="user",
                    content=data.question,
                    model_id=data.model_id,
                )
            )
            session.add(
                ChatMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=generated["answer"],
                    citations=[],
                    tokens_used=generated["tokens_used"],
                    model_id=generated["model_id"],
                    reasoning=generated["reasoning"],
                    metadata_json={
                        "assistant_mode": data.assistant_mode,
                        "strategy_draft": generated.get("strategy_draft"),
                        "reason_code": generated.get("reason_code"),
                        "diagnostic_message": generated.get("diagnostic_message"),
                        "diagnostics": None,
                    },
                )
            )
            await session.commit()

        return {
            "conversation_id": conversation_id,
            "answer": generated["answer"],
            "citations": [],
            "context_chunks_used": 0,
            "tokens_used": generated["tokens_used"],
            "model_id": generated["model_id"],
            "assistant_mode": data.assistant_mode,
            "strategy_draft": generated.get("strategy_draft"),
            "stock_analysis_task": None,
            "stock_analysis_report": None,
            "reasoning": generated["reasoning"],
            "reason_code": generated.get("reason_code"),
            "diagnostic_message": generated.get("diagnostic_message"),
            "diagnostics": None,
        }

    async def _generate_standalone_answer(
        self,
        data: KBChatRequest,
        user_id: str,
        conversation_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ai_enabled = await self.rag_service.ai_chat_service.can_generate(
            user_id=user_id,
            model_id=data.model_id,
        )
        generated = await self.rag_service.ai_chat_service.generate_answer(
            question=data.question,
            citations=[],
            assistant_mode=data.assistant_mode,
            thinking_mode=data.thinking_mode,
            conversation_history=conversation_history,
            retrieval_diagnostics=None,
            knowledge_base_settings={
                "quant_focus": self._quant_focus_for_mode(data.assistant_mode)
            },
            user_id=user_id,
            model_id=data.model_id,
        )
        if generated is not None:
            strategy_draft = generated.get("strategy_draft")
            if data.assistant_mode == "backtrader_strategy" and strategy_draft is None:
                draft = build_ai_strategy_draft(data.question, [])
                strategy_draft = draft.model_dump()
                if not generated.get("answer"):
                    generated["answer"] = render_ai_strategy_draft_answer(draft)
            return {
                "answer": generated["answer"],
                "tokens_used": int(generated["tokens_used"]),
                "model_id": generated["model_id"],
                "strategy_draft": strategy_draft,
                "reasoning": generated["reasoning"],
                "reason_code": None,
                "diagnostic_message": None,
            }

        reason_code = "ai_provider_failed" if ai_enabled else "ai_not_configured"
        if data.assistant_mode == "backtrader_strategy":
            draft = build_ai_strategy_draft(data.question, [])
            diagnostic_message = (
                "AI 模型调用失败，已使用本地模板生成 Backtrader 策略草稿。"
                if ai_enabled
                else "当前系统未配置生成式 AI 模型，已使用本地模板生成 Backtrader 策略草稿。"
            )
            return {
                "answer": render_ai_strategy_draft_answer(draft),
                "tokens_used": 0,
                "model_id": None,
                "strategy_draft": draft.model_dump(),
                "reasoning": None,
                "reason_code": reason_code,
                "diagnostic_message": diagnostic_message,
            }

        mode_label = self._mode_label(data.assistant_mode)
        diagnostic_message = (
            f"AI 模型调用失败，无法完成{mode_label}。请检查模型服务后重试。"
            if ai_enabled
            else f"当前系统未配置生成式 AI 模型，无法完成{mode_label}。请先配置可用模型后重试。"
        )
        return {
            "answer": diagnostic_message,
            "tokens_used": 0,
            "model_id": None,
            "strategy_draft": None,
            "reasoning": None,
            "reason_code": reason_code,
            "diagnostic_message": diagnostic_message,
        }

    async def _send_stock_analysis(self, user_id: str, data: KBChatRequest) -> dict | None:
        async with async_session_maker() as session:
            conversation_id = data.conversation_id or str(uuid.uuid4())
            if data.conversation_id:
                conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                        )
                    )
                ).scalar_one_or_none()
                if conversation is None:
                    return None
                conversation.updated_at = utc_now_naive()
            else:
                conversation = ChatConversation(
                    id=conversation_id,
                    knowledge_base_id=None,
                    user_id=user_id,
                    title=self._build_conversation_title(data.assistant_mode, data.question),
                    model_id=data.model_id,
                )
                session.add(conversation)

            user_message = ChatMessage(
                conversation_id=conversation_id,
                role="user",
                content=data.question,
                model_id=data.model_id,
            )
            session.add(user_message)
            await session.flush()

            params = (
                data.stock_analysis_params
                or StockAnalysisTaskService.parse_params_from_question(data.question)
            )
            task_service = StockAnalysisTaskService(session)
            task = await task_service.create_pending(
                user_id=user_id,
                params=params,
                request_text=data.question,
                conversation_id=conversation_id,
            )
            task_card = task_service.task_to_card(task)
            metadata = {
                "assistant_mode": data.assistant_mode,
                "strategy_draft": None,
                "stock_analysis_task": task_card,
                "stock_analysis_report": None,
                "reason_code": None,
                "diagnostic_message": None,
                "diagnostics": None,
            }
            answer = f"已创建 {task.symbol} 的股票分析任务，正在后台执行兼容阶段分析。"
            assistant_message = ChatMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                citations=[],
                tokens_used=0,
                model_id=data.model_id,
                reasoning="股票分析通过原生兼容流水线生成，保留阶段顺序、报告字段和决策语义。",
                metadata_json=metadata,
            )
            session.add(assistant_message)
            await session.flush()
            task.assistant_message_id = assistant_message.id
            await session.commit()
            asyncio.create_task(
                StockAnalysisTaskService.run_pending_task(task_id=task.id, user_id=user_id)
            )

            return {
                "conversation_id": conversation_id,
                "answer": answer,
                "citations": [],
                "context_chunks_used": 0,
                "tokens_used": 0,
                "model_id": data.model_id,
                "assistant_mode": data.assistant_mode,
                "strategy_draft": None,
                "stock_analysis_task": task_card,
                "stock_analysis_report": None,
                "reasoning": assistant_message.reasoning,
                "reason_code": None,
                "diagnostic_message": None,
                "diagnostics": None,
            }

    @staticmethod
    def _mode_label(assistant_mode: str) -> str:
        return {
            "strategy_idea": "策略构思",
            "backtrader_strategy": "Backtrader 策略生成",
            "strategy_review": "策略审查",
            "trading_execution": "交易执行解析",
            "stock_analysis": "股票分析",
        }.get(assistant_mode, "AI 助手请求")

    @staticmethod
    def _quant_focus_for_mode(assistant_mode: str) -> str:
        return {
            "strategy_review": "strategy_review",
            "backtrader_strategy": "implementation",
            "trading_execution": "implementation",
        }.get(assistant_mode, "strategy_research")

    @staticmethod
    def _build_conversation_title(assistant_mode: str, question: str) -> str:
        prefixes = {
            "knowledge_qa": "知识问答",
            "strategy_idea": "策略构思",
            "backtrader_strategy": "策略生成",
            "strategy_review": "策略审查",
            "trading_execution": "交易执行",
            "stock_analysis": "股票分析",
        }
        prefix = prefixes.get(assistant_mode, "AI对话")
        normalized_question = " ".join(str(question or "").split())
        snippet = normalized_question[:40] or "新对话"
        return f"{prefix}: {snippet}"
