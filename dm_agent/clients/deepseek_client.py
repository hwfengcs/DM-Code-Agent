"""DeepSeek Responses/Chat API 的 HTTP 客户端。"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

import requests

from .base_client import BaseLLMClient, LLMError

DEFAULT_RETRY_STATUS_CODES = frozenset({400, 408, 409, 429, 500, 502, 503, 504})


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
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        retry_status_codes: Optional[Iterable[int]] = None,
    ) -> None:
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0.")
        if retry_backoff < 0:
            raise ValueError("retry_backoff must be >= 0.")
        self.endpoint = endpoint
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.retry_status_codes = (
            DEFAULT_RETRY_STATUS_CODES
            if retry_status_codes is None
            else frozenset(retry_status_codes)
        )
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
        for retry_index in range(self.max_retries + 1):
            attempt = retry_index + 1
            has_retry_budget = retry_index < self.max_retries
            try:
                response = self.session.post(url, json=payload, timeout=self.timeout)
            except requests.RequestException as exc:
                if self._is_retryable_exception(exc) and has_retry_budget:
                    self._sleep_before_retry(retry_index)
                    continue
                message = "DeepSeek API request failed"
                if self._is_retryable_exception(exc) and attempt > 1:
                    message = f"{message} after {attempt} attempts"
                raise DeepSeekError(f"{message}: {exc}") from exc

            if response.ok:
                try:
                    return response.json()
                except ValueError as exc:
                    if has_retry_budget:
                        self._sleep_before_retry(retry_index)
                        continue
                    raise DeepSeekError(
                        f"DeepSeek API returned invalid JSON after {attempt} attempts: {exc}"
                    ) from exc

            message = self._format_error(response)
            if self._is_retryable_response(response) and has_retry_budget:
                self._sleep_before_retry(retry_index)
                continue
            if self._is_retryable_response(response) and attempt > 1:
                message = f"{message} after {attempt} attempts"
            raise DeepSeekError(message)

        raise DeepSeekError("DeepSeek API request failed after exhausting retry budget.")

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

    def _sleep_before_retry(self, retry_index: int) -> None:
        if self.retry_backoff <= 0:
            return
        time.sleep(self.retry_backoff * (2**retry_index))

    def _is_retryable_response(self, response: requests.Response) -> bool:
        return response.status_code in self.retry_status_codes

    @staticmethod
    def _is_retryable_exception(exc: requests.RequestException) -> bool:
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
        response = getattr(exc, "response", None)
        return response is None
