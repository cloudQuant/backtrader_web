"""AI chat provider integration for KB copilot generation."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.config import get_settings
from app.schemas.strategy import AIStrategyDraft
from app.services.strategy_service import render_ai_strategy_draft_answer

_MODE_INSTRUCTIONS = {
    "knowledge_qa": """
你是 Backtrader Web 的知识库助手。优先回答用户问题，并明确引用上下文中的平台事实、接口能力、配置项和限制。
如果上下文不足，不要编造不存在的实现，直接说明缺失点。
""".strip(),
    "strategy_idea": """
你是量化策略研究助手。请把用户的一句话策略想法扩展成可执行的研究方案。
输出结构固定为：
1. 策略概述
2. 市场假设
3. 信号设计
4. 风控与仓位
5. 数据需求
6. 回测计划
7. 下一步建议
""".strip(),
    "backtrader_strategy": """
你是 Backtrader 策略 Copilot。请把用户需求转换成面向 Backtrader / Backtrader Web 的实现草案。
你必须返回一个 JSON 对象，不要使用 Markdown 代码块，不要输出 JSON 以外的内容。
JSON 结构：
{
  "answer_markdown": "给用户看的结构化说明，允许包含 Markdown",
  "strategy_draft": {
    "name": "策略名称",
    "description": "策略描述",
    "category": "trend|mean_reversion|volatility|indicator|arbitrage|custom",
    "code": "完整 Python/Backtrader 策略草案",
    "params": {
      "param_name": {
        "type": "int|float|string|enum",
        "default": 10,
        "min": 1,
        "max": 100,
        "options": null,
        "description": "参数说明"
      }
    },
    "rationale": "为什么这么设计",
    "next_steps": ["下一步1", "下一步2"],
    "suggested_symbol": null,
    "suggested_timeframe": "1d"
  }
}
""".strip(),
    "strategy_review": """
你是量化策略审查助手。请从策略逻辑、风控、数据质量、回测偏差、实现复杂度五个角度进行审查。
输出结构固定为：
1. 结论摘要
2. 主要风险
3. 缺失假设
4. 可改进项
5. 建议的验证顺序
""".strip(),
}


class AIChatService:
    """Generate KB chat answers via an OpenAI-compatible chat endpoint."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_enabled(self) -> bool:
        return bool(
            self.settings.AI_CHAT_ENABLED
            and self.settings.AI_CHAT_BASE_URL.strip()
            and self.settings.AI_CHAT_API_KEY.strip()
            and self.settings.AI_CHAT_MODEL.strip()
        )

    async def generate_answer(
        self,
        *,
        question: str,
        citations: list[dict[str, Any]],
        assistant_mode: str,
        thinking_mode: bool,
    ) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None

        messages = self._build_messages(
            question=question,
            citations=citations,
            assistant_mode=assistant_mode,
            thinking_mode=thinking_mode,
        )
        try:
            return await asyncio.to_thread(self._call_provider, messages, assistant_mode)
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            return None

    def _build_messages(
        self,
        *,
        question: str,
        citations: list[dict[str, Any]],
        assistant_mode: str,
        thinking_mode: bool,
    ) -> list[dict[str, str]]:
        mode_instruction = _MODE_INSTRUCTIONS.get(assistant_mode, _MODE_INSTRUCTIONS["knowledge_qa"])
        context_blocks = []
        for index, citation in enumerate(citations[:6], start=1):
            title = str(citation.get("document_title") or "未命名文档")
            chunk_index = citation.get("chunk_index")
            similarity = citation.get("similarity")
            content = str(citation.get("content") or "").strip()
            context_blocks.append(
                "\n".join(
                    [
                        f"[参考片段 {index}]",
                        f"文档: {title}",
                        f"Chunk: {chunk_index}",
                        f"相似度: {similarity}",
                        "内容:",
                        content,
                    ]
                )
            )
        context_text = "\n\n".join(context_blocks) if context_blocks else "无可用上下文"
        reasoning_hint = (
            "在最终答案前先给出一小段“分析摘要”，长度控制在 3-5 行。"
            if thinking_mode
            else "直接给出结构化结论，不要展开冗长推理。"
        )

        system_prompt = """
你是 Backtrader Web 的 AI Copilot。
你需要严格基于给定知识库上下文回答，帮助用户完成量化研究、策略设计与平台落地。
如果上下文无法支撑某个实现细节，要明确说明这是推断或需要补充信息。
""".strip()

        user_prompt = f"""
当前回答模式：
{assistant_mode}

模式要求：
{mode_instruction}

附加要求：
{reasoning_hint}
- 优先使用知识库中的平台事实、接口约束和术语。
- 若输出代码，默认使用 Python / Backtrader 风格。
- 若问题过于宽泛，先帮用户拆成可执行步骤。

用户问题：
{question}

知识库上下文：
{context_text}
""".strip()

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _call_provider(self, messages: list[dict[str, str]], assistant_mode: str) -> dict[str, Any]:
        endpoint = self._resolve_endpoint(self.settings.AI_CHAT_BASE_URL)
        payload = {
            "model": self.settings.AI_CHAT_MODEL,
            "messages": messages,
            "temperature": self.settings.AI_CHAT_TEMPERATURE,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.AI_CHAT_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.settings.AI_CHAT_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))

        answer = self._extract_content(body)
        if not answer:
            raise ValueError("AI provider returned empty content")

        usage = body.get("usage") or {}
        parsed_strategy_draft: dict[str, Any] | None = None
        if assistant_mode == "backtrader_strategy":
            parsed = self._parse_strategy_generation(answer)
            if parsed is not None:
                answer = parsed["answer"]
                parsed_strategy_draft = parsed["strategy_draft"]

        return {
            "answer": answer,
            "tokens_used": int(usage.get("total_tokens") or 0),
            "model_id": str(body.get("model") or self.settings.AI_CHAT_MODEL),
            "strategy_draft": parsed_strategy_draft,
            "reasoning": None,
        }

    @staticmethod
    def _resolve_endpoint(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    @staticmethod
    def _extract_content(body: dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def _parse_strategy_generation(content: str) -> dict[str, Any] | None:
        json_text = AIChatService._extract_json_object(content)
        if not json_text:
            return None
        payload = json.loads(json_text)
        strategy_payload = payload.get("strategy_draft", payload)
        draft = AIStrategyDraft.model_validate(strategy_payload)
        answer_text = str(payload.get("answer_markdown") or "").strip()
        if not answer_text:
            answer_text = render_ai_strategy_draft_answer(draft)
        return {
            "answer": answer_text,
            "strategy_draft": draft.model_dump(),
        }

    @staticmethod
    def _extract_json_object(content: str) -> str | None:
        stripped = content.strip()
        fenced = re.search(r"```json\s*(\{.*\})\s*```", stripped, flags=re.S)
        if fenced:
            return fenced.group(1).strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return stripped[start : end + 1]
        return None
