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
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    try:
        events = load_trace_events(args.trace)
    except FileNotFoundError:
        print(f"Trace not found: {args.trace}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Invalid trace JSONL: {exc}", file=sys.stderr)
        return 2

    if args.command == "view":
        return _view(events, as_json=args.json, raw=args.raw)
    if args.command == "replay":
        return _replay(
            events,
            execute_tools=args.execute_tools,
            allow_shell=args.allow_shell,
            workspace=args.workspace,
            as_json=args.json,
        )
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


if __name__ == "__main__":
    raise SystemExit(main())
