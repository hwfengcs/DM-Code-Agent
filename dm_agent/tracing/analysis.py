"""Deterministic advisory analysis for trace files and trace directories."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .summary import _first, _last, summarize_events
from .writer import load_trace_events

VERIFICATION_TOOLS = {"run_python", "run_tests", "run_linter"}


def _hallucination_signals(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic hallucination proxies from one trace (advisory only).

    These deliberately stay OUT of the trace-health score until calibrated
    against outcomes; they are surfaced for audit and aggregation.
    """
    read_paths: set = set()
    edit_without_read = 0
    missing_path_references = 0
    tool_call_count = 0
    truncation_hits = 0
    edit_guard_blocks = 0
    for event in events:
        name = event.get("event")
        if name == "observation_truncated":
            truncation_hits += 1
            continue
        if name == "edit_guard":
            edit_guard_blocks += 1
            continue
        if name != "tool_call":
            continue
        tool_call_count += 1
        payload = event.get("payload", {})
        action = str(payload.get("action", ""))
        action_input = payload.get("action_input")
        path = ""
        if isinstance(action_input, dict):
            path_value = action_input.get("path")
            if isinstance(path_value, str):
                path = path_value
        observation = str(payload.get("observation", "")).strip()
        if observation.startswith(("文件 ", "路径 ")) and observation.endswith(
            ("不存在。", "不是文件。")
        ):
            missing_path_references += 1
        if action in {"read_file", "search_in_file"} and path:
            read_paths.add(path)
        elif action == "edit_file" and path and path not in read_paths:
            edit_without_read += 1
    return {
        "edit_without_read_count": edit_without_read,
        "edit_guard_blocks": edit_guard_blocks,
        "truncation_hits": truncation_hits,
        "truncation_hit_rate": (truncation_hits / tool_call_count) if tool_call_count else 0.0,
        "missing_path_reference_count": missing_path_references,
    }


