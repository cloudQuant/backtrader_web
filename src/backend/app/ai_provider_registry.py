"""Default AI provider registry used by settings and runtime services."""

from __future__ import annotations

from typing import Any

DEFAULT_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "openai": {
        "display_name": "OpenAI",
        "provider_type": "litellm",
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini"],
    },
    "anthropic": {
        "display_name": "Anthropic",
        "provider_type": "litellm",
        "base_url": None,
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
    },
    "ollama": {
        "display_name": "Ollama",
        "provider_type": "litellm",
        "base_url": "http://localhost:11434",
        "api_key_env": None,
        "models": ["ollama/qwen2.5-coder:7b", "ollama/llama3.1:8b"],
    },
    "volcengine_ark": {
        "display_name": "火山方舟",
        "provider_type": "openai_compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "api_key_env": "VOLCENGINE_ARK_API_KEY",
        "models": [
            "doubao-seed-2.0-code",
            "doubao-seed-2.0-pro",
            "doubao-seed-2.0-lite",
            "doubao-seed-code",
            "minimax-m2.7",
            "minimax-m3",
            "glm-5.1",
            "glm-5.2",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "kimi-k2.6",
        ],
    },
    "siliconflow": {
        "display_name": "硅基流动",
        "provider_type": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "models": [
            "deepseek-ai/DeepSeek-V4-Pro",
            "deepseek-ai/DeepSeek-V4-Flash",
            "moonshotai/Kimi-K2.6",
            "zai-org/GLM-5.1",
        ],
    },
    "together": {
        "display_name": "Together AI",
        "provider_type": "litellm",
        "base_url": None,
        "api_key_env": "TOGETHER_API_KEY",
        "models": ["together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    },
    "groq": {
        "display_name": "Groq",
        "provider_type": "litellm",
        "base_url": None,
        "api_key_env": "GROQ_API_KEY",
        "models": ["groq/llama-3.3-70b-versatile"],
    },
}


def get_default_provider_registry() -> dict[str, dict[str, Any]]:
    return {key: dict(value) for key, value in DEFAULT_PROVIDER_REGISTRY.items()}
