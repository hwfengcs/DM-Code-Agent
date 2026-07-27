"""LLM 客户端工厂函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from .base_client import BaseLLMClient
from .claude_client import ClaudeClient
from .deepseek_client import DeepSeekClient
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient

if TYPE_CHECKING:
    from dm_agent.extensions import ExtensionAPI, ExtensionRegistry


def create_llm_client(
    provider: str,
    api_key: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 600,
    extension_registry: ExtensionRegistry | None = None,
    **kwargs: Any,
) -> BaseLLMClient:
    """创建 LLM 客户端实例。

    Args:
        provider: 已注册的提供商名称
        api_key: API 密钥
        model: 模型名称（可选，使用默认值）
        base_url: API 基础 URL（可选，使用默认值）
        timeout: 请求超时时间（秒）
        extension_registry: 本次运行的扩展注册表；省略时只加载内置供应商
        **kwargs: 其他特定于提供商的参数

    Returns:
        对应的 LLM 客户端实例

    Raises:
        ValueError: 如果提供商不支持
    """
    if extension_registry is None:
        from dm_agent.extensions.discovery import create_builtin_registry

        extension_registry = create_builtin_registry()
    factory = extension_registry.get_provider_factory(provider)
    if factory is None:
        supported = ", ".join(extension_registry.get_provider_names())
        raise ValueError(f"不支持的提供商: {provider}。支持的提供商: {supported}")
    client = factory(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        **kwargs,
    )
    return cast(BaseLLMClient, client)


def register_builtin_providers(api: ExtensionAPI) -> None:
    """通过 ExtensionAPI 按既有顺序注册四家内置供应商。"""
    api.register_provider("deepseek", _create_deepseek_client)
    api.register_provider("openai", _create_openai_client)
    api.register_provider("claude", _create_claude_client)
    api.register_provider("gemini", _create_gemini_client)


def _create_deepseek_client(
    *,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 600,
    **kwargs: Any,
) -> BaseLLMClient:
    params: dict[str, Any] = {
        "api_key": api_key,
        "model": model or "deepseek-chat",
        "base_url": base_url or "https://api.deepseek.com",
        "timeout": timeout,
    }
    for key in ("max_retries", "retry_backoff", "retry_status_codes"):
        if key in kwargs:
            params[key] = kwargs[key]
    return DeepSeekClient(**params)


def _create_openai_client(
    *,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 600,
    **kwargs: Any,
) -> BaseLLMClient:
    params: dict[str, Any] = {
        "api_key": api_key,
        "model": model or "gpt-5",
        "base_url": base_url or "",
        "timeout": timeout,
    }
    if "respond_retries" in kwargs:
        params["respond_retries"] = kwargs["respond_retries"]
    return OpenAIClient(**params)


def _create_claude_client(
    *,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 600,
    **kwargs: Any,
) -> BaseLLMClient:
    params: dict[str, Any] = {
        "api_key": api_key,
        "model": model or "claude-sonnet-4-5",
        "base_url": base_url or "",
        "timeout": timeout,
    }
    for key in ("anthropic_version", "respond_retries"):
        if key in kwargs:
            params[key] = kwargs[key]
    return ClaudeClient(**params)


def _create_gemini_client(
    *,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 600,
    **kwargs: Any,
) -> BaseLLMClient:
    params: dict[str, Any] = {
        "api_key": api_key,
        "model": model or "gemini-2.5-flash",
        "base_url": base_url or "",
        "timeout": timeout,
    }
    if "respond_retries" in kwargs:
        params["respond_retries"] = kwargs["respond_retries"]
    return GeminiClient(**params)


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
