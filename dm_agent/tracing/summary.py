"""Deterministic trace summaries and behavioral diffs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = _first(events, "runtime")
    run_start = _first(events, "run_start")
    run_end = _last(events, "run_end")
    steps = [event["payload"] for event in events if event.get("event") == "step"]
    plan = _first(events, "plan")
    metadata = run_end.get("payload", {}).get("metadata", {}) if run_end else {}
    runtime_payload = runtime.get("payload", {}) if runtime else {}
    return {
        "run_id": events[0].get("run_id") if events else "",
        "schema_version": (run_start or {}).get("payload", {}).get("schema_version"),
        "task": (run_start or {}).get("payload", {}).get("task", ""),
        "status": (run_end or {}).get("payload", {}).get("status", ""),
        "final_answer": (run_end or {}).get("payload", {}).get("final_answer", ""),
        "duration_seconds": (run_end or {}).get("payload", {}).get("duration_seconds"),
        "provider": runtime_payload.get("provider") or metadata.get("provider"),
        "model": runtime_payload.get("model") or metadata.get("model"),
        "base_url": runtime_payload.get("base_url") or metadata.get("base_url"),
        "event_count": len(events),
        "step_count": len(steps),
        "tool_call_count": sum(1 for event in events if event.get("event") == "tool_call"),
        "replan_count": sum(1 for event in events if event.get("event") == "replan"),
        "plan_steps": (plan or {}).get("payload", {}).get("steps", []),
        "steps": steps,
    }


def diff_events(
    base_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a deterministic behavioral diff between two trace event lists."""

    base = summarize_events(base_events)
    candidate = summarize_events(candidate_events)
    base_actions = _action_sequence(base)
    candidate_actions = _action_sequence(candidate)
    base_plan_actions = _plan_actions(base)
    candidate_plan_actions = _plan_actions(candidate)
    base_usage = _count_actions(base_actions)
    candidate_usage = _count_actions(candidate_actions)

    return {
        "base": _trace_header(base),
        "candidate": _trace_header(candidate),
        "status_changed": base.get("status") != candidate.get("status"),
        "task_changed": base.get("task") != candidate.get("task"),
        "final_answer_changed": base.get("final_answer") != candidate.get("final_answer"),
        "plan_changed": base_plan_actions != candidate_plan_actions,
        "metrics": {
            "step_count": _metric_delta(base, candidate, "step_count"),
            "tool_call_count": _metric_delta(base, candidate, "tool_call_count"),
            "replan_count": _metric_delta(base, candidate, "replan_count"),
            "duration_seconds": _float_metric_delta(base, candidate, "duration_seconds"),
        },
        "action_sequence": {
            "base": base_actions,
            "candidate": candidate_actions,
            "common_prefix": _common_prefix_length(base_actions, candidate_actions),
            "changes": _sequence_changes(base_actions, candidate_actions),
        },
        "tool_usage": {
            "base": base_usage,
            "candidate": candidate_usage,
            "delta": _count_delta(base_usage, candidate_usage),
        },
        "plan": {
            "base": base_plan_actions,
            "candidate": candidate_plan_actions,
        },
    }


def _first(events: Sequence[dict[str, Any]], event_name: str) -> dict[str, Any] | None:
    for event in events:
        if event.get("event") == event_name:
            return event
    return None


def _last(events: Sequence[dict[str, Any]], event_name: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event") == event_name:
            return event
    return None


def _trace_header(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": summary.get("run_id", ""),
        "task": summary.get("task", ""),
        "status": summary.get("status", ""),
        "provider": summary.get("provider", ""),
        "model": summary.get("model", ""),
        "step_count": summary.get("step_count", 0),
        "tool_call_count": summary.get("tool_call_count", 0),
        "replan_count": summary.get("replan_count", 0),
        "duration_seconds": summary.get("duration_seconds"),
    }


def _action_sequence(summary: dict[str, Any]) -> list[str]:
    return [str(step.get("action", "")) for step in summary.get("steps", [])]


def _plan_actions(summary: dict[str, Any]) -> list[str]:
    return [str(step.get("action", "")) for step in summary.get("plan_steps", [])]


def _metric_delta(
    base: dict[str, Any],
    candidate: dict[str, Any],
    key: str,
) -> dict[str, int]:
    base_value = int(base.get(key) or 0)
    candidate_value = int(candidate.get(key) or 0)
    return {
        "base": base_value,
        "candidate": candidate_value,
        "delta": candidate_value - base_value,
    }


def _float_metric_delta(
    base: dict[str, Any],
    candidate: dict[str, Any],
    key: str,
) -> dict[str, float | None]:
    base_value = base.get(key)
    candidate_value = candidate.get(key)
    delta = None
    if base_value is not None and candidate_value is not None:
        delta = float(candidate_value) - float(base_value)
    return {
        "base": float(base_value) if base_value is not None else None,
        "candidate": float(candidate_value) if candidate_value is not None else None,
        "delta": delta,
    }


def _common_prefix_length(base: Sequence[str], candidate: Sequence[str]) -> int:
    count = 0
    for left, right in zip(base, candidate, strict=False):
        if left != right:
            break
        count += 1
    return count


def _sequence_changes(base: Sequence[str], candidate: Sequence[str]) -> list[dict[str, str | int]]:
    changes: list[dict[str, str | int]] = []
    max_length = max(len(base), len(candidate))
    for index in range(max_length):
        base_action = base[index] if index < len(base) else ""
        candidate_action = candidate[index] if index < len(candidate) else ""
        if base_action == candidate_action:
            continue
        changes.append(
            {
                "step_number": index + 1,
                "base": base_action,
                "candidate": candidate_action,
            }
        )
    return changes


def _count_actions(actions: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        if not action:
            continue
        counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def _count_delta(
    base: dict[str, int],
    candidate: dict[str, int],
) -> dict[str, dict[str, int]]:
    delta: dict[str, dict[str, int]] = {}
    for action in sorted(set(base) | set(candidate)):
        base_count = base.get(action, 0)
        candidate_count = candidate.get(action, 0)
        if base_count == candidate_count:
            continue
        delta[action] = {
            "base": base_count,
            "candidate": candidate_count,
            "delta": candidate_count - base_count,
        }
    return delta
