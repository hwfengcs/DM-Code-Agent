"""Evaluation runner with ablation variants and metrics."""

from __future__ import annotations

import json
import os
import statistics
import tempfile
from contextlib import redirect_stdout
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dm_agent.core import ReactAgent
from dm_agent.skills import SkillManager
from dm_agent.tools import default_tools

from .models import EvalResult, EvalTask
from .scripted_client import ScriptedLLMClient
from .tasks import get_builtin_tasks


@dataclass(frozen=True)
class EvalVariant:
    name: str
    enable_planning: bool = True
    enable_skills: bool = True
    enable_compression: bool = True


DEFAULT_VARIANTS: List[EvalVariant] = [
    EvalVariant("full", True, True, True),
    EvalVariant("no_planning", False, True, True),
    EvalVariant("no_skills", True, False, True),
    EvalVariant("no_compression", True, True, False),
]


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_suite(
    *,
    tasks: Optional[Sequence[EvalTask]] = None,
    variants: Optional[Sequence[EvalVariant]] = None,
    task_ids: Optional[Iterable[str]] = None,
    variant_names: Optional[Iterable[str]] = None,
    cost_per_1k_tokens: float = 0.0,
) -> Dict[str, Any]:
    selected_tasks = list(tasks or get_builtin_tasks())
    selected_variants = list(variants or DEFAULT_VARIANTS)

    if task_ids:
        allowed_tasks = set(task_ids)
        selected_tasks = [task for task in selected_tasks if task.task_id in allowed_tasks]

    if variant_names:
        allowed_variants = set(variant_names)
        selected_variants = [
            variant for variant in selected_variants if variant.name in allowed_variants
        ]

    results: List[EvalResult] = []
    for variant in selected_variants:
        for task in selected_tasks:
            results.append(run_task(task, variant, cost_per_1k_tokens=cost_per_1k_tokens))

    return {
        "summary": summarize_results(results),
        "results": [result.to_dict() for result in results],
        "tasks": [task.to_public_dict() for task in selected_tasks],
        "variants": [variant.__dict__ for variant in selected_variants],
    }


def run_task(
    task: EvalTask,
    variant: EvalVariant,
    *,
    cost_per_1k_tokens: float = 0.0,
) -> EvalResult:
    responses = _script_for(task, variant)
    client = ScriptedLLMClient(responses)

    with tempfile.TemporaryDirectory(prefix=f"dm-agent-eval-{task.task_id}-") as tmp:
        workspace = Path(tmp)
        _write_setup_files(workspace, task.setup_files)

        skill_manager = None
        if variant.enable_skills:
            skill_manager = SkillManager()
            skill_manager.load_all()

        agent = ReactAgent(
            client,
            default_tools(include_mcp=False),
            max_steps=task.max_steps,
            enable_planning=variant.enable_planning,
            enable_compression=variant.enable_compression,
            skill_manager=skill_manager,
        )

        with chdir(workspace):
            try:
                with redirect_stdout(StringIO()):
                    raw_result = agent.run(task.prompt)
            except Exception as exc:  # noqa: BLE001
                raw_result = {
                    "final_answer": "",
                    "steps": [],
                    "metadata": {
                        "status": "exception",
                        "failure_reason": str(exc),
                        "duration_seconds": 0.0,
                    },
                }

        success, failure_reason = _validate(task, raw_result, workspace)

    steps = raw_result.get("steps", [])
    actions = [step.get("action", "") for step in steps]
    metadata = raw_result.get("metadata", {})
    estimated_cost = client.usage.estimated_tokens / 1000 * cost_per_1k_tokens

    return EvalResult(
        task_id=task.task_id,
        task_name=task.name,
        variant=variant.name,
        success=success,
        final_answer=raw_result.get("final_answer", ""),
        failure_reason=failure_reason,
        actions=actions,
        steps_count=len(steps),
        tool_calls=sum(1 for action in actions if action not in {"finish", "error"}),
        duration_seconds=float(metadata.get("duration_seconds", 0.0)),
        prompt_chars=client.usage.prompt_chars,
        completion_chars=client.usage.completion_chars,
        estimated_tokens=client.usage.estimated_tokens,
        estimated_cost_usd=estimated_cost,
        metadata=metadata,
    )


