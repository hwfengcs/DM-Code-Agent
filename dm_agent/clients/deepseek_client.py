"""DeepSeek Responses/Chat API 的 HTTP 客户端。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .base_client import BaseLLMClient, LLMError


class DeepSeekError(LLMError):
    """当 DeepSeek API 请求失败时抛出。"""


class DeepSeekClient(BaseLLMClient):
    """DeepSeek 聊天补全 API 的轻量级封装。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        endpoint: str = "/v1/chat/completions",
        timeout: int = 600,
    ) -> None:
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)
        self.endpoint = endpoint
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        response_format: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        **extra: Any,
    ) -> Dict[str, Any]:
        """向 DeepSeek API 发送聊天式补全请求。"""

        if stream:
            raise NotImplementedError("此客户端未实现流式传输。")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(extra)

        url = f"{self.base_url}/{self.endpoint.lstrip('/')}"
        response = self.session.post(url, json=payload, timeout=self.timeout)
        if not response.ok:
            message = self._format_error(response)
            raise DeepSeekError(message)
        return response.json()

    def extract_text(self, data: Dict[str, Any]) -> str:
        """从各种响应格式中提取助手文本内容。"""

        if not isinstance(data, dict):
            raise DeepSeekError("意外的响应负载类型。")

        # Responses API 风格
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        # Chat completions 风格
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    if isinstance(content, list):
                        parts = [
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and part.get("type") == "output_text"
                        ]
                        if parts:
                            return "".join(parts).strip()

        raise DeepSeekError("无法从 DeepSeek 响应中提取文本。")

    @staticmethod
    def _format_error(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        message = f"DeepSeek API error: {response.status_code} {response.reason}"
        if isinstance(body, dict):
            detail = body.get("error", {}).get("message") or body.get("error_msg")
            if not detail:
                detail = body.get("message")
            if detail:
                message = f"{message} - {detail}"
        elif body:
            message = f"{message} - {body}"
        return message
