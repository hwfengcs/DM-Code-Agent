"""ZhipuAI API 的客户端（使用官方 SDK）。"""

from __future__ import annotations

from typing import Any, Dict, List
from zai import ZhipuAiClient as ZhipuAiSDK
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .base_client import BaseLLMClient, LLMError


class ZhipuAIClient(BaseLLMClient):
    """ZhipuAI API 的轻量级封装（使用官方 SDK）。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "glm-4.7",
        base_url: str = "",  # zhipuai SDK 不需要 base_url
        timeout: int = 600,
    ) -> None:

        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

        # 创建 ZhipuAI 客户端实例
        # zhipuai SDK 不需要手动设置 base_url
        self.client = ZhipuAiSDK(
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """向 ZhipuAI API 发送生成请求。"""

        try:
            # 调用 ZhipuAI chat completions API
            # 直接传递消息列表，不需要转换为字符串
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            # 将响应对象转换为字典格式
            response_dict = {
                "choices": [{
                    "message": {
                        "content": response.choices[0].message.content
                    }
                }]
            }

            return response_dict

        except Exception as e:
            raise LLMError(f"ZhipuAI API 调用失败: {e}")

    def extract_text(self, data: Dict[str, Any]) -> str:
        """从 ZhipuAI 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise LLMError("意外的响应负载类型。")

        # 从响应中提取文本
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()

        raise LLMError("无法从 ZhipuAI 响应中提取文本。")

    