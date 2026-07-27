"""Shared data models for deterministic agent evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalExpected:
    """Validation rules for one eval task."""

    required_actions: list[str] = field(default_factory=list)
    final_answer_contains: list[str] = field(default_factory=list)
    final_answer_contains_any: list[list[str]] = field(default_factory=list)
    workspace_files: dict[str, str] = field(default_factory=dict)
    metadata_min: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalTask:
    """A deterministic task driven by scripted LLM responses."""

    task_id: str
    name: str
    prompt: str
    planner_response: str | None
    agent_responses: list[str]
    expected: EvalExpected
    setup_files: dict[str, str] = field(default_factory=dict)
    replan_response: str | None = None
    max_steps: int = 8
    tags: list[str] = field(default_factory=list)
    # 传给 ReactAgent 构造函数的关键字覆盖（如小截断阈值），用于行为类 eval。
    agent_overrides: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "prompt": self.prompt,
            "tags": self.tags,
            "expected_actions": self.expected.required_actions,
            "expected_keywords": self.expected.final_answer_contains,
            "expected_keyword_groups": self.expected.final_answer_contains_any,
            "max_steps": self.max_steps,
        }


@dataclass(frozen=True)
class EvalResult:
    """Metrics and validation output for one task under one variant."""

    task_id: str
    task_name: str
    variant: str
    success: bool
    final_answer: str
    failure_reason: str
    actions: list[str]
    steps_count: int
    tool_calls: int
    duration_seconds: float
    prompt_chars: int
    completion_chars: int
    estimated_tokens: int
    estimated_cost_usd: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "variant": self.variant,
            "success": self.success,
            "final_answer": self.final_answer,
            "failure_reason": self.failure_reason,
            "actions": self.actions,
            "steps_count": self.steps_count,
            "tool_calls": self.tool_calls,
            "duration_seconds": self.duration_seconds,
            "prompt_chars": self.prompt_chars,
            "completion_chars": self.completion_chars,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "metadata": self.metadata,
        }
