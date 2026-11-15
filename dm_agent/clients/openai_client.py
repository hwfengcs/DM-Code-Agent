"""OpenAI API 的客户端（使用官方 SDK）。"""

from __future__ import annotations

from typing import Any, cast

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .base_client import BaseLLMClient, LLMError, classify_retryable_exception


class OpenAIClient(BaseLLMClient):
    """OpenAI API 的轻量级封装（使用官方 SDK）。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-5",
        base_url: str = "",
        timeout: int = 600,
        respond_retries: int = 2,
    ) -> None:
        if not OPENAI_AVAILABLE:
            raise ImportError("openai 未安装。请运行: pip install openai")

        super().__init__(
            api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            respond_retries=respond_retries,
        )

        # 创建 OpenAI 客户端实例
        self.client = OpenAI(
            api_key=self.api_key,
            timeout=self.timeout,
            base_url=self.base_url or None,
            max_retries=0,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        **extra: Any,
    ) -> dict[str, Any]:
        """向 OpenAI API 发送生成请求。"""

        try:
            parameters = dict(extra)
            if "max_tokens" in parameters:
                parameters.setdefault("max_output_tokens", parameters.pop("max_tokens"))
            # Reasoning families do not universally accept sampling controls.
            if self.model.startswith(("gpt-5", "o1", "o3", "o4")):
                for key in ("temperature", "top_p"):
                    parameters.pop(key, None)
            response = self.client.responses.create(
                model=self.model,
                input=cast(Any, messages),
                **parameters,
            )

            # 返回包含响应的字典
            return {"response": response}

        except Exception as e:
            raise LLMError(
                f"OpenAI API 调用失败: {e}", retryable=classify_retryable_exception(e)
            ) from e

    def extract_text(self, data: dict[str, Any]) -> str:
        """从 OpenAI 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise LLMError("意外的响应负载类型。")

        # 从响应中提取文本
        response = data.get("response")
        if response:
            try:
                return response.output_text.strip()
            except Exception as e:
                raise LLMError(f"无法从 OpenAI 响应中提取文本: {e}") from e

        raise LLMError("无法从 OpenAI 响应中提取文本。")
