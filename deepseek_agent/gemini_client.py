"""Google Gemini API 的客户端（使用 google.genai SDK）。"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from .base_client import BaseLLMClient, LLMError


class GeminiClient(BaseLLMClient):
    """Gemini API 的轻量级封装（使用 google.genai SDK）。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        base_url: str = "",  # Gemini 不需要 base_url
        timeout: int = 600,
    ) -> None:
        if not GENAI_AVAILABLE:
            raise ImportError(
                "google-genai 未安装。请运行: pip install google-genai"
            )

        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

        # 创建 genai 客户端实例
        self.client = genai.Client(api_key=self.api_key)

    def complete(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """向 Gemini API 发送生成请求。"""

        try:
            # 将消息格式转换为 Gemini 内容格式
            contents = self._convert_messages_to_contents(messages)

            # 调用 Gemini API
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents
            )

            # 返回包含响应的字典
            return {"response": response}

        except Exception as e:
            raise LLMError(f"Gemini API 调用失败: {e}")

    def extract_text(self, data: Dict[str, Any]) -> str:
        """从 Gemini 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise LLMError("意外的响应负载类型。")

        # 从响应中提取文本
        response = data.get("response")
        if response:
            try:
                return response.text.strip()
            except Exception as e:
                raise LLMError(f"无法从 Gemini 响应中提取文本: {e}")

        raise LLMError("无法从 Gemini 响应中提取文本。")

    def _convert_messages_to_contents(self, messages: List[Dict[str, str]]) -> str:
        """将标准消息格式转换为 Gemini 内容格式。"""
        # 合并所有消息内容
        contents_parts = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                contents_parts.append(f"System: {content}")
            elif role == "user":
                contents_parts.append(f"User: {content}")
            elif role == "assistant":
                contents_parts.append(f"Assistant: {content}")
            else:
                contents_parts.append(content)

        # 返回合并后的内容字符串
        return "\n\n".join(contents_parts)