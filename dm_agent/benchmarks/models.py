"""Data models for coding-agent benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 判分强制的改动范围约束，`BenchmarkTask.scoped_prompt` 追加在 prompt 末尾。
#
# 三处措辞是照着实际失败样本写的，改动前先看 devlog 36：
#   - 说明「即使实现完全正确也判失败」——对齐 `_score_run` 的真实行为，
#     baseline 里 8 道违规题的隐藏测试全部是通过的。
#   - 显式点名「新建文件同样算」——Claude 那一轮有一题栽在新建 conftest.py。
#   - 显式放行读操作——否则约束会误伤探索步骤。
# 位置必须在 MAINTENANCE_PROMPT_SUFFIX 之后：后者有一句 "update tests when the task
# asks for a regression test"，会反向鼓励 agent 去动测试文件，靠末尾指令压过它。
SCOPE_CONSTRAINT_TEMPLATE = (
    "\n\nSCOPE CONSTRAINT (enforced by the grader): you may only create or modify "
    "these files: {allowed}. Changing any other file (including creating a new one, "
    "and including test files not in that list) fails this task even if your "
    "implementation is completely correct. Reading any file is unrestricted; the "
    "limit applies to writes only."
)


@dataclass(frozen=True)
class BenchmarkTask:
    """One isolated coding task scored by hidden tests."""

    task_id: str
    name: str
    prompt: str
    setup_files: dict[str, str]
    hidden_files: dict[str, str]
    visible_test_command: list[str] = field(
        default_factory=lambda: ["{python}", "-m", "pytest", "-q"]
    )
    hidden_test_command: list[str] = field(
        default_factory=lambda: ["{python}", "-m", "pytest", "-q"]
    )
    max_steps: int = 14
    tags: list[str] = field(default_factory=list)
    allowed_changed_files: list[str] = field(default_factory=list)
    required_changed_files: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
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

    def scoped_prompt(self) -> str:
        """prompt 追加改动范围约束；无 ``allowed_changed_files`` 时逐字返回原 prompt。

        这是**派生视图**，不改 ``self.prompt``——``benchmark_task_fingerprint`` 读的是
        字段本身，所以启用约束声明不会动 ``suite_signature``，两侧报告仍可直接
        ``dm-agent-score-diff``。这条不变量由 ``tests/test_coding_benchmarks.py`` 守着。

        逐题列出实际允许的文件，不能简化成「不要改测试」：有 4 道题的可改范围里
        本来就含 ``tests/``（如 ``retry_regression_tests``），一刀切会把它们判错。
        """
        if not self.allowed_changed_files:
            return self.prompt
        allowed = ", ".join(f"`{path}`" for path in self.allowed_changed_files)
        return self.prompt + SCOPE_CONSTRAINT_TEMPLATE.format(allowed=allowed)


@dataclass(frozen=True)
class BenchmarkVariant:
    name: str
    enable_planning: bool = True
    enable_skills: bool = True
    enable_compression: bool = True


@dataclass(frozen=True)
class BenchmarkRunConfig:
    provider: str = "deepseek"
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout: int = 120
    temperature: float = 0.0
    repeat: int = 1
    max_steps: int | None = None
    test_timeout: int = 30
    keep_workspaces: bool = False
    workspace_root: str | None = None
    trace_dir: str | None = None
    quiet: bool = True
    enable_adaptive_replanning: bool = False
    max_replans: int = -1
    cost_per_1k_tokens: float = 0.0
    # 把每题的 allowed_changed_files 声明进 prompt。默认关闭：既有 baseline 是在
    # 「agent 看不到约束」下跑的，开着会让两侧不可比。见 devlog 36。
    declare_allowed_files: bool = False
    # Advisory: run hidden tests node-by-node for partial credit (score unchanged).
    per_test_credit: bool = False


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
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
    actions: list[str]
    steps_count: int
    tool_calls: int
    duration_seconds: float
    prompt_chars: int
    completion_chars: int
    estimated_tokens: int
    estimated_cost_usd: float
    request_count: int
    metadata: dict[str, Any]
    hidden_test: CommandResult
    changed_files: list[str] = field(default_factory=list)
    workspace_path: str = ""

    def to_dict(self) -> dict[str, Any]:
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
