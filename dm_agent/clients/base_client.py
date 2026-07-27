"""LLM 客户端基类定义。"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

# Provider-agnostic transient-failure status codes (429/5xx plus common
# request-conflict/timeout codes). Semantic 4xx errors are never retried.
RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})

_RETRYABLE_NAME_TOKENS = (
    "timeout",
    "connection",
    "ratelimit",
    "internalserver",
    "serviceunavailable",
    "overloaded",
)
_RETRYABLE_TEXT_TOKENS = (
    "timed out",
    "timeout",
    "connection",
    "rate limit",
    "overloaded",
    "temporarily unavailable",
    "429",
    "502",
    "503",
    "504",
)


class LLMError(RuntimeError):
    """当 LLM API 请求失败时抛出。

    ``retryable`` 标记该错误是否为瞬时故障（超时/断连/429/5xx）。
    只有 retryable 的 LLMError 才会被 ``complete_with_retry`` 重试。
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def classify_retryable_exception(exc: Exception) -> bool:
    """Best-effort 判断 provider SDK 异常是否为瞬时故障。"""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "code", None)
    if isinstance(status, int) and status in RETRYABLE_STATUS_CODES:
        return True
    name = type(exc).__name__.lower()
    if any(token in name for token in _RETRYABLE_NAME_TOKENS):
        return True
    text = str(exc).lower()
    return any(token in text for token in _RETRYABLE_TEXT_TOKENS)


class BaseLLMClient(ABC):
    """LLM 客户端的抽象基类。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        base_url: str,
        timeout: int = 600,
        respond_retries: int = 2,
        respond_retry_backoff: float = 1.0,
    ) -> None:
        if not api_key:
            raise ValueError("LLM 客户端需要 API 密钥。")
        if respond_retries < 0:
            raise ValueError("respond_retries must be >= 0.")
        if respond_retry_backoff < 0:
            raise ValueError("respond_retry_backoff must be >= 0.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # 统一重试层：仅对 retryable=True 的 LLMError 指数退避重试。
        # 自带内部重试的客户端（如 DeepSeek）应传 respond_retries=0 防止双重重试。
        self.respond_retries = respond_retries
        self.respond_retry_backoff = respond_retry_backoff
        self.total_respond_retries = 0

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        **extra: Any,
    ) -> dict[str, Any]:
        """发送聊天式补全请求到 LLM API。

        Args:
            messages: 消息列表，每个消息包含 role 和 content
            **extra: 额外的参数（如 temperature, max_tokens 等）

        Returns:
            API 响应的字典
        """
        pass

    @abstractmethod
    def extract_text(self, data: dict[str, Any]) -> str:
        """从 API 响应中提取文本内容。

        Args:
            data: API 响应的字典

        Returns:
            提取的文本内容
        """
        pass

    def complete_with_retry(
        self,
        messages: list[dict[str, str]],
        **extra: Any,
    ) -> dict[str, Any]:
        """调用 ``complete``，对瞬时故障做有限的指数退避重试。"""
        attempts = self.respond_retries + 1
        for attempt in range(attempts):
            try:
                return self.complete(messages, **extra)
            except LLMError as exc:
                is_last = attempt == attempts - 1
                if not getattr(exc, "retryable", False) or is_last:
                    raise
                self.total_respond_retries += 1
                if self.respond_retry_backoff > 0:
                    time.sleep(self.respond_retry_backoff * (2**attempt))
        raise LLMError("LLM request failed after exhausting retry budget.")

    def respond(self, messages: list[dict[str, str]], **extra: Any) -> str:
        """返回补全响应的文本部分。

        Args:
            messages: 消息列表
            **extra: 额外的参数

        Returns:
            提取的文本响应
        """
        data = self.complete_with_retry(messages, **extra)
        return self.extract_text(data)