def summarize_results(results: Sequence[EvalResult]) -> Dict[str, Any]:
    by_variant: Dict[str, List[EvalResult]] = {}
    for result in results:
        by_variant.setdefault(result.variant, []).append(result)

    variants = {}
    for name, group in by_variant.items():
        successes = [result for result in group if result.success]
        variants[name] = {
            "tasks": len(group),
            "successes": len(successes),
            "success_rate": len(successes) / len(group) if group else 0.0,
            "avg_steps": _mean(result.steps_count for result in group),
            "avg_tool_calls": _mean(result.tool_calls for result in group),
            "avg_estimated_tokens": _mean(result.estimated_tokens for result in group),
            "total_estimated_cost_usd": sum(result.estimated_cost_usd for result in group),
            "recovery_events": sum(
                int(result.metadata.get("parse_repair_count", 0))
                + int(result.metadata.get("parse_error_count", 0))
                + int(result.metadata.get("unknown_tool_count", 0))
                + int(result.metadata.get("argument_error_count", 0))
                + int(result.metadata.get("replan_count", 0))
                for result in group
            ),
            "activated_skill_runs": sum(
                1 for result in group if result.metadata.get("activated_skills")
            ),
        }

    return {
        "total_runs": len(results),
        "overall_success_rate": (
            sum(1 for result in results if result.success) / len(results) if results else 0.0
        ),
        "variants": variants,
    }


def write_json_report(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# DM-Code-Agent Eval Report",
        "",
        f"- Total runs: `{summary['total_runs']}`",
        f"- Overall success rate: `{summary['overall_success_rate']:.1%}`",
        "",
        "## Ablation Summary",
        "",
        "| Variant | Success | Avg steps | Avg tools | Avg tokens | Recovery events | Skill runs |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for name, data in summary["variants"].items():
        lines.append(
            "| {name} | {success_rate:.1%} ({successes}/{tasks}) | {avg_steps:.2f} | "
            "{avg_tool_calls:.2f} | {avg_estimated_tokens:.0f} | {recovery_events} | "
            "{activated_skill_runs} |".format(name=name, **data)
        )

    lines.extend(["", "## Failed Runs", ""])
    failures = [result for result in report["results"] if not result["success"]]
    if not failures:
        lines.append("No failed runs.")
    else:
        for result in failures:
            lines.append(f"- `{result['variant']}/{result['task_id']}`: {result['failure_reason']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _script_for(task: EvalTask, variant: EvalVariant) -> List[str]:
    responses: List[str] = []
    if variant.enable_planning and task.planner_response:
        responses.append(task.planner_response)
    if variant.enable_planning and task.replan_response:
        responses.extend(task.agent_responses[:1])
        responses.append(task.replan_response)
        responses.extend(task.agent_responses[1:])
    else:
        responses.extend(task.agent_responses)
    return responses


def _write_setup_files(workspace: Path, files: Dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _validate(task: EvalTask, raw_result: Dict[str, Any], workspace: Path) -> tuple[bool, str]:
    metadata = raw_result.get("metadata", {})
    if metadata.get("status") != "success":
        return False, metadata.get("failure_reason") or f"status={metadata.get('status')}"

    final_answer = raw_result.get("final_answer", "").lower()
    for keyword in task.expected.final_answer_contains:
        if keyword.lower() not in final_answer:
            return False, f"final answer missing keyword: {keyword}"
    for keyword_group in task.expected.final_answer_contains_any:
        if not any(keyword.lower() in final_answer for keyword in keyword_group):
            return False, f"final answer missing one of keywords: {keyword_group}"

    actions = [step.get("action", "") for step in raw_result.get("steps", [])]
    for action in task.expected.required_actions:
        if action not in actions:
            return False, f"required action not used: {action}"

    for relative_path, expected_content in task.expected.workspace_files.items():
        path = workspace / relative_path
        if not path.exists():
            return False, f"expected file missing: {relative_path}"
        if expected_content not in path.read_text(encoding="utf-8"):
            return False, f"expected content missing in: {relative_path}"

    for key, minimum in task.expected.metadata_min.items():
        value = int(metadata.get(key, 0))
        if value < minimum:
            return False, f"metadata {key} expected >= {minimum}, got {value}"

    return True, ""


def _mean(values: Iterable[float]) -> float:
    data = list(values)
    return statistics.fmean(data) if data else 0.0
