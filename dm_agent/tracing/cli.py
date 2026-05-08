"""Command-line tools for viewing and replaying DM-Code-Agent traces."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from dm_agent.tools import default_tools

from .writer import load_trace_events

EXECUTION_TOOLS = {"run_python", "run_shell", "run_tests", "run_linter"}
VERIFICATION_TOOLS = {"run_python", "run_tests", "run_linter"}


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or replay DM-Code-Agent JSONL traces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    view_parser = subparsers.add_parser("view", help="Print a human-readable trace summary.")
    view_parser.add_argument("trace", type=Path, help="Path to a JSONL trace file.")
    view_parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    view_parser.add_argument("--raw", action="store_true", help="Print raw trace events.")

    replay_parser = subparsers.add_parser("replay", help="Replay a trace timeline.")
    replay_parser.add_argument("trace", type=Path, help="Path to a JSONL trace file.")
    replay_parser.add_argument(
        "--execute-tools",
        action="store_true",
        help=("Re-execute recorded tool calls in the selected workspace. This can modify files."),
    )
    replay_parser.add_argument(
        "--allow-shell",
        action="store_true",
        help="Allow run_python/run_shell/run_tests/run_linter during --execute-tools replay.",
    )
    replay_parser.add_argument(
        "--workspace",
        type=Path,
        help="Workspace for tool replay. Defaults to the current directory.",
    )
    replay_parser.add_argument("--json", action="store_true", help="Print replay result as JSON.")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze failure stage, recovery, and verification gaps in one trace.",
    )
    analyze_parser.add_argument("trace", type=Path, help="Path to a JSONL trace file.")
    analyze_parser.add_argument("--json", action="store_true", help="Print analysis as JSON.")

    diff_parser = subparsers.add_parser("diff", help="Compare two trace timelines.")
    diff_parser.add_argument("base_trace", type=Path, help="Baseline JSONL trace file.")
    diff_parser.add_argument("candidate_trace", type=Path, help="Candidate JSONL trace file.")
    diff_parser.add_argument("--json", action="store_true", help="Print diff result as JSON.")
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)

    if args.command == "view":
        events = _load_trace_for_cli(args.trace)
        if events is None:
            return 2
        return _view(events, as_json=args.json, raw=args.raw)
    if args.command == "replay":
        events = _load_trace_for_cli(args.trace)
        if events is None:
            return 2
        return _replay(
            events,
            execute_tools=args.execute_tools,
            allow_shell=args.allow_shell,
            workspace=args.workspace,
            as_json=args.json,
        )
    if args.command == "analyze":
        events = _load_trace_for_cli(args.trace)
        if events is None:
            return 2
        return _analyze(events, as_json=args.json)
    if args.command == "diff":
        base_events = _load_trace_for_cli(args.base_trace)
        candidate_events = _load_trace_for_cli(args.candidate_trace)
        if base_events is None or candidate_events is None:
            return 2
        return _diff(base_events, candidate_events, as_json=args.json)
    return 2


def _view(events: List[Dict[str, Any]], *, as_json: bool, raw: bool) -> int:
    if raw:
        print(json.dumps(events, indent=2, ensure_ascii=False))
        return 0

    summary = summarize_events(events)
    if as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print(f"Trace run: {summary.get('run_id', '<unknown>')}")
    print(f"Task: {summary.get('task', '')}")
    print(f"Status: {summary.get('status', '<unknown>')}")
    if summary.get("provider"):
        print(f"Provider: {summary['provider']}")
    if summary.get("model"):
        print(f"Model: {summary['model']}")
    print(f"Events: {summary['event_count']}")
    print(f"Steps: {summary['step_count']}")
    print()

    for step in summary["steps"]:
        action = step.get("action", "")
        observation = _shorten(str(step.get("observation", "")), 140)
        print(f"{step.get('step_number')}. {action} -> {observation}")

    final_answer = summary.get("final_answer", "")
    if final_answer:
        print()
        print(f"Final: {_shorten(final_answer, 280)}")
    return 0


def _replay(
    events: List[Dict[str, Any]],
    *,
    execute_tools: bool,
    allow_shell: bool,
    workspace: Path | None,
    as_json: bool,
) -> int:
    summary = summarize_events(events)
    result: Dict[str, Any] = {
        "run_id": summary.get("run_id"),
        "task": summary.get("task"),
        "mode": "tool" if execute_tools else "dry",
        "status": "ok",
        "events_replayed": len(events),
        "steps_replayed": summary.get("step_count", 0),
        "tool_replay": [],
        "mismatch_count": 0,
    }

    if execute_tools:
        replay_workspace = workspace or Path.cwd()
        tool_results = replay_tools(events, replay_workspace, allow_shell=allow_shell)
        result["tool_replay"] = tool_results
        result["mismatch_count"] = sum(1 for item in tool_results if not item["matches"])
        if any(item["status"] == "blocked" for item in tool_results):
            result["status"] = "blocked"
        elif result["mismatch_count"]:
            result["status"] = "mismatch"

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Replay mode: {result['mode']}")
        print(f"Task: {result.get('task', '')}")
        print(f"Steps replayed: {result['steps_replayed']}")
        if execute_tools:
            print(f"Tool calls replayed: {len(result['tool_replay'])}")
            print(f"Mismatches: {result['mismatch_count']}")
            for item in result["tool_replay"]:
                marker = "OK" if item["matches"] else item["status"].upper()
                print(f"- {marker} {item['action']} step={item['step_number']}")

    return 0 if result["status"] == "ok" else 1


def _analyze(
    events: List[Dict[str, Any]],
    *,
    as_json: bool,
) -> int:
    analysis = analyze_events(events)
    if as_json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        return 0

    recovery = analysis["recovery"]
    verification = analysis["verification"]
    health = analysis["trace_health"]
    print("Trace analysis")
    print(f"Task: {analysis.get('task', '')}")
    print(f"Status: {analysis.get('status', '')}")
    print(f"Primary failure stage: {analysis['primary_failure_stage']}")
    print(f"Final failure stage: {analysis['final_failure_stage']}")
    print(
        "Recovery: "
        f"failures={recovery['failure_event_count']}, "
        f"replans={recovery['replan_count']}, "
        f"replanned_after_failure={str(recovery['replanned_after_failure']).lower()}, "
        f"recovered={str(recovery['recovered']).lower()}"
    )
    print(
        "Verification: "
        f"actions={verification['count']}, "
        f"before_finish={str(verification['before_finish']).lower()}, "
        f"gap={str(verification['gap']).lower()}"
    )
    print(f"Health: {health['grade']} ({health['score']:.2f})")
    if health["issues"]:
        print("Issues:")
        for issue in health["issues"]:
            print(f"- {issue}")
    return 0


def _diff(
    base_events: List[Dict[str, Any]],
    candidate_events: List[Dict[str, Any]],
    *,
    as_json: bool,
) -> int:
    diff = diff_events(base_events, candidate_events)
    if as_json:
        print(json.dumps(diff, indent=2, ensure_ascii=False))
        return 0

    base = diff["base"]
    candidate = diff["candidate"]
    metrics = diff["metrics"]
    print("Trace diff")
    print(f"Base: {base.get('task', '')}")
    print(f"Candidate: {candidate.get('task', '')}")
    print(f"Status: {base.get('status', '')} -> {candidate.get('status', '')}")
    print(
        "Steps: "
        f"{metrics['step_count']['base']} -> {metrics['step_count']['candidate']} "
        f"({_signed(metrics['step_count']['delta'])})"
    )
    print(
        "Tool calls: "
        f"{metrics['tool_call_count']['base']} -> {metrics['tool_call_count']['candidate']} "
        f"({_signed(metrics['tool_call_count']['delta'])})"
    )
    print(
        "Replans: "
        f"{metrics['replan_count']['base']} -> {metrics['replan_count']['candidate']} "
        f"({_signed(metrics['replan_count']['delta'])})"
    )
    print()
    print(f"Action common prefix: {diff['action_sequence']['common_prefix']}")
    if diff["action_sequence"]["changes"]:
        print("Action changes:")
        for change in diff["action_sequence"]["changes"]:
            print(
                "- Step {index}: {base} -> {candidate}".format(
                    index=change["step_number"],
                    base=change.get("base") or "<missing>",
                    candidate=change.get("candidate") or "<missing>",
                )
            )
    else:
        print("Action changes: none")

    usage_delta = diff["tool_usage"]["delta"]
    if usage_delta:
        print()
        print("Tool usage delta:")
        for action, data in usage_delta.items():
            print(
                "- {action}: {base} -> {candidate} ({delta})".format(
                    action=action,
                    base=data["base"],
                    candidate=data["candidate"],
                    delta=_signed(data["delta"]),
                )
            )
    print()
    print(f"Plan changed: {'yes' if diff['plan_changed'] else 'no'}")
    print(f"Final answer changed: {'yes' if diff['final_answer_changed'] else 'no'}")
    return 0


def summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    base_events: List[Dict[str, Any]],
    candidate_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
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


def analyze_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def replay_tools(
    events: Iterable[Dict[str, Any]],
    workspace: Path,
    *,
    allow_shell: bool = False,
) -> List[Dict[str, Any]]:
    tools = {tool.name: tool for tool in default_tools(include_mcp=False)}
    results: List[Dict[str, Any]] = []

    for event in events:
        if event.get("event") != "tool_call":
            continue
        payload = event.get("payload", {})
        action = payload.get("action", "")
        if action in {"finish", "error"}:
            continue

        item: Dict[str, Any] = {
            "step_number": payload.get("step_number"),
            "action": action,
            "status": "ok",
            "matches": False,
            "expected_observation": payload.get("observation", ""),
            "actual_observation": "",
        }

        tool = tools.get(action)
        if tool is None:
            item["status"] = "unknown_tool"
            results.append(item)
            continue
        if action in EXECUTION_TOOLS and not allow_shell:
            item["status"] = "blocked"
            item["actual_observation"] = "Execution tools require --allow-shell."
            results.append(item)
            continue
        try:
            with chdir(workspace):
                actual = tool.execute(payload.get("action_input") or {})
        except Exception as exc:  # noqa: BLE001
            actual = f"Tool execution failed: {exc}"
            item["status"] = "error"

        item["actual_observation"] = actual
        item["matches"] = actual == item["expected_observation"]
        if item["status"] == "ok" and not item["matches"]:
            item["status"] = "mismatch"
        results.append(item)

    return results


def _load_trace_for_cli(path: Path) -> List[Dict[str, Any]] | None:
    try:
        return load_trace_events(path)
    except FileNotFoundError:
        print(f"Trace not found: {path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"Invalid trace JSONL: {exc}", file=sys.stderr)
        return None


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _first(events: Sequence[Dict[str, Any]], event_name: str) -> Dict[str, Any] | None:
    for event in events:
        if event.get("event") == event_name:
            return event
    return None


def _last(events: Sequence[Dict[str, Any]], event_name: str) -> Dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event") == event_name:
            return event
    return None


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _trace_header(summary: Dict[str, Any]) -> Dict[str, Any]:
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


def _action_sequence(summary: Dict[str, Any]) -> List[str]:
    return [str(step.get("action", "")) for step in summary.get("steps", [])]


def _plan_actions(summary: Dict[str, Any]) -> List[str]:
    return [str(step.get("action", "")) for step in summary.get("plan_steps", [])]


def _metric_delta(
    base: Dict[str, Any],
    candidate: Dict[str, Any],
    key: str,
) -> Dict[str, int]:
    base_value = int(base.get(key) or 0)
    candidate_value = int(candidate.get(key) or 0)
    return {
        "base": base_value,
        "candidate": candidate_value,
        "delta": candidate_value - base_value,
    }


def _float_metric_delta(
    base: Dict[str, Any],
    candidate: Dict[str, Any],
    key: str,
) -> Dict[str, float | None]:
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
    for left, right in zip(base, candidate):
        if left != right:
            break
        count += 1
    return count


def _sequence_changes(base: Sequence[str], candidate: Sequence[str]) -> List[Dict[str, str | int]]:
    changes: List[Dict[str, str | int]] = []
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


def _count_actions(actions: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for action in actions:
        if not action:
            continue
        counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def _count_delta(
    base: Dict[str, int],
    candidate: Dict[str, int],
) -> Dict[str, Dict[str, int]]:
    delta: Dict[str, Dict[str, int]] = {}
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


def _failure_events(
    events: Sequence[Dict[str, Any]],
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
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
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "event_index": index,
        "event": event,
        "stage": stage,
        "step_number": payload.get("step_number"),
        "action": payload.get("action", ""),
    }


def _classify_tool_failure(payload: Dict[str, Any]) -> str:
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


def _final_failure_stage(summary: Dict[str, Any], primary_stage: str) -> str:
    status = str(summary.get("status") or "")
    if status == "success":
        return "none"
    if status == "max_steps_exceeded":
        return "max_steps"
    if primary_stage != "none":
        return primary_stage
    return status or "unknown"


def _verification_analysis(summary: Dict[str, Any]) -> Dict[str, Any]:
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
) -> List[str]:
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
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
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


def _signed(value: int) -> str:
    return f"{value:+d}"


if __name__ == "__main__":
    raise SystemExit(main())
