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
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.core import EpisodicMemory, ReactAgent, Reflector
from dm_agent.evals.real_runner import PROVIDER_API_KEY_ENV, UsageTrackingClient
from dm_agent.prompts import build_code_agent_prompt
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
    system_prompt_addition: str = "",
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
    system_prompt = None
    if system_prompt_addition.strip():
        system_prompt = build_code_agent_prompt(tools) + "\n\n" + system_prompt_addition.strip()
    agent = ReactAgent(
        client,
        tools,
        max_steps=config.max_steps,
        temperature=config.temperature,
        system_prompt=system_prompt,
        enable_planning=enable_planning,
        enable_compression=enable_compression,
        skill_manager=skill_manager,
        trace_writer=trace_writer,
        enable_adaptive_replanning=config.enable_adaptive_replanning,
        max_replans=config.max_replans,
    )
    return agent, client


def _build_reflector(config: SWEBenchRunConfig) -> tuple[Reflector, UsageTrackingClient]:
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
    return Reflector(client), client


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


def _run_single_trial(
    instance: SWEBenchInstance,
    config: SWEBenchRunConfig,
    *,
    workspace_root: Path,
    trace_dir: Optional[Path],
    enable_planning: bool = True,
    enable_skills: bool = True,
    enable_compression: bool = True,
    reflexion_memory: Optional[EpisodicMemory] = None,
    trial_number: int = 1,
) -> SWEBenchResult:
    trace_writer: Optional[TraceWriter] = None
    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_name = (
            f"{instance.instance_id}.jsonl"
            if trial_number == 1
            else f"{instance.instance_id}-t{trial_number}.jsonl"
        )
        trace_writer = TraceWriter(trace_dir / trace_name)
        trace_writer.record(
            "swebench_lite_instance",
            {
                "instance_id": instance.instance_id,
                "repo": instance.repo,
                "version": instance.version,
                "base_commit": instance.base_commit,
                "fail_to_pass_count": len(instance.fail_to_pass),
                "pass_to_pass_count": len(instance.pass_to_pass),
                "trial": trial_number,
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
            system_prompt_addition=(
                reflexion_memory.render_for_prompt() if reflexion_memory is not None else ""
            ),
        )

        task_prompt = _build_task_prompt(instance)

        with chdir(workspace.path):
            stdout_buffer = StringIO()
            with redirect_stdout(stdout_buffer if config.quiet else sys.stdout):
                run_result = agent.run(task_prompt, max_steps=config.max_steps)

        steps = run_result.get("steps", [])
        metadata = dict(run_result.get("metadata", {}))
        metadata.update(
            {
                "trial": trial_number,
                "max_trials": config.max_trials,
                "reflexion_enabled": config.enable_reflexion,
                "reflexion_lesson_count": len(reflexion_memory or []),
            }
        )
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
            trial=trial_number,
        )

    finally:
        if trace_writer is not None:
            trace_writer.close()
        if not config.keep_workspaces:
            workspace.__exit__(None, None, None)
        else:
            workspace.discard()


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
    """Run one instance, optionally retrying with hidden-test Reflexion feedback."""
    if config.max_trials < 1:
        raise ValueError("max_trials must be at least 1")
    if not config.enable_reflexion or config.max_trials <= 1:
        return _run_single_trial(
            instance,
            config,
            workspace_root=workspace_root,
            trace_dir=trace_dir,
            enable_planning=enable_planning,
            enable_skills=enable_skills,
            enable_compression=enable_compression,
        )

    memory = EpisodicMemory()
    trial_results: List[SWEBenchResult] = []
    reflector: Optional[Reflector] = None
    reflector_client: Optional[UsageTrackingClient] = None
    lessons: List[str] = []

    for trial in range(1, config.max_trials + 1):
        result = _run_single_trial(
            instance,
            config,
            workspace_root=workspace_root,
            trace_dir=trace_dir,
            enable_planning=enable_planning,
            enable_skills=enable_skills,
            enable_compression=enable_compression,
            reflexion_memory=memory,
            trial_number=trial,
        )
        trial_results.append(result)
        if result.success or trial >= config.max_trials:
            return _merge_reflexion_trials(
                result,
                trial_results,
                lessons=lessons,
                reflector_client=reflector_client,
            )

        if reflector is None:
            try:
                reflector, reflector_client = _build_reflector(config)
            except Exception:  # noqa: BLE001 - fallback lesson still lets retry proceed
                reflector = None
                reflector_client = None
        feedback = _build_hidden_test_feedback(result)
        if reflector is not None:
            try:
                lesson = reflector.reflect(
                    task=_build_task_prompt(instance),
                    final_answer=result.final_answer,
                    metadata=result.metadata,
                    steps=[],
                    failure_feedback=feedback,
                )
            except Exception as exc:  # noqa: BLE001
                lesson = _fallback_swebench_lesson(result, error=str(exc))
        else:
            lesson = _fallback_swebench_lesson(result)
        memory.add(
            lesson,
            source="hidden_test_failure",
            metadata={"trial": trial, "failure_reason": result.failure_reason},
        )
        lessons.append(lesson)
    raise AssertionError("unreachable: max_trials validation should guarantee a return")


