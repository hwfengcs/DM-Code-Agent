"""LLM 客户端基类定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LLMError(RuntimeError):
    """当 LLM API 请求失败时抛出。"""


class BaseLLMClient(ABC):
    """LLM 客户端的抽象基类。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        base_url: str,
        timeout: int = 600,
    ) -> None:
        if not api_key:
            raise ValueError("LLM 客户端需要 API 密钥。")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """发送聊天式补全请求到 LLM API。

        Args:
            messages: 消息列表，每个消息包含 role 和 content
            **extra: 额外的参数（如 temperature, max_tokens 等）

        Returns:
            API 响应的字典
        """
        pass

    @abstractmethod
    def extract_text(self, data: Dict[str, Any]) -> str:
        """从 API 响应中提取文本内容。

        Args:
            data: API 响应的字典

        Returns:
            提取的文本内容
        """
        pass

    def respond(self, messages: List[Dict[str, str]], **extra: Any) -> str:
        """返回补全响应的文本部分。

        Args:
            messages: 消息列表
            **extra: 额外的参数

        Returns:
            提取的文本响应
        """
        data = self.complete(messages, **extra)
        return self.extract_text(data)