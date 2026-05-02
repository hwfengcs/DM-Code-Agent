"""End-to-end runner for the SWE-bench Lite suite.

For each instance:

  1. Prepare a clean git workspace at ``base_commit + test_patch``.
  2. Run :class:`dm_agent.core.ReactAgent` inside that workspace, feeding it
     the natural-language ``problem_statement``.
  3. Collect the agent's prediction by diffing the workspace against the
     post-test_patch HEAD.
  4. Reset the workspace and run :func:`verify_prediction` to score the patch
     against ``FAIL_TO_PASS`` and ``PASS_TO_PASS``.
  5. Record per-instance metadata, usage, trace path, and verification result.

The runner intentionally does NOT activate variants. SWE-bench instances are
expensive enough that the canonical ablation surface is "feature on / off"
between separate runs, recorded in distinct ``bench_reports/*.json`` files.
"""

from __future__ import annotations

import os
import statistics
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.core import ReactAgent
from dm_agent.evals.real_runner import PROVIDER_API_KEY_ENV, UsageTrackingClient
from dm_agent.skills import SkillManager
from dm_agent.tools import default_tools
from dm_agent.tracing import TraceWriter

from .models import (
    SWEBenchInstance,
    SWEBenchResult,
    SWEBenchRunConfig,
    SWEBenchVerification,
)
from .verifier import empty_verification, verify_prediction
from .workspace import SWEBenchWorkspace, WorkspaceError


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _resolve_api_key(provider: str, override_env: Optional[str]) -> Optional[str]:
    if override_env:
        return os.environ.get(override_env)
    env_var = PROVIDER_API_KEY_ENV.get(provider.lower())
    if env_var:
        return os.environ.get(env_var)
    return None


def _build_agent(
    config: SWEBenchRunConfig,
    *,
    enable_planning: bool = True,
    enable_skills: bool = True,
    enable_compression: bool = True,
    trace_writer: Optional[TraceWriter] = None,
) -> tuple[ReactAgent, UsageTrackingClient]:
    provider = config.provider.lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    api_key = _resolve_api_key(provider, config.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Missing API key for provider {provider!r}. Set "
            f"{PROVIDER_API_KEY_ENV.get(provider, 'PROVIDER_API_KEY')} in the "
            f"environment or pass --api-key-env."
        )
    raw_client = create_llm_client(
        provider=provider,
        api_key=api_key,
        model=config.model or defaults.get("model"),
        base_url=config.base_url or defaults.get("base_url"),
    )
    client = UsageTrackingClient(raw_client)

    skill_manager: Optional[SkillManager] = None
    if enable_skills:
        skill_manager = SkillManager()
        skill_manager.load_all()

    tools = default_tools(include_mcp=False)
    agent = ReactAgent(
        client,
        tools,
        max_steps=config.max_steps,
        temperature=config.temperature,
        enable_planning=enable_planning,
        enable_compression=enable_compression,
        skill_manager=skill_manager,
        trace_writer=trace_writer,
    )
    return agent, client


def _build_task_prompt(instance: SWEBenchInstance) -> str:
    """Compose the user-facing task description shown to the agent.

    We surface the issue text and a directive that nudges the agent toward
    surgical edits rather than wholesale rewrites. We do NOT show the
    FAIL_TO_PASS / PASS_TO_PASS lists, the reference patch, or the test_patch.
    """
    parts = [
        f"You are working in a checkout of the GitHub repository {instance.repo} at "
        f"commit {instance.base_commit[:12]}. The repository's hidden tests have "
        f"already been added to the workspace; do not edit any test files.",
        "",
        "## Problem statement",
        instance.problem_statement.strip(),
    ]
    if instance.hints_text and instance.hints_text.strip():
        parts.extend(["", "## Hints", instance.hints_text.strip()])
    parts.extend(
        [
            "",
            "## Instructions",
            "- Read the relevant source files before editing.",
            "- Make a minimal, targeted change. Do not refactor unrelated code.",
            "- Do not modify any file under tests/, test/, or *_test.py / test_*.py.",
            "- Do not run git commands. Use the file editing tools.",
            "- When you are confident the fix is correct, finish with a short summary.",
        ]
    )
    return "\n".join(parts)


def _classify_failure_reason(
    instance: SWEBenchInstance,
    verification: SWEBenchVerification,
    metadata: Dict[str, Any],
) -> str:
    """Return a short string describing why this instance was not resolved."""
    if verification.resolved:
        return ""
    if verification.error == "empty_prediction":
        return "no_patch_produced"
    if verification.error == "patch_apply_failed":
        return "patch_apply_failed"
    if metadata.get("status") and metadata["status"] != "success":
        return f"agent_status_{metadata['status']}"
    if verification.fail_to_pass_pass < verification.fail_to_pass_total:
        return "fail_to_pass_unresolved"
    if verification.pass_to_pass_pass < verification.pass_to_pass_total:
        return "pass_to_pass_regression"
    if verification.error:
        return verification.error
    return "unknown"


