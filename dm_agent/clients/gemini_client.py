"""Google Gemini API 的客户端（使用 google.genai SDK）。"""

from __future__ import annotations

from typing import Any

try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from .base_client import BaseLLMClient, LLMError, classify_retryable_exception


class GeminiClient(BaseLLMClient):
    """Gemini API 的轻量级封装（使用 google.genai SDK）。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        base_url: str = "",
        timeout: int = 600,
        respond_retries: int = 2,
    ) -> None:
        if not GENAI_AVAILABLE:
            raise ImportError("google-genai 未安装。请运行: pip install google-genai")

        super().__init__(
            api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            respond_retries=respond_retries,
        )

        # 创建 genai 客户端实例
        http_options = types.HttpOptions(
            timeout=self.timeout * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
            base_url=self.base_url or None,
        )
        self.client = genai.Client(api_key=self.api_key, http_options=http_options)

    def complete(
        self,
        messages: list[dict[str, str]],
        **extra: Any,
    ) -> dict[str, Any]:
        """向 Gemini API 发送生成请求。"""

        try:
            parameters = dict(extra)
            if "max_tokens" in parameters:
                parameters.setdefault("max_output_tokens", parameters.pop("max_tokens"))
            systems = [msg["content"] for msg in messages if msg.get("role") == "system"]
            if systems:
                parameters["system_instruction"] = "\n\n".join(systems)
            contents = [
                types.Content(
                    role="model" if msg.get("role") == "assistant" else "user",
                    parts=[types.Part(text=msg.get("content", ""))],
                )
                for msg in messages
                if msg.get("role") != "system"
            ]
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(**parameters),
            )

            # 返回包含响应的字典
            return {"response": response}

        except Exception as e:
            raise LLMError(
                f"Gemini API 调用失败: {e}", retryable=classify_retryable_exception(e)
            ) from e

    def extract_text(self, data: dict[str, Any]) -> str:
        """从 Gemini 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise LLMError("意外的响应负载类型。")

        # 从响应中提取文本
        response = data.get("response")
        if response:
            try:
                return response.text.strip()
            except Exception as e:
                raise LLMError(f"无法从 Gemini 响应中提取文本: {e}") from e

        raise LLMError("无法从 Gemini 响应中提取文本。")
