"""通过显式扩展连接 Xinference 等 Chat Completions 服务，见 docs/local-models.md。"""

from __future__ import annotations

import os
from typing import Any, cast

from openai import OpenAI

from dm_agent.clients.base_client import BaseLLMClient, LLMError, classify_retryable_exception
from dm_agent.extensions import ExtensionAPI


class ChatCompletionsClient(BaseLLMClient):
    """保留消息角色，只调用调用者指定服务的 /chat/completions。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        base_url: str,
        timeout: int = 600,
        respond_retries: int = 2,
    ) -> None:
        if not base_url or not model:
            raise ValueError("openai-compatible requires --base-url and --model.")
        super().__init__(
            api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            respond_retries=respond_retries,
        )
        self.client = OpenAI(
            api_key=api_key, base_url=self.base_url, timeout=timeout, max_retries=0
        )

    def complete(self, messages: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
        if extra.get("stream"):
            raise LLMError("This extension supports non-streaming chat completions only.")
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=cast(Any, messages), **extra
            )
        except Exception as exc:
            raise LLMError(
                f"Chat Completions request failed: {exc}",
                retryable=classify_retryable_exception(exc),
            ) from exc
        return response.model_dump()

    def extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                return content.strip()
        raise LLMError(
            "The server returned no assistant text in choices[0].message.content. "
            "Use a chat/instruct model that returns final text; reasoning_content alone is insufficient."
        )


def create_client(
    *,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 600,
    **kwargs: Any,
) -> ChatCompletionsClient:
    # 独立变量避免把已有云供应商密钥意外送给本地服务。无鉴权服务使用占位值。
    return ChatCompletionsClient(
        api_key or os.environ.get("DM_COMPATIBLE_API_KEY") or "local-no-key",
        model=model or "",
        base_url=base_url or "",
        timeout=timeout,
        respond_retries=kwargs.get("respond_retries", 2),
    )


def setup(api: ExtensionAPI) -> None:
    api.register_provider("openai-compatible", create_client)
