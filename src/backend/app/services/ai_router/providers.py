from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AIProviderSpec:
    name: str
    display_name: str
    provider_type: str
    base_url: str | None = None
    api_key_env: str | None = None
    models: tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True


def get_default_provider_specs() -> list[AIProviderSpec]:
    return [
        AIProviderSpec(
            name="openai",
            display_name="OpenAI",
            provider_type="litellm",
            api_key_env="OPENAI_API_KEY",
            models=("gpt-4o", "gpt-4o-mini"),
        ),
        AIProviderSpec(
            name="anthropic",
            display_name="Anthropic",
            provider_type="litellm",
            api_key_env="ANTHROPIC_API_KEY",
            models=("claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"),
        ),
        AIProviderSpec(
            name="ollama",
            display_name="Ollama",
            provider_type="litellm",
            base_url="http://localhost:11434",
            models=("ollama/qwen2.5-coder:7b", "ollama/llama3.1:8b"),
        ),
        AIProviderSpec(
            name="together",
            display_name="Together AI",
            provider_type="litellm",
            api_key_env="TOGETHER_API_KEY",
            models=("together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",),
        ),
        AIProviderSpec(
            name="groq",
            display_name="Groq",
            provider_type="litellm",
            api_key_env="GROQ_API_KEY",
            models=("groq/llama-3.3-70b-versatile",),
        ),
    ]