def _merge_reflexion_trials(
    final_result: SWEBenchResult,
    trial_results: Sequence[SWEBenchResult],
    *,
    lessons: Sequence[str],
    reflector_client: Optional[UsageTrackingClient],
) -> SWEBenchResult:
    """Return the final trial result with cumulative Reflexion telemetry."""
    metadata = dict(final_result.metadata)
    metadata.update(
        {
            "reflexion_enabled": True,
            "trial_count": len(trial_results),
            "max_trials": metadata.get("max_trials", len(trial_results)),
            "reflexion_lessons": list(lessons),
            "trials": [
                {
                    "trial": result.trial,
                    "success": result.success,
                    "failure_reason": result.failure_reason,
                    "steps_count": result.steps_count,
                    "tool_calls": result.tool_calls,
                    "estimated_tokens": result.estimated_tokens,
                    "request_count": result.request_count,
                }
                for result in trial_results
            ],
        }
    )
    reflection_prompt_chars = reflector_client.usage.prompt_chars if reflector_client else 0
    reflection_completion_chars = reflector_client.usage.completion_chars if reflector_client else 0
    reflection_tokens = reflector_client.usage.estimated_tokens if reflector_client else 0
    reflection_requests = reflector_client.usage.request_count if reflector_client else 0
    metadata["reflection_request_count"] = reflection_requests
    metadata["reflection_estimated_tokens"] = reflection_tokens

    return replace(
        final_result,
        actions=[action for result in trial_results for action in result.actions],
        steps_count=sum(result.steps_count for result in trial_results),
        tool_calls=sum(result.tool_calls for result in trial_results),
        duration_seconds=sum(result.duration_seconds for result in trial_results),
        prompt_chars=sum(result.prompt_chars for result in trial_results) + reflection_prompt_chars,
        completion_chars=(
            sum(result.completion_chars for result in trial_results) + reflection_completion_chars
        ),
        estimated_tokens=sum(result.estimated_tokens for result in trial_results)
        + reflection_tokens,
        request_count=sum(result.request_count for result in trial_results) + reflection_requests,
        metadata=metadata,
    )


def _build_hidden_test_feedback(result: SWEBenchResult) -> str:
    verification = result.verification
    return "\n".join(
        [
            f"failure_reason: {result.failure_reason}",
            f"patch_applied: {verification.patch_applied}",
            f"fail_to_pass: {verification.fail_to_pass_pass}/{verification.fail_to_pass_total}",
            f"pass_to_pass: {verification.pass_to_pass_pass}/{verification.pass_to_pass_total}",
            f"verification_error: {verification.error or ''}",
            f"stdout_tail:\n{verification.stdout_tail[-2000:]}",
            f"stderr_tail:\n{verification.stderr_tail[-1000:]}",
        ]
    )


def _fallback_swebench_lesson(result: SWEBenchResult, *, error: str = "") -> str:
    suffix = f" Reflection call failed: {error}" if error else ""
    return (
        f"Previous trial failed with {result.failure_reason or 'unknown failure'}. "
        "Use the hidden-test feedback to narrow the bug, avoid broad edits, and verify the "
        f"specific failing behavior before finishing.{suffix}"
    )


