"""LLM 客户端工厂函数。"""

from __future__ import annotations

from typing import Optional

from .base_client import BaseLLMClient
from .claude_client import ClaudeClient
from .deepseek_client import DeepSeekClient
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient


def create_llm_client(
    provider: str,
    api_key: str,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 600,
    **kwargs,
) -> BaseLLMClient:
    """创建 LLM 客户端实例。

    Args:
        provider: 提供商名称 ("deepseek", "openai", "claude", "gemini")
        api_key: API 密钥
        model: 模型名称（可选，使用默认值）
        base_url: API 基础 URL（可选，使用默认值）
        timeout: 请求超时时间（秒）
        **kwargs: 其他特定于提供商的参数

    Returns:
        对应的 LLM 客户端实例

    Raises:
        ValueError: 如果提供商不支持
    """
    provider_lower = provider.lower()

    if provider_lower == "deepseek":
        params = {
            "api_key": api_key,
            "model": model or "deepseek-chat",
            "base_url": base_url or "https://api.deepseek.com",
            "timeout": timeout,
        }
        return DeepSeekClient(**params)

    elif provider_lower == "openai":
        params = {
            "api_key": api_key,
            "model": model or "gpt-5",
            "base_url": base_url or "",  # OpenAI SDK 不需要 base_url
            "timeout": timeout,
        }
        return OpenAIClient(**params)

    elif provider_lower == "claude":
        params = {
            "api_key": api_key,
            "model": model or "claude-sonnet-4-5",
            "base_url": base_url or "",  # Claude SDK 不需要 base_url
            "timeout": timeout,
        }
        if "anthropic_version" in kwargs:
            params["anthropic_version"] = kwargs["anthropic_version"]
        return ClaudeClient(**params)

    elif provider_lower == "gemini":
        params = {
            "api_key": api_key,
            "model": model or "gemini-2.5-flash",
            "base_url": base_url or "",  # Gemini 不需要 base_url
            "timeout": timeout,
        }
        return GeminiClient(**params)

    else:
        raise ValueError(
            f"不支持的提供商: {provider}。"
            f"支持的提供商: deepseek, openai, claude, gemini"
        )


# 提供商默认配置
PROVIDER_DEFAULTS = {
    "deepseek": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
    "openai": {
        "model": "gpt-5",
        "base_url": "",  # OpenAI SDK 不需要 base_url
    },
    "claude": {
        "model": "claude-sonnet-4-5",
        "base_url": "",  # Claude SDK 不需要 base_url
    },
    "gemini": {
        "model": "gemini-2.5-flash",
        "base_url": "",  # Gemini 不需要 base_url
    },
}