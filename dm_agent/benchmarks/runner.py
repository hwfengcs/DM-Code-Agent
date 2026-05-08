"""Runner for hidden-test coding benchmarks."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.core import CriticAgent, ReactAgent
from dm_agent.evals.real_runner import PROVIDER_API_KEY_ENV, UsageTrackingClient
from dm_agent.memory import HybridRetriever
from dm_agent.skills import SkillManager
from dm_agent.tools import default_tools
from dm_agent.tracing import TraceWriter

from .models import (
    BenchmarkRunConfig,
    BenchmarkTask,
    BenchmarkVariant,
    CodingBenchResult,
    CommandResult,
)
from .tasks import get_benchmark_tasks

BENCH_VARIANTS: List[BenchmarkVariant] = [
    BenchmarkVariant("full", True, True, True),
    BenchmarkVariant("no_planning", False, True, True),
    BenchmarkVariant("no_skills", True, False, True),
    BenchmarkVariant("no_compression", True, True, False),
]

DEFAULT_BENCH_VARIANTS: List[BenchmarkVariant] = [BENCH_VARIANTS[0]]


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
    tasks: Optional[Sequence[BenchmarkTask]] = None,
    variants: Optional[Sequence[BenchmarkVariant]] = None,
    task_ids: Optional[Iterable[str]] = None,
    variant_names: Optional[Iterable[str]] = None,
    config: Optional[BenchmarkRunConfig] = None,
) -> Dict[str, Any]:
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

    results: List[CodingBenchResult] = []
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
        "reflexion": {
            "enabled": config.enable_reflexion,
            "max_trials": config.max_trials,
        },
        "adaptive_replanning": {
            "enabled": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
        },
        "rag": {
            "enabled": config.enable_rag,
            "top_k": config.rag_top_k,
            "granularity": config.rag_granularity,
            "max_files": config.rag_max_files,
        },
        "critic": {
            "enabled": config.enable_critic,
        },
        "self_consistency": {
            "runs": config.self_consistency_runs,
            "strategy": config.self_consistency_strategy,
        },
        "token_economics": {
            "cost_per_1k_tokens": config.cost_per_1k_tokens,
        },
        "summary": summarize_benchmark_results(results),
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
    if config.self_consistency_runs > 1:
        return _run_self_consistency_benchmark_task(
            task,
            variant,
            config,
            repeat_index=repeat_index,
            suite=suite,
        )

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
        return CommandResult(
            command=resolved,
            returncode=124,
            stdout=_tail(exc.stdout or ""),
            stderr=_tail((exc.stderr or "") + f"\nCommand timed out after {timeout}s"),
            duration_seconds=time.perf_counter() - started_at,
        )


def summarize_benchmark_results(results: Sequence[CodingBenchResult]) -> Dict[str, Any]:
    by_variant: Dict[str, List[CodingBenchResult]] = {}
    for result in results:
        by_variant.setdefault(result.variant, []).append(result)

    variants: Dict[str, Any] = {}
    for name, group in by_variant.items():
        successes = [result for result in group if result.success]
        hidden_passes = [result for result in group if result.hidden_test.returncode == 0]
        completed = [result for result in group if result.metadata.get("status") == "success"]
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
        }

    hidden_passes = [result for result in results if result.hidden_test.returncode == 0]
    completed = [result for result in results if result.metadata.get("status") == "success"]
    successes = sum(1 for result in results if result.success)
    return {
        "total_runs": len(results),
        "overall_pass_rate": (successes / len(results) if results else 0.0),
        "overall_pass_rate_ci_95": _wilson_interval(successes, len(results)),
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


def write_json_report(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(report: Dict[str, Any], path: Path) -> None:
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
    trace_path: Optional[Path] = None
    trace_writer: Optional[TraceWriter] = None

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
        enable_reflexion=config.enable_reflexion,
        max_trials=config.max_trials,
        enable_adaptive_replanning=config.enable_adaptive_replanning,
        max_replans=config.max_replans,
        enable_rag=config.enable_rag,
        retriever=_build_benchmark_retriever(workspace, config) if config.enable_rag else None,
        rag_top_k=config.rag_top_k,
        critic=CriticAgent(client) if config.enable_critic else None,
    )

    with chdir(workspace):
        try:
            if config.quiet:
                with redirect_stdout(StringIO()):
                    raw_result = agent.run(task.prompt)
            else:
                raw_result = agent.run(task.prompt)
        except Exception as exc:  # noqa: BLE001
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

    changed_files = _diff_workspace(before_snapshot, _snapshot_workspace(workspace))
    _write_files(workspace, task.hidden_files)
    hidden_result = run_hidden_tests(task, workspace, timeout=config.test_timeout)

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
            "trace_path": str(trace_path) if trace_path else "",
            "reflexion_enabled": config.enable_reflexion,
            "max_trials": config.max_trials,
            "adaptive_replanning_enabled": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
            "cost_per_1k_tokens": config.cost_per_1k_tokens,
            "rag_enabled": config.enable_rag,
            "rag_top_k": config.rag_top_k,
            "critic_enabled": config.enable_critic,
            "self_consistency_runs": config.self_consistency_runs,
            "self_consistency_strategy": config.self_consistency_strategy,
        }
    )

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


def _run_self_consistency_benchmark_task(
    task: BenchmarkTask,
    variant: BenchmarkVariant,
    config: BenchmarkRunConfig,
    *,
    repeat_index: int,
    suite: str,
) -> CodingBenchResult:
    single_config = replace(config, self_consistency_runs=1)
    candidates = [
        run_benchmark_task(
            task,
            variant,
            single_config,
            repeat_index=repeat_index * config.self_consistency_runs + index,
            suite=suite,
        )
        for index in range(config.self_consistency_runs)
    ]
    selected = _select_self_consistency_candidate(candidates, config.self_consistency_strategy)
    selected_index = next(
        index for index, candidate in enumerate(candidates, start=1) if candidate is selected
    )
    metadata = dict(selected.metadata)
    metadata["self_consistency"] = {
        "runs": config.self_consistency_runs,
        "strategy": config.self_consistency_strategy,
        "selected_index": selected_index,
        "candidates": [
            {
                "run_index": index,
                "success": candidate.success,
                "failure_reason": candidate.failure_reason,
                "final_answer": candidate.final_answer,
                "estimated_tokens": candidate.estimated_tokens,
                "estimated_cost_usd": candidate.estimated_cost_usd,
                "steps_count": candidate.steps_count,
            }
            for index, candidate in enumerate(candidates, start=1)
        ],
    }

    return replace(
        selected,
        actions=[action for candidate in candidates for action in candidate.actions],
        steps_count=sum(candidate.steps_count for candidate in candidates),
        tool_calls=sum(candidate.tool_calls for candidate in candidates),
        duration_seconds=sum(candidate.duration_seconds for candidate in candidates),
        prompt_chars=sum(candidate.prompt_chars for candidate in candidates),
        completion_chars=sum(candidate.completion_chars for candidate in candidates),
        estimated_tokens=sum(candidate.estimated_tokens for candidate in candidates),
        estimated_cost_usd=sum(candidate.estimated_cost_usd for candidate in candidates),
        request_count=sum(candidate.request_count for candidate in candidates),
        metadata=metadata,
    )


def _select_self_consistency_candidate(
    candidates: Sequence[CodingBenchResult],
    strategy: str,
) -> CodingBenchResult:
    if not candidates:
        raise ValueError("self-consistency produced no candidates")
    if strategy == "test_pass":
        return max(candidates, key=lambda item: (item.success, -item.estimated_tokens))
    if strategy == "critic_score":
        return max(
            candidates,
            key=lambda item: (
                float(item.metadata.get("critic_last_score", 0.0)),
                item.success,
                -item.estimated_tokens,
            ),
        )
    if strategy == "majority_vote":
        groups: Dict[str, List[CodingBenchResult]] = {}
        for candidate in candidates:
            key = candidate.final_answer.strip()
            groups.setdefault(key, []).append(candidate)
        ranked_groups = sorted(
            groups.values(),
            key=lambda group: (
                len(group),
                sum(1 for candidate in group if candidate.success),
                -sum(candidate.estimated_tokens for candidate in group),
            ),
            reverse=True,
        )
        return max(ranked_groups[0], key=lambda item: (item.success, -item.estimated_tokens))
    raise ValueError(f"Unsupported self-consistency strategy: {strategy}")


def _score_run(
    task: BenchmarkTask,
    raw_result: Dict[str, Any],
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


def _build_benchmark_retriever(workspace: Path, config: BenchmarkRunConfig) -> HybridRetriever:
    return HybridRetriever.from_repository(
        workspace,
        granularity=config.rag_granularity,
        max_files=config.rag_max_files,
        include_tests=True,
        enable_embeddings=False,
    )


def _validate_benchmark_config(config: BenchmarkRunConfig) -> None:
    if config.max_trials < 1:
        raise ValueError("max_trials must be at least 1")
    if config.max_replans < -1:
        raise ValueError("max_replans must be -1 or greater")
    if config.rag_top_k < 1:
        raise ValueError("rag_top_k must be at least 1")
    if config.rag_max_files < 1:
        raise ValueError("rag_max_files must be at least 1")
    if config.rag_granularity not in {"symbol", "file", "both"}:
        raise ValueError("rag_granularity must be one of: symbol, file, both")
    if config.self_consistency_runs < 1:
        raise ValueError("self_consistency_runs must be at least 1")
    if config.self_consistency_strategy not in {"majority_vote", "critic_score", "test_pass"}:
        raise ValueError(
            "self_consistency_strategy must be one of: majority_vote, critic_score, test_pass"
        )
    if config.self_consistency_strategy == "critic_score" and not config.enable_critic:
        raise ValueError("critic_score self-consistency requires --enable-critic")


def _write_files(workspace: Path, files: Dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _snapshot_workspace(workspace: Path) -> Dict[str, bytes]:
    snapshot: Dict[str, bytes] = {}
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace).as_posix()
        if not _should_track_file(relative):
            continue
        snapshot[relative] = path.read_bytes()
    return snapshot


def _diff_workspace(before: Dict[str, bytes], after: Dict[str, bytes]) -> List[str]:
    changed = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            changed.append(path)
    return changed


def _should_track_file(relative_path: str) -> bool:
    parts = set(Path(relative_path).parts)
    if parts & {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache"}:
        return False
    return not relative_path.endswith((".pyc", ".pyo"))


def _resolve_command(command: Sequence[str]) -> List[str]:
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


def _wilson_interval(successes: int, total: int, *, z: float = 1.96) -> Dict[str, float]:
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
