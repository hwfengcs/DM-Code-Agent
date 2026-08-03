"""Runner for hidden-test coding benchmarks."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Sequence
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, cast

from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.core import ReactAgent
from dm_agent.evals.real_runner import PROVIDER_API_KEY_ENV, UsageTrackingClient
from dm_agent.skills import SkillManager
from dm_agent.tools import default_tools
from dm_agent.tracing import TraceWriter, analyze_events, load_trace_events

from .models import (
    BenchmarkRunConfig,
    BenchmarkTask,
    BenchmarkVariant,
    CodingBenchResult,
    CommandResult,
)
from .tasks import get_benchmark_tasks

BENCH_VARIANTS: list[BenchmarkVariant] = [
    BenchmarkVariant("full", True, True, True),
    BenchmarkVariant("no_planning", False, True, True),
    BenchmarkVariant("no_skills", True, False, True),
    BenchmarkVariant("no_compression", True, True, False),
]

DEFAULT_BENCH_VARIANTS: list[BenchmarkVariant] = [BENCH_VARIANTS[0]]


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_benchmark_suite(
    *,
    suite: str = "coding",
    tasks: Sequence[BenchmarkTask] | None = None,
    variants: Sequence[BenchmarkVariant] | None = None,
    task_ids: Iterable[str] | None = None,
    variant_names: Iterable[str] | None = None,
    config: BenchmarkRunConfig | None = None,
) -> dict[str, Any]:
    config = config or BenchmarkRunConfig()
    selected_tasks = list(tasks or get_benchmark_tasks(suite, task_ids))
    selected_variants = list(variants or DEFAULT_BENCH_VARIANTS)

    if task_ids and tasks is not None:
        allowed_tasks = set(task_ids)
        selected_tasks = [task for task in selected_tasks if task.task_id in allowed_tasks]

    if variant_names:
        allowed_variants = set(variant_names)
        selected_variants = [
            variant for variant in BENCH_VARIANTS if variant.name in allowed_variants
        ]

    if config.repeat < 1:
        raise ValueError("repeat must be at least 1")
    _validate_benchmark_config(config)
    if not selected_tasks:
        raise ValueError("no benchmark tasks selected")
    if not selected_variants:
        raise ValueError("no benchmark variants selected")

    results: list[CodingBenchResult] = []
    for repeat_index in range(config.repeat):
        for variant in selected_variants:
            for task in selected_tasks:
                results.append(
                    run_benchmark_task(
                        task,
                        variant,
                        config,
                        repeat_index=repeat_index,
                        suite=suite,
                    )
                )

    provider = config.provider.lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    return {
        "mode": f"{suite}_benchmark",
        "suite": suite,
        "provider": provider,
        "model": config.model or defaults.get("model"),
        "base_url": config.base_url or defaults.get("base_url"),
        "repeat": config.repeat,
        "adaptive_replanning": {
            "enabled": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
        },
        "token_economics": {
            "cost_per_1k_tokens": config.cost_per_1k_tokens,
        },
        "summary": summarize_benchmark_results(results, tasks=selected_tasks),
        "manifest": build_benchmark_manifest(
            suite=suite,
            tasks=selected_tasks,
            variants=selected_variants,
        ),
        "results": [result.to_dict() for result in results],
        "tasks": [task.to_public_dict() for task in selected_tasks],
        "variants": [variant.__dict__ for variant in selected_variants],
    }


def run_benchmark_task(
    task: BenchmarkTask,
    variant: BenchmarkVariant,
    config: BenchmarkRunConfig,
    *,
    repeat_index: int = 0,
    suite: str = "coding",
) -> CodingBenchResult:
    _validate_benchmark_config(config)

    if config.keep_workspaces:
        root = Path(config.workspace_root) if config.workspace_root else None
        if root:
            root.mkdir(parents=True, exist_ok=True)
        workspace = Path(
            tempfile.mkdtemp(
                prefix=f"dm-agent-bench-{task.task_id}-", dir=str(root) if root else None
            )
        )
        return _run_benchmark_task_in_workspace(
            task,
            variant,
            config,
            workspace,
            repeat_index=repeat_index,
            cleanup=False,
            suite=suite,
        )

    with tempfile.TemporaryDirectory(prefix=f"dm-agent-bench-{task.task_id}-") as tmp:
        return _run_benchmark_task_in_workspace(
            task,
            variant,
            config,
            Path(tmp),
            repeat_index=repeat_index,
            cleanup=True,
            suite=suite,
        )


def prepare_workspace(
    task: BenchmarkTask,
    workspace: Path,
    *,
    include_hidden: bool = False,
) -> None:
    _write_files(workspace, task.setup_files)
    if include_hidden:
        _write_files(workspace, task.hidden_files)


def run_hidden_tests(task: BenchmarkTask, workspace: Path, *, timeout: int = 30) -> CommandResult:
    return run_command(task.hidden_test_command, workspace, timeout=timeout)


def run_hidden_tests_per_node(
    task: BenchmarkTask, workspace: Path, *, timeout: int = 30
) -> dict[str, Any] | None:
    """Advisory per-test partial credit for hidden tests.

    Mirrors the SWE-bench verifier's node-level pattern (collect-only then run
    each node) without importing the swebench package. Returns None when
    collection fails so callers fall back to the binary suite result; the
    strict pass/fail score is never affected.
    """
    test_paths = sorted(
        path for path in task.hidden_files if path.endswith(".py") and "test" in Path(path).name
    )
    if not test_paths:
        return None
    collect = run_command(
        ["{python}", "-m", "pytest", "--collect-only", "-q", *test_paths],
        workspace,
        timeout=timeout,
    )
    if collect.returncode != 0:
        return None
    node_ids = [
        line.strip()
        for line in collect.stdout.splitlines()
        if "::" in line and not line.strip().startswith("=")
    ]
    if not node_ids:
        return None
    nodes: list[dict[str, Any]] = []
    passed = 0
    for node_id in node_ids:
        result = run_command(
            ["{python}", "-m", "pytest", node_id, "-q", "--no-header", "--tb=short"],
            workspace,
            timeout=timeout,
        )
        node_passed = result.returncode == 0
        passed += int(node_passed)
        nodes.append(
            {
                "node_id": node_id,
                "passed": node_passed,
                "returncode": result.returncode,
            }
        )
    return {
        "total": len(node_ids),
        "passed": passed,
        "pass_fraction": passed / len(node_ids),
        "nodes": nodes,
    }


def run_command(command: Sequence[str], cwd: Path, *, timeout: int = 30) -> CommandResult:
    started_at = time.perf_counter()
    resolved = _resolve_command(command)
    try:
        completed = subprocess.run(
            resolved,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return CommandResult(
            command=resolved,
            returncode=completed.returncode,
            stdout=_tail(completed.stdout),
            stderr=_tail(completed.stderr),
            duration_seconds=time.perf_counter() - started_at,
        )
    except subprocess.TimeoutExpired as exc:
        # 上面以 text=True 启动子进程，超时异常携带的 stdout/stderr 运行时必为 str；
        # typeshed 对 TimeoutExpired 统一标注为 bytes | None，故此处用 cast 声明实际类型
        # （cast 是运行时空操作，不改变任何行为）。
        timed_out_stdout = cast("str | None", exc.stdout)
        timed_out_stderr = cast("str | None", exc.stderr)
        return CommandResult(
            command=resolved,
            returncode=124,
            stdout=_tail(timed_out_stdout or ""),
            stderr=_tail((timed_out_stderr or "") + f"\nCommand timed out after {timeout}s"),
            duration_seconds=time.perf_counter() - started_at,
        )


BENCH_RECOVERY_SIGNAL_KEYS = (
    "parse_repair_count",
    "parse_error_count",
    "unknown_tool_count",
    "argument_error_count",
    "tool_error_count",
    "replan_count",
    "edit_guard_block_count",
)


def _bench_had_failure_signal(metadata: dict[str, Any]) -> bool:
    return any(int(metadata.get(key, 0) or 0) > 0 for key in BENCH_RECOVERY_SIGNAL_KEYS)


def _repeat_stability(group: Sequence[CodingBenchResult]) -> dict[str, Any] | None:
    """Aggregate per-task pass stability across --repeat runs (None if single-run)."""
    repeat_indexes = {result.metadata.get("repeat_index") for result in group}
    repeat_indexes.discard(None)
    if len(repeat_indexes) < 2:
        return None
    by_task: dict[str, list[bool]] = {}
    for result in group:
        by_task.setdefault(result.task_id, []).append(bool(result.success))
    per_task: dict[str, Any] = {}
    for task_id, passes in sorted(by_task.items()):
        per_task[task_id] = {
            "runs": len(passes),
            "passes": sum(passes),
            "pass_at_k": any(passes),
            "pass_pow_k": all(passes),
            "per_repeat_pass": list(passes),
        }
    task_rates = [entry["passes"] / entry["runs"] for entry in per_task.values()]
    return {
        "repeats": len(repeat_indexes),
        "per_task": per_task,
        "pass_at_k_rate": (
            sum(1 for entry in per_task.values() if entry["pass_at_k"]) / len(per_task)
        ),
        "pass_pow_k_rate": (
            sum(1 for entry in per_task.values() if entry["pass_pow_k"]) / len(per_task)
        ),
        "task_pass_rate_stddev": (statistics.pstdev(task_rates) if len(task_rates) > 1 else 0.0),
    }


def summarize_benchmark_results(
    results: Sequence[CodingBenchResult],
    *,
    tasks: Sequence[BenchmarkTask] | None = None,
) -> dict[str, Any]:
    by_variant: dict[str, list[CodingBenchResult]] = {}
    for result in results:
        by_variant.setdefault(result.variant, []).append(result)

    variants: dict[str, Any] = {}
    for name, group in by_variant.items():
        successes = [result for result in group if result.success]
        hidden_passes = [result for result in group if result.hidden_test.returncode == 0]
        completed = [result for result in group if result.metadata.get("status") == "success"]
        runs_with_failures = [
            result for result in group if _bench_had_failure_signal(result.metadata)
        ]
        recovered_runs = [result for result in runs_with_failures if result.success]
        variants[name] = {
            "tasks": len(group),
            "successes": len(successes),
            "pass_rate": len(successes) / len(group) if group else 0.0,
            "pass_rate_ci_95": _wilson_interval(len(successes), len(group)),
            "hidden_test_pass_rate": len(hidden_passes) / len(group) if group else 0.0,
            "hidden_test_pass_rate_ci_95": _wilson_interval(len(hidden_passes), len(group)),
            "agent_completion_rate": len(completed) / len(group) if group else 0.0,
            "agent_completion_rate_ci_95": _wilson_interval(len(completed), len(group)),
            "avg_steps": _mean(result.steps_count for result in group),
            "avg_tool_calls": _mean(result.tool_calls for result in group),
            "avg_changed_files": _mean(len(result.changed_files) for result in group),
            "avg_estimated_tokens": _mean(result.estimated_tokens for result in group),
            "total_estimated_tokens": sum(result.estimated_tokens for result in group),
            "tokens_per_success": _tokens_per_success(group),
            "estimated_cost_usd": sum(result.estimated_cost_usd for result in group),
            "cost_per_success_usd": _cost_per_success(group),
            "total_requests": sum(result.request_count for result in group),
            "avg_duration_seconds": _mean(result.duration_seconds for result in group),
            "hidden_test_passes": len(hidden_passes),
            "avg_trials": _mean(result.metadata.get("trial_count", 1) for result in group),
            "runs_with_failures": len(runs_with_failures),
            "recovered_runs": len(recovered_runs),
            "recovery_success_rate": (
                len(recovered_runs) / len(runs_with_failures) if runs_with_failures else None
            ),
        }
        stability = _repeat_stability(group)
        if stability is not None:
            variants[name]["repeat_stability"] = stability
        node_fractions = [
            result.metadata["hidden_test_nodes"]["pass_fraction"]
            for result in group
            if isinstance(result.metadata.get("hidden_test_nodes"), dict)
        ]
        if node_fractions:
            variants[name]["avg_hidden_test_node_pass_fraction"] = _mean(node_fractions)

    hidden_passes = [result for result in results if result.hidden_test.returncode == 0]
    completed = [result for result in results if result.metadata.get("status") == "success"]
    success_count = sum(1 for result in results if result.success)
    summary = {
        "total_runs": len(results),
        "overall_pass_rate": (success_count / len(results) if results else 0.0),
        "overall_pass_rate_ci_95": _wilson_interval(success_count, len(results)),
        "overall_hidden_test_pass_rate": len(hidden_passes) / len(results) if results else 0.0,
        "overall_hidden_test_pass_rate_ci_95": _wilson_interval(len(hidden_passes), len(results)),
        "overall_agent_completion_rate": len(completed) / len(results) if results else 0.0,
        "overall_agent_completion_rate_ci_95": _wilson_interval(len(completed), len(results)),
        "avg_trials": _mean(result.metadata.get("trial_count", 1) for result in results),
        "total_estimated_tokens": sum(result.estimated_tokens for result in results),
        "tokens_per_success": _tokens_per_success(results),
        "estimated_cost_usd": sum(result.estimated_cost_usd for result in results),
        "cost_per_success_usd": _cost_per_success(results),
        "variants": variants,
    }
    if tasks is not None:
        tags_by_task = {task.task_id: list(task.tags) for task in tasks}
        by_tag: dict[str, dict[str, Any]] = {}
        for result in results:
            for tag in tags_by_task.get(result.task_id, []):
                entry = by_tag.setdefault(tag, {"runs": 0, "successes": 0})
                entry["runs"] += 1
                entry["successes"] += int(result.success)
        for entry in by_tag.values():
            entry["success_rate"] = entry["successes"] / entry["runs"] if entry["runs"] else 0.0
        summary["by_tag"] = dict(sorted(by_tag.items()))
    return summary


def build_benchmark_manifest(
    *,
    suite: str,
    tasks: Sequence[BenchmarkTask],
    variants: Sequence[BenchmarkVariant],
) -> dict[str, Any]:
    task_fingerprints = {
        task.task_id: benchmark_task_fingerprint(task)
        for task in sorted(tasks, key=lambda item: item.task_id)
    }
    variant_names = sorted(variant.name for variant in variants)
    signature_payload = {
        "suite": suite,
        "task_fingerprints": task_fingerprints,
        "variant_names": variant_names,
    }
    return {
        "suite": suite,
        "task_count": len(tasks),
        "task_ids": sorted(task.task_id for task in tasks),
        "task_fingerprints": task_fingerprints,
        "variant_names": variant_names,
        "suite_signature": _stable_hash(signature_payload),
    }


def benchmark_task_fingerprint(task: BenchmarkTask) -> str:
    """Return a stable task fingerprint including hidden-test content."""

    payload = {
        "task_id": task.task_id,
        "name": task.name,
        "prompt": task.prompt,
        "setup_files": task.setup_files,
        "hidden_files": task.hidden_files,
        "visible_test_command": task.visible_test_command,
        "hidden_test_command": task.hidden_test_command,
        "max_steps": task.max_steps,
        "tags": task.tags,
        "allowed_changed_files": task.allowed_changed_files,
        "required_changed_files": task.required_changed_files,
    }
    return _stable_hash(payload)


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        f"# DM-Code-Agent {str(report.get('suite', 'coding')).title()} Benchmark Report",
        "",
        f"- Total runs: `{summary['total_runs']}`",
        f"- Overall pass rate: `{summary['overall_pass_rate']:.1%}`",
        f"- Hidden-test pass rate: `{summary['overall_hidden_test_pass_rate']:.1%}`",
        f"- Agent completion rate: `{summary['overall_agent_completion_rate']:.1%}`",
        "",
        "## Variant Summary",
        "",
        "| Variant | Strict pass (95% CI) | Hidden pass | Agent done | Avg steps | Avg tools | Avg changed | Avg tokens | Cost | Cost/success | Requests |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for name, data in summary["variants"].items():
        data = {
            "estimated_cost_usd": 0.0,
            "cost_per_success_usd": 0.0,
            "pass_rate_ci_95": None,
            **data,
        }
        lines.append(
            "| {name} | {pass_rate:.1%} ({successes}/{tasks}) {pass_ci} | "
            "{hidden_test_pass_rate:.1%} | {agent_completion_rate:.1%} | "
            "{avg_steps:.2f} | {avg_tool_calls:.2f} | {avg_changed_files:.2f} | "
            "{avg_estimated_tokens:.0f} | "
            "${estimated_cost_usd:.4f} | ${cost_per_success_usd:.4f} | "
            "{total_requests} |".format(
                name=name,
                pass_ci=_format_ci(data.get("pass_rate_ci_95")),
                **data,
            )
        )

    recovery_rows = []
    for name, data in summary["variants"].items():
        rate = data.get("recovery_success_rate")
        if data.get("runs_with_failures"):
            recovery_rows.append(
                f"| {name} | {rate:.1%} | {data.get('recovered_runs', 0)} | "
                f"{data.get('runs_with_failures', 0)} |"
            )
    if recovery_rows:
        lines.extend(
            [
                "",
                "## Recovery",
                "",
                "| Variant | Recovery success rate | Recovered | Runs with failures |",
                "| --- | ---: | ---: | ---: |",
                *recovery_rows,
            ]
        )

    by_tag = summary.get("by_tag") or {}
    if by_tag:
        lines.extend(
            [
                "",
                "## Capability by tag",
                "",
                "| Tag | Pass | Runs |",
                "| --- | ---: | ---: |",
            ]
        )
        for tag, data in by_tag.items():
            lines.append(
                f"| {tag} | {data['success_rate']:.1%} ({data['successes']}/{data['runs']}) "
                f"| {data['runs']} |"
            )

    stability_rows = []
    for name, data in summary["variants"].items():
        stability = data.get("repeat_stability")
        if stability:
            stability_rows.append(
                f"| {name} | {stability['repeats']} | {stability['pass_at_k_rate']:.1%} | "
                f"{stability['pass_pow_k_rate']:.1%} | "
                f"{stability['task_pass_rate_stddev']:.3f} |"
            )
    if stability_rows:
        lines.extend(
            [
                "",
                "## Stability (repeat variance)",
                "",
                "Repeat-variance across identical reruns (same config; API nondeterminism"
                " included). Not a controlled-seed measurement.",
                "",
                "| Variant | Repeats | pass@k | pass^k | Task pass-rate stddev |",
                "| --- | ---: | ---: | ---: | ---: |",
                *stability_rows,
            ]
        )

    lines.extend(["", "## Failed Runs", ""])
    failures = [result for result in report["results"] if not result["success"]]
    if not failures:
        lines.append("No failed runs.")
    else:
        for result in failures:
            lines.append(f"- `{result['variant']}/{result['task_id']}`: {result['failure_reason']}")

    lines.extend(
        [
            "",
            "## Run Details",
            "",
            "| Variant | Task | Pass | Hidden rc | Changed files | Trace |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for result in report["results"]:
        changed = ", ".join(f"`{path}`" for path in result.get("changed_files", [])) or "-"
        trace = result.get("metadata", {}).get("trace_path") or "-"
        if trace != "-":
            trace = f"`{trace}`"
        lines.append(
            "| {variant} | {task_id} | {success} | {hidden_rc} | {changed} | {trace} |".format(
                variant=result["variant"],
                task_id=result["task_id"],
                success="yes" if result["success"] else "no",
                hidden_rc=result.get("hidden_test", {}).get("returncode", ""),
                changed=changed,
                trace=trace,
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_trace_analysis_for_report(trace_path: Path) -> tuple[dict[str, Any], str]:
    """Load compact trace analysis for benchmark report metadata."""

    try:
        analysis = analyze_events(load_trace_events(trace_path))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    return {
        "primary_failure_stage": analysis.get("primary_failure_stage", "none"),
        "final_failure_stage": analysis.get("final_failure_stage", "none"),
        "signals": analysis.get("signals", []),
        "recovery": analysis.get("recovery", {}),
        "verification": analysis.get("verification", {}),
        "trace_health": analysis.get("trace_health", {}),
    }, ""


def _run_benchmark_task_in_workspace(
    task: BenchmarkTask,
    variant: BenchmarkVariant,
    config: BenchmarkRunConfig,
    workspace: Path,
    *,
    repeat_index: int,
    cleanup: bool,
    suite: str,
) -> CodingBenchResult:
    prepare_workspace(task, workspace)
    before_snapshot = _snapshot_workspace(workspace)
    client = _build_tracking_client(config)
    trace_path: Path | None = None
    trace_writer: TraceWriter | None = None

    if config.trace_dir:
        trace_root = Path(config.trace_dir)
        trace_root.mkdir(parents=True, exist_ok=True)
        trace_path = trace_root / f"{suite}-{variant.name}-{task.task_id}-r{repeat_index}.jsonl"
        trace_writer = TraceWriter(trace_path)
        trace_writer.record(
            "runtime",
            {
                "mode": f"{suite}_benchmark",
                "suite": suite,
                "task_id": task.task_id,
                "variant": variant.name,
                "provider": config.provider.lower(),
                "model": client.model,
                "base_url": client.base_url,
                "repeat_index": repeat_index,
            },
        )

    skill_manager = None
    if variant.enable_skills:
        skill_manager = SkillManager()
        skill_manager.load_all()

    agent = ReactAgent(
        client,
        default_tools(include_mcp=False),
        max_steps=config.max_steps or task.max_steps,
        temperature=config.temperature,
        enable_planning=variant.enable_planning,
        enable_compression=variant.enable_compression,
        skill_manager=skill_manager,
        trace_writer=trace_writer,
        enable_adaptive_replanning=config.enable_adaptive_replanning,
        max_replans=config.max_replans,
    )

    with chdir(workspace):
        try:
            if config.quiet:
                with redirect_stdout(StringIO()):
                    raw_result = agent.run(task.prompt)
            else:
                raw_result = agent.run(task.prompt)
        except Exception as exc:
            if trace_writer:
                trace_writer.record(
                    "run_error",
                    {"error_type": type(exc).__name__, "message": str(exc)},
                )
            raw_result = {
                "final_answer": "",
                "steps": [],
                "metadata": {
                    "status": "exception",
                    "failure_reason": str(exc),
                    "duration_seconds": 0.0,
                },
            }
        finally:
            if trace_writer:
                trace_writer.close()

    after_snapshot = _snapshot_workspace(workspace)
    changed_files = _diff_workspace(before_snapshot, after_snapshot)
    patch_fingerprint = _patch_fingerprint(before_snapshot, after_snapshot, changed_files)
    _write_files(workspace, task.hidden_files)
    hidden_result = run_hidden_tests(task, workspace, timeout=config.test_timeout)
    per_node_result = (
        run_hidden_tests_per_node(task, workspace, timeout=config.test_timeout)
        if config.per_test_credit
        else None
    )

    metadata = raw_result.get("metadata", {})
    metadata.update(
        {
            "mode": f"{suite}_benchmark",
            "suite": suite,
            "provider": config.provider.lower(),
            "model": client.model,
            "request_count": client.usage.request_count,
            "prompt_tokens": client.usage.prompt_tokens,
            "completion_tokens": client.usage.completion_tokens,
            "total_tokens": client.usage.total_tokens,
            "repeat_index": repeat_index,
            "changed_files": changed_files,
            "patch_fingerprint": patch_fingerprint,
            "trace_path": str(trace_path) if trace_path else "",
            "adaptive_replanning_enabled": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
            "cost_per_1k_tokens": config.cost_per_1k_tokens,
        }
    )
    if per_node_result is not None:
        metadata["hidden_test_nodes"] = per_node_result
    if trace_path:
        trace_analysis, trace_analysis_error = load_trace_analysis_for_report(trace_path)
        if trace_analysis:
            metadata["trace_analysis"] = trace_analysis
        if trace_analysis_error:
            metadata["trace_analysis_error"] = trace_analysis_error

    success, failure_reason = _score_run(task, raw_result, hidden_result, changed_files)
    steps = raw_result.get("steps", [])
    actions = [step.get("action", "") for step in steps]

    return CodingBenchResult(
        task_id=task.task_id,
        task_name=task.name,
        variant=variant.name,
        success=success,
        failure_reason=failure_reason,
        final_answer=raw_result.get("final_answer", ""),
        actions=actions,
        steps_count=len(steps),
        tool_calls=sum(1 for action in actions if action not in {"finish", "error"}),
        duration_seconds=float(metadata.get("duration_seconds", 0.0)),
        prompt_chars=client.usage.prompt_chars,
        completion_chars=client.usage.completion_chars,
        estimated_tokens=client.usage.estimated_tokens,
        estimated_cost_usd=_estimated_cost(client.usage.estimated_tokens, config),
        request_count=client.usage.request_count,
        metadata=metadata,
        hidden_test=hidden_result,
        changed_files=changed_files,
        workspace_path=str(workspace) if not cleanup else "",
    )


def _score_run(
    task: BenchmarkTask,
    raw_result: dict[str, Any],
    hidden_result: CommandResult,
    changed_files: Sequence[str],
) -> tuple[bool, str]:
    metadata = raw_result.get("metadata", {})
    if metadata.get("status") != "success":
        return False, metadata.get("failure_reason") or f"agent status={metadata.get('status')}"
    if task.allowed_changed_files:
        allowed = set(task.allowed_changed_files)
        violations = [path for path in changed_files if path not in allowed]
        if violations:
            return False, "changed files outside allowed set: " + ", ".join(violations)
    if task.required_changed_files:
        changed = set(changed_files)
        missing = [path for path in task.required_changed_files if path not in changed]
        if missing:
            return False, "required files were not changed: " + ", ".join(missing)
    if hidden_result.returncode != 0:
        detail = hidden_result.stderr or hidden_result.stdout or "hidden tests failed"
        return False, _tail(detail, limit=800)
    return True, ""


def _build_tracking_client(config: BenchmarkRunConfig) -> UsageTrackingClient:
    provider = config.provider.lower()
    env_name = config.api_key_env or PROVIDER_API_KEY_ENV.get(provider)
    if not env_name:
        raise ValueError(f"No default API key environment variable for provider: {provider}")

    api_key = os.environ.get(env_name)
    if not api_key:
        raise ValueError(f"Missing API key. Set {env_name} before running coding benchmarks.")

    defaults = PROVIDER_DEFAULTS.get(provider, {})
    client = create_llm_client(
        provider=provider,
        api_key=api_key,
        model=config.model or defaults.get("model"),
        base_url=config.base_url or defaults.get("base_url"),
        timeout=config.timeout,
    )
    return UsageTrackingClient(client)


def _validate_benchmark_config(config: BenchmarkRunConfig) -> None:
    if config.max_replans < -1:
        raise ValueError("max_replans must be -1 or greater")


def _write_files(workspace: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _snapshot_workspace(workspace: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace).as_posix()
        if not _should_track_file(relative):
            continue
        snapshot[relative] = path.read_bytes()
    return snapshot


def _diff_workspace(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    changed = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            changed.append(path)
    return changed


def _patch_fingerprint(
    before: dict[str, bytes],
    after: dict[str, bytes],
    changed_files: Sequence[str],
) -> str:
    if not changed_files:
        return ""
    payload = {}
    for path in changed_files:
        # 用 before[path] 而非 before.get(path)：条件分支已保证键存在，取值完全等价，
        # 但下标取值能让类型检查器看到值类型是 bytes 而非 bytes | None。
        payload[path] = {
            "before": (hashlib.sha256(before[path]).hexdigest() if path in before else None),
            "after": hashlib.sha256(after[path]).hexdigest() if path in after else None,
        }
    return _stable_hash(payload)


def _should_track_file(relative_path: str) -> bool:
    parts = set(Path(relative_path).parts)
    if parts & {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache"}:
        return False
    return not relative_path.endswith((".pyc", ".pyo"))


def _resolve_command(command: Sequence[str]) -> list[str]:
    return [sys.executable if part == "{python}" else part for part in command]


def _tail(text: str, *, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _mean(values: Iterable[float]) -> float:
    data = list(values)
    return statistics.fmean(data) if data else 0.0


def _estimated_cost(estimated_tokens: int, config: BenchmarkRunConfig) -> float:
    if config.cost_per_1k_tokens <= 0:
        return 0.0
    return (estimated_tokens / 1000.0) * config.cost_per_1k_tokens


def _tokens_per_success(results: Sequence[CodingBenchResult]) -> float:
    successes = sum(1 for result in results if result.success)
    if successes <= 0:
        return 0.0
    return sum(result.estimated_tokens for result in results) / successes


def _cost_per_success(results: Sequence[CodingBenchResult]) -> float:
    successes = sum(1 for result in results if result.success)
    if successes <= 0:
        return 0.0
    return sum(result.estimated_cost_usd for result in results) / successes


def _wilson_interval(successes: int, total: int, *, z: float = 1.96) -> dict[str, float]:
    if total <= 0:
        return {"low": 0.0, "high": 0.0}
    phat = successes / total
    denominator = 1 + (z * z / total)
    centre = phat + (z * z / (2 * total))
    margin = z * ((phat * (1 - phat) + (z * z / (4 * total))) / total) ** 0.5
    return {
        "low": max(0.0, (centre - margin) / denominator),
        "high": min(1.0, (centre + margin) / denominator),
    }


def _format_ci(interval: Any) -> str:
    if not isinstance(interval, dict):
        return ""
    low = float(interval.get("low", 0.0))
    high = float(interval.get("high", 0.0))
    return f"[95% CI {low:.1%}-{high:.1%}]"


def _stable_hash(payload: Any, *, length: int = 16) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:length]
