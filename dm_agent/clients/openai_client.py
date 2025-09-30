"""OpenAI API 的客户端（使用官方 SDK）。"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .base_client import BaseLLMClient, LLMError


class OpenAIClient(BaseLLMClient):
    """OpenAI API 的轻量级封装（使用官方 SDK）。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-5",
        base_url: str = "",  # OpenAI SDK 不需要 base_url
        timeout: int = 600,
    ) -> None:
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai 未安装。请运行: pip install openai"
            )

        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

        # 创建 OpenAI 客户端实例
        # 官方 SDK 不需要手动设置 base_url
        self.client = OpenAI(
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """向 OpenAI API 发送生成请求。"""

        try:
            # 将消息格式转换为输入字符串
            input_text = self._convert_messages_to_input(messages)

            # 调用 OpenAI responses API
            response = self.client.responses.create(
                model=self.model,
                input=input_text,
            )

            # 返回包含响应的字典
            return {"response": response}

        except Exception as e:
            raise LLMError(f"OpenAI API 调用失败: {e}")

    def extract_text(self, data: Dict[str, Any]) -> str:
        """从 OpenAI 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise LLMError("意外的响应负载类型。")

        # 从响应中提取文本
        response = data.get("response")
        if response:
            try:
                return response.output_text.strip()
            except Exception as e:
                raise LLMError(f"无法从 OpenAI 响应中提取文本: {e}")

        raise LLMError("无法从 OpenAI 响应中提取文本。")

    def _convert_messages_to_input(self, messages: List[Dict[str, str]]) -> str:
        """将标准消息格式转换为输入字符串。"""
        input_parts = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                input_parts.append(f"System: {content}")
            elif role == "user":
                input_parts.append(f"User: {content}")
            elif role == "assistant":
                input_parts.append(f"Assistant: {content}")
            else:
                input_parts.append(content)

        return "\n\n".join(input_parts)