"""Data models for coding-agent benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BenchmarkTask:
    """One isolated coding task scored by hidden tests."""

    task_id: str
    name: str
    prompt: str
    setup_files: Dict[str, str]
    hidden_files: Dict[str, str]
    visible_test_command: List[str] = field(
        default_factory=lambda: ["{python}", "-m", "pytest", "-q"]
    )
    hidden_test_command: List[str] = field(
        default_factory=lambda: ["{python}", "-m", "pytest", "-q"]
    )
    max_steps: int = 14
    tags: List[str] = field(default_factory=list)
    allowed_changed_files: List[str] = field(default_factory=list)
    required_changed_files: List[str] = field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "prompt": self.prompt,
            "setup_files": sorted(self.setup_files),
            "hidden_test_count": len(self.hidden_files),
            "visible_test_command": self.visible_test_command,
            "hidden_test_command": self.hidden_test_command,
            "max_steps": self.max_steps,
            "tags": self.tags,
            "allowed_changed_files": self.allowed_changed_files,
            "required_changed_files": self.required_changed_files,
        }


@dataclass(frozen=True)
class BenchmarkVariant:
    name: str
    enable_planning: bool = True
    enable_skills: bool = True
    enable_compression: bool = True


@dataclass(frozen=True)
class BenchmarkRunConfig:
    provider: str = "deepseek"
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    timeout: int = 120
    temperature: float = 0.0
    repeat: int = 1
    max_steps: Optional[int] = None
    test_timeout: int = 30
    keep_workspaces: bool = False
    workspace_root: Optional[str] = None
    trace_dir: Optional[str] = None
    quiet: bool = True
    enable_reflexion: bool = False
    max_trials: int = 1
    enable_adaptive_replanning: bool = False
    max_replans: int = -1
    cost_per_1k_tokens: float = 0.0


@dataclass(frozen=True)
class CommandResult:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class CodingBenchResult:
    task_id: str
    task_name: str
    variant: str
    success: bool
    failure_reason: str
    final_answer: str
    actions: List[str]
    steps_count: int
    tool_calls: int
    duration_seconds: float
    prompt_chars: int
    completion_chars: int
    estimated_tokens: int
    estimated_cost_usd: float
    request_count: int
    metadata: Dict[str, Any]
    hidden_test: CommandResult
    changed_files: List[str] = field(default_factory=list)
    workspace_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "variant": self.variant,
            "success": self.success,
            "failure_reason": self.failure_reason,
            "final_answer": self.final_answer,
            "actions": self.actions,
            "steps_count": self.steps_count,
            "tool_calls": self.tool_calls,
            "duration_seconds": self.duration_seconds,
            "prompt_chars": self.prompt_chars,
            "completion_chars": self.completion_chars,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "request_count": self.request_count,
            "metadata": self.metadata,
            "hidden_test": self.hidden_test.to_dict(),
            "changed_files": self.changed_files,
            "workspace_path": self.workspace_path,
        }
