"""DM-Agent - 基于 ReAct 的多模型智能体系统

一个支持多种 LLM API (DeepSeek、OpenAI、Claude、Gemini) 的 ReAct 智能体实现。
"""

from .clients import (
    PROVIDER_DEFAULTS,
    BaseLLMClient,
    ClaudeClient,
    DeepSeekClient,
    GeminiClient,
    LLMError,
    OpenAIClient,
    create_llm_client,
)
from .core import (
    AdaptiveReplanPolicy,
    ReactAgent,
    ReplanDecision,
    ReplanSignal,
    Step,
)
from .memory import ContextCompressor, Mem0StyleMemory, MemoryHit, MemoryItem
from .prompts import build_code_agent_prompt
from .skills import BaseSkill, ConfigSkill, SkillManager, SkillMetadata
from .tools import Tool, default_tools
from .tracing import TraceWriter

__version__ = "2.0.0"

__all__ = [
    "PROVIDER_DEFAULTS",
    "AdaptiveReplanPolicy",
    # Clients
    "BaseLLMClient",
    # Skills
    "BaseSkill",
    "ClaudeClient",
    "ConfigSkill",
    # Memory
    "ContextCompressor",
    "DeepSeekClient",
    "GeminiClient",
    "LLMError",
    "Mem0StyleMemory",
    "MemoryHit",
    "MemoryItem",
    "OpenAIClient",
    # Core
    "ReactAgent",
    "ReplanDecision",
    "ReplanSignal",
    "SkillManager",
    "SkillMetadata",
    "Step",
    # Tools
    "Tool",
    "TraceWriter",
    # Prompts
    "build_code_agent_prompt",
    "create_llm_client",
    "default_tools",
]