def run_swebench_lite(
    instances: Sequence[SWEBenchInstance],
    *,
    config: Optional[SWEBenchRunConfig] = None,
    enable_planning: bool = True,
    enable_skills: bool = True,
    enable_compression: bool = True,
    resume_results: Optional[Sequence[SWEBenchResult]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Run the agent on a sequence of SWE-bench Lite instances.

    Args:
        instances: Instances to run, in order.
        config: Runtime configuration. ``None`` uses defaults.
        enable_planning: Toggle the agent's task planner.
        enable_skills: Toggle skill activation.
        enable_compression: Toggle context compression.
        resume_results: Existing per-instance results to reuse by
            ``instance_id``. Used by long-running CLI resume/checkpoint mode.
        progress_callback: Optional hook called with a partial report after
            each newly completed instance.

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

    resume_by_id = {r.instance_id: r for r in resume_results or []}
    results: List[SWEBenchResult] = []
    reused_count = 0
    for instance in instances:
        if instance.instance_id in resume_by_id:
            result = resume_by_id[instance.instance_id]
            reused_count += 1
        else:
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
        if progress_callback is not None and instance.instance_id not in resume_by_id:
            progress_callback(
                build_report(
                    results,
                    instances,
                    config=config,
                    enable_planning=enable_planning,
                    enable_skills=enable_skills,
                    enable_compression=enable_compression,
                    reused_count=reused_count,
                )
            )

    return build_report(
        results,
        instances,
        config=config,
        enable_planning=enable_planning,
        enable_skills=enable_skills,
        enable_compression=enable_compression,
        reused_count=reused_count,
    )


def build_report(
    results: Sequence[SWEBenchResult],
    instances: Sequence[SWEBenchInstance],
    *,
    config: SWEBenchRunConfig,
    enable_planning: bool,
    enable_skills: bool,
    enable_compression: bool,
    reused_count: int = 0,
) -> Dict[str, Any]:
    """Build the serializable report payload for completed results."""
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
            "enable_reflexion": config.enable_reflexion,
            "max_trials": config.max_trials,
            "enable_adaptive_replanning": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
        },
        "token_economics": {
            "cost_per_1k_tokens": config.cost_per_1k_tokens,
        },
        "summary": summarize_results(results),
        "results": [result.to_dict() for result in results],
        "instances": [instance.to_public_dict() for instance in instances],
        "resume": {
            "selected_instances": len(instances),
            "completed_results": len(results),
            "reused_results": reused_count,
        },
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
            "avg_trials": 0.0,
            "pass_at_1": 0.0,
            "pass_at_k": 0.0,
        }
    total = len(results)
    resolved = sum(1 for r in results if r.success)
    patch_applied = sum(1 for r in results if r.verification.patch_applied)
    pass_at_1 = sum(1 for r in results if _success_at_trial(r, 1))
    return {
        "total": total,
        "resolved": resolved,
        "resolved_rate": resolved / total,
        "pass_at_1": pass_at_1 / total,
        "pass_at_k": resolved / total,
        "patch_applied_rate": patch_applied / total,
        "avg_steps": statistics.mean(r.steps_count for r in results),
        "avg_tool_calls": statistics.mean(r.tool_calls for r in results),
        "avg_estimated_tokens": int(statistics.mean(r.estimated_tokens for r in results)),
        "total_request_count": sum(r.request_count for r in results),
        "avg_duration_seconds": statistics.mean(r.duration_seconds for r in results),
        "avg_trials": statistics.mean(r.metadata.get("trial_count", r.trial) for r in results),
    }


def _success_at_trial(result: SWEBenchResult, trial: int) -> bool:
    for item in result.metadata.get("trials", []):
        if item.get("trial") == trial:
            return bool(item.get("success"))
    return result.success and result.trial == trial


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
        f"- Pass@1: `{summary.get('pass_at_1', 0.0) * 100:.1f}%`",
        f"- Pass@k: `{summary.get('pass_at_k', 0.0) * 100:.1f}%`",
        f"- Patch applied: `{summary.get('patch_applied_rate', 0.0) * 100:.1f}%`",
        f"- Avg trials: `{summary.get('avg_trials', 0.0):.2f}`",
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
