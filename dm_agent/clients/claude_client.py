"""Claude (Anthropic) API 的客户端（使用官方 SDK）。"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from .base_client import BaseLLMClient, LLMError


class ClaudeClient(BaseLLMClient):
    """Claude API 的轻量级封装（使用官方 anthropic SDK）。"""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-sonnet-4-5",
        base_url: str = "",  # Claude SDK 不需要 base_url
        timeout: int = 600,
        anthropic_version: str = "2023-06-01",
    ) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic 未安装。请运行: pip install anthropic"
            )

        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)
        self.anthropic_version = anthropic_version

        # 创建 Anthropic 客户端实例
        # 官方 SDK 不需要手动设置 base_url
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def complete(
        self,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> Dict[str, Any]:
        """向 Claude API 发送消息请求。"""

        try:
            # Claude API 要求分离系统消息
            system_message = None
            claude_messages = []

            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                else:
                    claude_messages.append(msg)

            # 调用 Claude API
            kwargs = {
                "model": self.model,
                "messages": claude_messages,
                "max_tokens": extra.pop("max_tokens", 4096),
            }

            if system_message:
                kwargs["system"] = system_message

            kwargs.update(extra)

            response = self.client.messages.create(**kwargs)

            # 转换为字典格式
            return {"response": response}

        except Exception as e:
            raise LLMError(f"Claude API 调用失败: {e}")

    def extract_text(self, data: Dict[str, Any]) -> str:
        """从 Claude 响应中提取文本内容。"""

        if not isinstance(data, dict):
            raise LLMError("意外的响应负载类型。")

        # 从响应中提取文本
        response = data.get("response")
        if response:
            try:
                # Claude SDK 返回的 content 是一个列表
                if hasattr(response, 'content') and response.content:
                    # 提取所有文本块
                    text_parts = []
                    for block in response.content:
                        if hasattr(block, 'text'):
                            text_parts.append(block.text)
                    if text_parts:
                        return "\n".join(text_parts).strip()
            except Exception as e:
                raise LLMError(f"无法从 Claude 响应中提取文本: {e}")

        raise LLMError("无法从 Claude 响应中提取文本。")