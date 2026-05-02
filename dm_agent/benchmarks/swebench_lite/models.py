"""Data models for the SWE-bench Lite benchmark suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SWEBenchInstance:
    """A single SWE-bench Lite task instance.

    Mirrors the schema of `princeton-nlp/SWE-bench_Lite` so that we can serialize
    instances to and from JSON without depending on the `datasets` library at
    consumption time.

    Attributes:
        instance_id: Unique ID, e.g. ``django__django-11099``.
        repo: GitHub ``owner/name`` slug, e.g. ``django/django``.
        version: Repository version label, e.g. ``"1.11"``.
        base_commit: Commit SHA the agent starts from.
        environment_setup_commit: Commit used for environment setup (often the
            same as ``base_commit``, occasionally different for older instances).
        problem_statement: Natural-language issue description shown to the agent.
        hints_text: Optional supplementary text from the upstream issue/PR.
        created_at: ISO timestamp of the upstream issue (used for stratification).
        patch: Reference solution patch (NEVER shown to the agent; verifier-only).
        test_patch: Patch that adds the hidden tests; applied before scoring.
        fail_to_pass: List of test node IDs expected to flip from FAIL to PASS.
        pass_to_pass: List of test node IDs expected to remain PASS.
    """

    instance_id: str
    repo: str
    version: str
    base_commit: str
    environment_setup_commit: str
    problem_statement: str
    hints_text: str = ""
    created_at: str = ""
    patch: str = ""
    test_patch: str = ""
    fail_to_pass: List[str] = field(default_factory=list)
    pass_to_pass: List[str] = field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        """Return a redacted view safe to embed in a benchmark report."""
        return {
            "instance_id": self.instance_id,
            "repo": self.repo,
            "version": self.version,
            "base_commit": self.base_commit,
            "environment_setup_commit": self.environment_setup_commit,
            "problem_statement_chars": len(self.problem_statement),
            "hints_chars": len(self.hints_text),
            "created_at": self.created_at,
            "fail_to_pass_count": len(self.fail_to_pass),
            "pass_to_pass_count": len(self.pass_to_pass),
        }


@dataclass(frozen=True)
class SWEBenchVerification:
    """Outcome of running hidden tests against an agent-produced patch."""

    patch_applied: bool
    fail_to_pass_pass: int
    fail_to_pass_total: int
    pass_to_pass_pass: int
    pass_to_pass_total: int
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_seconds: float = 0.0
    error: Optional[str] = None  # set when verification could not run at all

    @property
    def resolved(self) -> bool:
        """SWE-bench official: instance is resolved iff every FAIL_TO_PASS flips
        to PASS *and* every PASS_TO_PASS still passes."""
        if not self.patch_applied:
            return False
        if self.fail_to_pass_total == 0:
            return False
        return (
            self.fail_to_pass_pass == self.fail_to_pass_total
            and self.pass_to_pass_pass == self.pass_to_pass_total
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_applied": self.patch_applied,
            "fail_to_pass_pass": self.fail_to_pass_pass,
            "fail_to_pass_total": self.fail_to_pass_total,
            "pass_to_pass_pass": self.pass_to_pass_pass,
            "pass_to_pass_total": self.pass_to_pass_total,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "resolved": self.resolved,
        }


@dataclass(frozen=True)
class SWEBenchResult:
    """One agent run on one SWE-bench Lite instance."""

    instance_id: str
    repo: str
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
    request_count: int
    metadata: Dict[str, Any]
    verification: SWEBenchVerification
    prediction: str = ""  # the unified diff the agent produced
    workspace_path: str = ""
    trial: int = 1  # which trial produced this result (Reflexion / multi-trial)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "repo": self.repo,
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
            "request_count": self.request_count,
            "metadata": self.metadata,
            "verification": self.verification.to_dict(),
            "prediction": self.prediction,
            "workspace_path": self.workspace_path,
            "trial": self.trial,
        }


@dataclass(frozen=True)
class SWEBenchRunConfig:
    """Runtime configuration for a SWE-bench Lite run."""

    provider: str = "deepseek"
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    max_steps: int = 60
    temperature: float = 0.0
    test_timeout: int = 300
    instance_timeout: int = 1800
    use_docker: bool = False
    keep_workspaces: bool = False
    workspace_root: Optional[str] = None
    trace_dir: Optional[str] = None
    quiet: bool = True


class FailureCategory(str, Enum):
    """Failure-mode buckets used by the analyzer.

    Order matters: when multiple buckets apply we report the most-actionable.
    """

    PATCH_NOT_PRODUCED = "patch_not_produced"  # agent never emitted a usable diff
    PATCH_APPLY_FAILED = "patch_apply_failed"  # diff did not apply cleanly
    HIDDEN_TEST_FAIL = "hidden_test_fail"  # patch applied; FAIL_TO_PASS still fails
    REGRESSION = "regression"  # patch applied; PASS_TO_PASS broke
    MAX_STEPS = "max_steps"  # agent loop hit max_steps
    PARSE_ERROR = "parse_error"  # JSON parsing of agent output failed
    TOOL_ERROR = "tool_error"  # tool execution dominated the run
    TIMEOUT = "timeout"  # instance budget exceeded
    UNKNOWN = "unknown"