def analyze_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a deterministic advisory analysis for one trace."""

    summary = summarize_events(events)
    run_start = _first(events, "run_start")
    run_end = _last(events, "run_end")
    metadata = run_end.get("payload", {}).get("metadata", {}) if run_end else {}
    failures = _failure_events(events, summary)
    primary_failure = failures[0] if failures else {}
    primary_stage = str(primary_failure.get("stage") or "none")
    final_stage = _final_failure_stage(summary, primary_stage)
    replan_indices = [index for index, event in enumerate(events) if event.get("event") == "replan"]
    first_failure_index = primary_failure.get("event_index")
    replanned_after_failure = first_failure_index is not None and any(
        index > first_failure_index for index in replan_indices
    )
    recovered = bool(failures and summary.get("status") == "success")
    verification = _verification_analysis(summary)
    signals = _analysis_signals(
        primary_stage=primary_stage,
        final_stage=final_stage,
        verification_gap=verification["gap"],
        replanned_after_failure=replanned_after_failure,
        failure_count=len(failures),
    )
    health = _trace_health(
        has_run_start=run_start is not None,
        has_run_end=run_end is not None,
        final_stage=final_stage,
        verification_gap=verification["gap"],
        failure_count=len(failures),
        replanned_after_failure=replanned_after_failure,
        metadata=metadata,
    )

    return {
        "run_id": summary.get("run_id", ""),
        "task": summary.get("task", ""),
        "status": summary.get("status", ""),
        "primary_failure_stage": primary_stage,
        "final_failure_stage": final_stage,
        "signals": signals,
        "recovery": {
            "failure_event_count": len(failures),
            "first_failure_step": primary_failure.get("step_number"),
            "first_failure_event": primary_failure.get("event"),
            "replan_count": summary.get("replan_count", 0),
            "replanned_after_failure": replanned_after_failure,
            "recovered": recovered,
        },
        "verification": verification,
        "hallucination_signals": _hallucination_signals(events),
        "metadata_counters": {
            key: metadata.get(key, 0)
            for key in (
                "parse_error_count",
                "parse_repair_count",
                "tool_error_count",
                "unknown_tool_count",
                "argument_error_count",
                "critic_reject_count",
                "replan_count",
            )
            if key in metadata
        },
        "trace_health": health,
    }


def analyze_trace_directory(directory: Path, *, pattern: str = "*.jsonl") -> dict[str, Any]:
    """Analyze a directory of trace JSONL files without replaying tools."""

    paths = sorted(path for path in directory.glob(pattern) if path.is_file())
    analyses = []
    errors = []
    for path in paths:
        try:
            analysis = analyze_events(load_trace_events(path))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        analyses.append({"path": str(path), "analysis": analysis})

    return {
        "mode": "trace_directory_analysis",
        "directory": str(directory),
        "pattern": pattern,
        "summary": _trace_directory_summary(paths, analyses, errors),
        "analyses": analyses,
        "errors": errors,
    }


def _failure_events(
    events: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        name = event.get("event")
        payload = event.get("payload", {})
        if name == "parse_error":
            failures.append(_failure_item(index, name, "parse", payload))
        elif name == "llm_error":
            failures.append(_failure_item(index, name, "llm", payload))
        elif name == "critic_review" and not payload.get("passed", True):
            failures.append(_failure_item(index, name, "critic", payload))
        elif name == "tool_call" and payload.get("failed"):
            failures.append(_failure_item(index, name, _classify_tool_failure(payload), payload))

    status = str(summary.get("status") or "")
    if status == "max_steps_exceeded" and not failures:
        failures.append(
            {
                "event_index": len(events),
                "event": "run_end",
                "stage": "max_steps",
                "step_number": None,
                "action": "",
            }
        )
    return failures


def _failure_item(
    index: int,
    event: str,
    stage: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_index": index,
        "event": event,
        "stage": stage,
        "step_number": payload.get("step_number"),
        "action": payload.get("action", ""),
    }


def _classify_tool_failure(payload: dict[str, Any]) -> str:
    action = str(payload.get("action") or "")
    observation = str(payload.get("observation") or "")
    lowered = observation.lower()
    if action in {"run_tests", "run_linter"}:
        return "verification"
    if "returncode: 1" in lowered or "pytest" in lowered or "assertionerror" in lowered:
        return "verification"
    if "unknown tool" in lowered:
        return "tool_selection"
    if "tool arguments" in lowered:
        return "tool_arguments"
    if "critic rejected" in lowered or "critic review failed" in lowered:
        return "critic"
    if "tool execution failed" in lowered:
        return "tool_execution"
    return "tool"


def _final_failure_stage(summary: dict[str, Any], primary_stage: str) -> str:
    status = str(summary.get("status") or "")
    if status == "success":
        return "none"
    if status == "max_steps_exceeded":
        return "max_steps"
    if primary_stage != "none":
        return primary_stage
    return status or "unknown"


def _verification_analysis(summary: dict[str, Any]) -> dict[str, Any]:
    steps = summary.get("steps", [])
    finish_steps = [
        int(step.get("step_number") or index + 1)
        for index, step in enumerate(steps)
        if step.get("action") in {"finish", "task_complete"}
    ]
    finish_step = min(finish_steps) if finish_steps else None
    actions = [
        {
            "step_number": int(step.get("step_number") or index + 1),
            "action": step.get("action"),
        }
        for index, step in enumerate(steps)
        if step.get("action") in VERIFICATION_TOOLS
    ]
    before_finish = bool(
        actions
        and (
            finish_step is None
            or any(int(action["step_number"]) < finish_step for action in actions)
        )
    )
    status = summary.get("status")
    return {
        "actions": actions,
        "count": len(actions),
        "finish_step": finish_step,
        "before_finish": before_finish,
        "gap": status == "success" and not before_finish,
    }


def _analysis_signals(
    *,
    primary_stage: str,
    final_stage: str,
    verification_gap: bool,
    replanned_after_failure: bool,
    failure_count: int,
) -> list[str]:
    signals = []
    if primary_stage != "none":
        signals.append(f"primary_failure:{primary_stage}")
    if final_stage != "none":
        signals.append(f"final_failure:{final_stage}")
    if verification_gap:
        signals.append("verification_gap")
    if failure_count and replanned_after_failure:
        signals.append("replanned_after_failure")
    elif failure_count:
        signals.append("no_replan_after_failure")
    return signals


def _trace_health(
    *,
    has_run_start: bool,
    has_run_end: bool,
    final_stage: str,
    verification_gap: bool,
    failure_count: int,
    replanned_after_failure: bool,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    score = 1.0
    issues = []
    if not has_run_start:
        score -= 0.2
        issues.append("missing_run_start")
    if not has_run_end:
        score -= 0.4
        issues.append("missing_run_end")
    if final_stage != "none":
        score -= 0.3
        issues.append(f"final_failure:{final_stage}")
    if verification_gap:
        score -= 0.2
        issues.append("verification_gap")
    if failure_count and not replanned_after_failure:
        score -= 0.15
        issues.append("failure_without_replan")
    if int(metadata.get("parse_error_count") or 0) > 0 and final_stage != "none":
        score -= 0.05
        issues.append("unrecovered_parse_errors")
    if int(metadata.get("tool_error_count") or 0) > 0 and final_stage != "none":
        score -= 0.05
        issues.append("unrecovered_tool_errors")

    score = max(0.0, min(1.0, round(score, 2)))
    if score >= 0.85:
        grade = "good"
    elif score >= 0.65:
        grade = "warning"
    else:
        grade = "risky"
    return {"score": score, "grade": grade, "issues": issues}


def _trace_directory_summary(
    paths: Sequence[Path],
    analyses: Sequence[dict[str, Any]],
    errors: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    analysis_payloads = [item["analysis"] for item in analyses]
    runs_with_failures = [
        analysis
        for analysis in analysis_payloads
        if analysis.get("recovery", {}).get("failure_event_count", 0)
    ]
    recovered_runs = [
        analysis for analysis in runs_with_failures if analysis.get("recovery", {}).get("recovered")
    ]
    return {
        "total_files": len(paths),
        "analyzed_traces": len(analyses),
        "error_count": len(errors),
        "verification_gap_count": sum(
            1 for analysis in analysis_payloads if analysis.get("verification", {}).get("gap")
        ),
        "runs_with_failures": len(runs_with_failures),
        "recovered_runs": len(recovered_runs),
        "recovery_success_rate": (
            len(recovered_runs) / len(runs_with_failures) if runs_with_failures else None
        ),
        "hallucination_signals": {
            "edit_without_read_count": sum(
                int(a.get("hallucination_signals", {}).get("edit_without_read_count", 0))
                for a in analysis_payloads
            ),
            "edit_guard_blocks": sum(
                int(a.get("hallucination_signals", {}).get("edit_guard_blocks", 0))
                for a in analysis_payloads
            ),
            "truncation_hits": sum(
                int(a.get("hallucination_signals", {}).get("truncation_hits", 0))
                for a in analysis_payloads
            ),
            "missing_path_reference_count": sum(
                int(a.get("hallucination_signals", {}).get("missing_path_reference_count", 0))
                for a in analysis_payloads
            ),
        },
        "trace_health_counts": _count_values(
            analysis.get("trace_health", {}).get("grade", "unknown")
            for analysis in analysis_payloads
        ),
        "primary_failure_stage_counts": _count_values(
            analysis.get("primary_failure_stage", "none") for analysis in analysis_payloads
        ),
        "final_failure_stage_counts": _count_values(
            analysis.get("final_failure_stage", "none") for analysis in analysis_payloads
        ),
    }


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