def _run_single_instance(
    instance: SWEBenchInstance,
    config: SWEBenchRunConfig,
    *,
    workspace_root: Path,
    trace_dir: Optional[Path],
    enable_planning: bool = True,
    enable_skills: bool = True,
    enable_compression: bool = True,
) -> SWEBenchResult:
    trace_writer: Optional[TraceWriter] = None
    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_writer = TraceWriter(trace_dir / f"{instance.instance_id}.jsonl")
        trace_writer.record(
            "swebench_lite_instance",
            {
                "instance_id": instance.instance_id,
                "repo": instance.repo,
                "version": instance.version,
                "base_commit": instance.base_commit,
                "fail_to_pass_count": len(instance.fail_to_pass),
                "pass_to_pass_count": len(instance.pass_to_pass),
            },
        )

    workspace = SWEBenchWorkspace(instance, root_dir=workspace_root)

    try:
        try:
            workspace.setup()
        except WorkspaceError as exc:
            return SWEBenchResult(
                instance_id=instance.instance_id,
                repo=instance.repo,
                success=False,
                failure_reason=f"workspace_setup_failed: {exc}"[:500],
                final_answer="",
                actions=[],
                steps_count=0,
                tool_calls=0,
                duration_seconds=0.0,
                prompt_chars=0,
                completion_chars=0,
                estimated_tokens=0,
                request_count=0,
                metadata={"status": "workspace_setup_failed"},
                verification=empty_verification(instance, error="workspace_setup_failed"),
                prediction="",
                workspace_path=str(workspace._workspace_path or ""),
            )

        agent, client = _build_agent(
            config,
            enable_planning=enable_planning,
            enable_skills=enable_skills,
            enable_compression=enable_compression,
            trace_writer=trace_writer,
        )

        task_prompt = _build_task_prompt(instance)

        with chdir(workspace.path):
            stdout_buffer = StringIO()
            with redirect_stdout(stdout_buffer if config.quiet else sys.stdout):
                run_result = agent.run(task_prompt, max_steps=config.max_steps)

        steps = run_result.get("steps", [])
        metadata = run_result.get("metadata", {})
        actions: List[str] = [step.get("action", "") for step in steps]
        prediction = workspace.compute_prediction_diff()

        verification = verify_prediction(
            instance,
            workspace,
            prediction,
            test_timeout=config.test_timeout,
            use_docker=config.use_docker,
        )

        failure_reason = _classify_failure_reason(instance, verification, metadata)

        if trace_writer is not None:
            trace_writer.record(
                "swebench_lite_verification",
                {
                    "patch_applied": verification.patch_applied,
                    "fail_to_pass_pass": verification.fail_to_pass_pass,
                    "fail_to_pass_total": verification.fail_to_pass_total,
                    "pass_to_pass_pass": verification.pass_to_pass_pass,
                    "pass_to_pass_total": verification.pass_to_pass_total,
                    "resolved": verification.resolved,
                    "duration_seconds": verification.duration_seconds,
                    "error": verification.error,
                },
            )

        return SWEBenchResult(
            instance_id=instance.instance_id,
            repo=instance.repo,
            success=verification.resolved,
            failure_reason=failure_reason,
            final_answer=str(run_result.get("final_answer", ""))[:2000],
            actions=actions,
            steps_count=len(steps),
            tool_calls=sum(1 for a in actions if a not in {"finish", "task_complete", "error"}),
            duration_seconds=float(metadata.get("duration_seconds", 0.0)),
            prompt_chars=client.usage.prompt_chars,
            completion_chars=client.usage.completion_chars,
            estimated_tokens=client.usage.estimated_tokens,
            request_count=client.usage.request_count,
            metadata=metadata,
            verification=verification,
            prediction=prediction,
            workspace_path=str(workspace.path),
        )

    finally:
        if trace_writer is not None:
            trace_writer.close()
        if not config.keep_workspaces:
            workspace.__exit__(None, None, None)
        else:
            workspace.discard()


