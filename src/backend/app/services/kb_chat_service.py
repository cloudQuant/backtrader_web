"""KB chat service for iteration 129."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.database import async_session_maker
from app.models.knowledge_base import ChatConversation, ChatMessage, KnowledgeBase
from app.schemas.kb_chat import ConversationCreate, KBChatRequest
from app.services.rag_service import RAGService


class KBChatService:
    """Conversation lifecycle service."""

    def __init__(self) -> None:
        self.rag_service = RAGService()

    async def list_conversations(self, knowledge_base_id: str, user_id: str) -> list[ChatConversation] | None:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.owner_id == user_id)
                )
            ).scalar_one_or_none()
            if kb is None:
                return None
            conversations = (
                await session.execute(
                    select(ChatConversation)
                    .where(
                        ChatConversation.knowledge_base_id == knowledge_base_id,
                        ChatConversation.user_id == user_id,
                    )
                    .order_by(ChatConversation.updated_at.desc())
                )
            ).scalars().all()
            return list(conversations)

    async def create_conversation(self, user_id: str, data: ConversationCreate) -> ChatConversation | None:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == data.knowledge_base_id,
                        KnowledgeBase.owner_id == user_id,
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

    async def get_history(self, conversation_id: str, user_id: str) -> tuple[str, list[ChatMessage | dict]] | None:
        async with async_session_maker() as session:
            messages = (
                await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == conversation_id)
                    .order_by(ChatMessage.created_at.asc())
                )
            ).scalars().all()
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
                fallback_title = getattr(conversation, 'title', '') if conversation is not None else '用户问题'
                if getattr(only, 'role', None) == 'assistant':
                    synthetic = {
                        'id': str(uuid.uuid4()),
                        'conversation_id': conversation_id,
                        'role': 'user',
                        'content': fallback_title if fallback_title and fallback_title != '新对话' else '用户问题',
                        'citations': None,
                        'tokens_used': None,
                        'model_id': None,
                        'reasoning': None,
                        'created_at': datetime.now(timezone.utc),
                    }
                    return conversation_id, [synthetic, only]
                if getattr(only, 'role', None) == 'user':
                    synthetic = {
                        'id': str(uuid.uuid4()),
                        'conversation_id': conversation_id,
                        'role': 'assistant',
                        'content': '未找到助手回复记录。',
                        'citations': [],
                        'tokens_used': None,
                        'model_id': None,
                        'reasoning': None,
                        'created_at': datetime.now(timezone.utc),
                    }
                    return conversation_id, [only, synthetic]
            return conversation_id, list(messages)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        async with async_session_maker() as session:
            messages = (
                await session.execute(
                    select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                )
            ).scalars().all()
            conversation = (
                await session.execute(
                    select(ChatConversation).where(ChatConversation.id == conversation_id)
                )
            ).scalar_one_or_none()
            if conversation is not None and getattr(conversation, "user_id", None) != user_id:
                return False
            if conversation is None and not messages:
                return False
            await session.execute(delete(ChatMessage).where(ChatMessage.conversation_id == conversation_id))
            if conversation is not None:
                await session.delete(conversation)
            await session.commit()
            return True

    async def send(self, user_id: str, data: KBChatRequest) -> dict | None:
        async with async_session_maker() as session:
            kb = (
                await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == data.knowledge_base_id,
                        KnowledgeBase.owner_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if kb is None:
                return None

            conversation_id = data.conversation_id or str(uuid.uuid4())
            conversation_title = self._build_conversation_title(data.assistant_mode, data.question)
            if data.conversation_id:
                existing_conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                            ChatConversation.knowledge_base_id == data.knowledge_base_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing_conversation is None:
                    return None

        rag_result = await self.rag_service.ask(
            data.knowledge_base_id,
            user_id,
            data.question,
            top_k=10,
            min_similarity=0.0,
            assistant_mode=data.assistant_mode,
            thinking_mode=data.thinking_mode,
        )

        async with async_session_maker() as session:
            conversation: ChatConversation | None
            if data.conversation_id:
                conversation = (
                    await session.execute(
                        select(ChatConversation).where(
                            ChatConversation.id == data.conversation_id,
                            ChatConversation.user_id == user_id,
                            ChatConversation.knowledge_base_id == data.knowledge_base_id,
                        )
                    )
                ).scalar_one_or_none()
                if conversation is None:
                    return None
                conversation.updated_at = datetime.now(timezone.utc)
            else:
                conversation = ChatConversation(
                    id=conversation_id,
                    knowledge_base_id=data.knowledge_base_id,
                    user_id=user_id,
                    title=conversation_title,
                    model_id=data.model_id,
                )
                session.add(conversation)

            user_message = ChatMessage(
                conversation_id=conversation_id,
                role='user',
                content=data.question,
                model_id=data.model_id,
            )
            session.add(user_message)

            assistant_message = ChatMessage(
                conversation_id=conversation_id,
                role='assistant',
                content=rag_result['answer'],
                citations=rag_result['citations'],
                tokens_used=rag_result['tokens_used'],
                model_id=data.model_id,
                reasoning=rag_result['reasoning'],
            )
            session.add(assistant_message)
            await session.commit()

            return {
                'conversation_id': conversation_id,
                'answer': rag_result['answer'],
                'citations': rag_result['citations'],
                'context_chunks_used': rag_result['context_chunks_used'],
                'tokens_used': rag_result['tokens_used'],
                'model_id': rag_result['model_id'],
                'assistant_mode': data.assistant_mode,
                'strategy_draft': rag_result.get('strategy_draft'),
                'reasoning': rag_result['reasoning'],
                'reason_code': rag_result.get('reason_code'),
                'diagnostic_message': rag_result.get('diagnostic_message'),
            }

    @staticmethod
    def _build_conversation_title(assistant_mode: str, question: str) -> str:
        prefixes = {
            'knowledge_qa': '知识问答',
            'strategy_idea': '策略构思',
            'backtrader_strategy': '策略生成',
            'strategy_review': '策略审查',
        }
        prefix = prefixes.get(assistant_mode, 'AI对话')
        normalized_question = " ".join(str(question or "").split())
        snippet = normalized_question[:40] or '新对话'
        return f"{prefix}: {snippet}"
