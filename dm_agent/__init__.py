"""DM-Agent - 基于 ReAct 的多模型智能体系统

一个支持多种 LLM API (DeepSeek、OpenAI、Claude、Gemini) 的 ReAct 智能体实现。
"""

from .core import (
    AdaptiveReplanPolicy,
    CriticAgent,
    CriticReview,
    EpisodicMemory,
    Lesson,
    ReactAgent,
    ReplanDecision,
    ReplanSignal,
    Reflector,
    SelfConsistencyCandidate,
    SelfConsistencyRunner,
    Step,
)
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
from .memory import ContextCompressor, MemoryHit, MemoryItem, Mem0StyleMemory
from .skills import BaseSkill, ConfigSkill, SkillMetadata, SkillManager
from .tracing import TraceWriter

__version__ = "2.0.0"

__all__ = [
    # Core
    "ReactAgent",
    "Step",
    "AdaptiveReplanPolicy",
    "ReplanDecision",
    "ReplanSignal",
    "CriticAgent",
    "CriticReview",
    "SelfConsistencyRunner",
    "SelfConsistencyCandidate",
    "Reflector",
    "EpisodicMemory",
    "Lesson",
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
    # Memory
    "ContextCompressor",
    "MemoryHit",
    "MemoryItem",
    "Mem0StyleMemory",
    # Skills
    "BaseSkill",
    "ConfigSkill",
    "SkillMetadata",
    "SkillManager",
    "TraceWriter",
]