def run_swebench_lite(
    instances: Sequence[SWEBenchInstance],
    *,
    config: Optional[SWEBenchRunConfig] = None,
    enable_planning: bool = True,
    enable_skills: bool = True,
    enable_compression: bool = True,
) -> Dict[str, Any]:
    """Run the agent on a sequence of SWE-bench Lite instances.

    Args:
        instances: Instances to run, in order.
        config: Runtime configuration. ``None`` uses defaults.
        enable_planning: Toggle the agent's task planner.
        enable_skills: Toggle skill activation.
        enable_compression: Toggle context compression.

    Returns:
        A dict with summary statistics and per-instance results.
    """
    config = config or SWEBenchRunConfig()
    if not instances:
        raise ValueError("At least one instance is required.")

    if config.workspace_root:
        workspace_root = Path(config.workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
    else:
        workspace_root = Path(tempfile.mkdtemp(prefix="dm-agent-swebench-"))

    trace_dir = Path(config.trace_dir) if config.trace_dir else None

    results: List[SWEBenchResult] = []
    for instance in instances:
        result = _run_single_instance(
            instance,
            config,
            workspace_root=workspace_root,
            trace_dir=trace_dir,
            enable_planning=enable_planning,
            enable_skills=enable_skills,
            enable_compression=enable_compression,
        )
        results.append(result)

    provider = config.provider.lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    return {
        "mode": "swebench_lite",
        "provider": provider,
        "model": config.model or defaults.get("model"),
        "base_url": config.base_url or defaults.get("base_url"),
        "use_docker": config.use_docker,
        "ablation_flags": {
            "enable_planning": enable_planning,
            "enable_skills": enable_skills,
            "enable_compression": enable_compression,
        },
        "summary": summarize_results(results),
        "results": [result.to_dict() for result in results],
        "instances": [instance.to_public_dict() for instance in instances],
    }


def summarize_results(results: Sequence[SWEBenchResult]) -> Dict[str, Any]:
    """Aggregate per-instance results into the report headline."""
    if not results:
        return {
            "total": 0,
            "resolved": 0,
            "resolved_rate": 0.0,
            "patch_applied_rate": 0.0,
            "avg_steps": 0.0,
            "avg_tool_calls": 0.0,
            "avg_estimated_tokens": 0,
            "total_request_count": 0,
            "avg_duration_seconds": 0.0,
        }
    total = len(results)
    resolved = sum(1 for r in results if r.success)
    patch_applied = sum(1 for r in results if r.verification.patch_applied)
    return {
        "total": total,
        "resolved": resolved,
        "resolved_rate": resolved / total,
        "patch_applied_rate": patch_applied / total,
        "avg_steps": statistics.mean(r.steps_count for r in results),
        "avg_tool_calls": statistics.mean(r.tool_calls for r in results),
        "avg_estimated_tokens": int(statistics.mean(r.estimated_tokens for r in results)),
        "total_request_count": sum(r.request_count for r in results),
        "avg_duration_seconds": statistics.mean(r.duration_seconds for r in results),
    }


def render_markdown_report(report: Dict[str, Any]) -> str:
    """Render the runner output as a human-friendly Markdown report."""
    summary = report.get("summary", {})
    lines: List[str] = [
        "# SWE-bench Lite Report",
        "",
        f"- Provider: `{report.get('provider')}`",
        f"- Model: `{report.get('model')}`",
        f"- Use docker: `{report.get('use_docker', False)}`",
        f"- Total: `{summary.get('total', 0)}`",
        f"- Resolved: `{summary.get('resolved', 0)}` "
        f"({summary.get('resolved_rate', 0.0) * 100:.1f}%)",
        f"- Patch applied: `{summary.get('patch_applied_rate', 0.0) * 100:.1f}%`",
        f"- Avg steps: `{summary.get('avg_steps', 0.0):.2f}`",
        f"- Avg tool calls: `{summary.get('avg_tool_calls', 0.0):.2f}`",
        f"- Avg estimated tokens: `{summary.get('avg_estimated_tokens', 0)}`",
        f"- Total LLM requests: `{summary.get('total_request_count', 0)}`",
        f"- Avg duration (s): `{summary.get('avg_duration_seconds', 0.0):.1f}`",
        "",
        "## Ablation Flags",
        "",
    ]
    for flag, value in (report.get("ablation_flags") or {}).items():
        lines.append(f"- `{flag}`: `{value}`")
    lines.extend(
        [
            "",
            "## Per-Instance Results",
            "",
            "| Instance | Repo | Resolved | F2P | P2P | Steps | Tools | Tokens | Reason |",
            "| --- | --- | :-: | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for r in report.get("results", []):
        verif = r.get("verification", {})
        f2p = f"{verif.get('fail_to_pass_pass', 0)}/{verif.get('fail_to_pass_total', 0)}"
        p2p = f"{verif.get('pass_to_pass_pass', 0)}/{verif.get('pass_to_pass_total', 0)}"
        check = "✅" if r.get("success") else "❌"
        reason = r.get("failure_reason", "") or ""
        lines.append(
            f"| `{r['instance_id']}` | `{r['repo']}` | {check} | {f2p} | {p2p} | "
            f"{r['steps_count']} | {r['tool_calls']} | {r['estimated_tokens']} | {reason} |"
        )
    return "\n".join(lines) + "\n"
