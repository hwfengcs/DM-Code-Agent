"""DM-Agent - 基于 ReAct 的多模型智能体系统

一个支持多种 LLM API (DeepSeek、OpenAI、Claude、Gemini) 的 ReAct 智能体实现。
"""

from .core import ReactAgent, Step
from .clients import (
    BaseLLMClient,
    LLMError,
    DeepSeekClient,
    OpenAIClient,
    ClaudeClient,
    GeminiClient,
    create_llm_client,
    PROVIDER_DEFAULTS,
)
from .tools import Tool, default_tools
from .prompts import build_code_agent_prompt

__version__ = "1.0.0"

__all__ = [
    # Core
    "ReactAgent",
    "Step",
    # Clients
    "BaseLLMClient",
    "LLMError",
    "DeepSeekClient",
    "OpenAIClient",
    "ClaudeClient",
    "GeminiClient",
    "create_llm_client",
    "PROVIDER_DEFAULTS",
    # Tools
    "Tool",
    "default_tools",
    # Prompts
    "build_code_agent_prompt",
]