"""质谱AI GLM API 的 HTTP 客户端。"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from .base_client import BaseLLMClient, LLMError


class GLMError(LLMError):
    """当 GLM API 请求失败时抛出。"""


class GLMClient(BaseLLMClient):
    """质谱AI GLM 聊天补全 API 的轻量级封装。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "xxx",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        endpoint: str = "/chat/completions",
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
        **extra: Any,
    ) -> Dict[str, Any]:
        """向 GLM API 发送聊天式补全请求。"""

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        payload.update(extra)

        url = f"{self.base_url}/{self.endpoint.lstrip('/')}"
        response = self.session.post(url, json=payload, timeout=self.timeout)
        if not response.ok:
            message = self._format_error(response)
            raise GLMError(message)
        return response.json()

    def extract_text(self, data: Dict[str, Any]) -> str:
        """从 GLM 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise GLMError("意外的响应负载类型。")

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()

        raise GLMError("无法从 GLM 响应中提取文本。")

    @staticmethod
    def _format_error(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        message = f"GLM API error: {response.status_code} {response.reason}"
        if isinstance(body, dict):
            detail = body.get("error", {}).get("message") or body.get("error_msg")
            if not detail:
                detail = body.get("message")
            if detail:
                message = f"{message} - {detail}"
        elif body:
            message = f"{message} - {body}"
        return message
