"""Command-line parsing and dispatch for DM-Code-Agent trace tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .analysis import analyze_events, analyze_trace_directory
from .fork import _fork, fork_session
from .render import _analyze, _analyze_dir, _diff, _view, render_trace_directory_markdown
from .replay import _replay, replay_tools
from .summary import diff_events, summarize_events
from .writer import load_trace_events

__all__ = [
    "analyze_events",
    "analyze_trace_directory",
    "diff_events",
    "fork_session",
    "main",
    "parse_args",
    "render_trace_directory_markdown",
    "replay_tools",
    "summarize_events",
]


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

    analyze_dir_parser = subparsers.add_parser(
        "analyze-dir",
        help="Analyze all trace files in a directory and print aggregate counts.",
    )
    analyze_dir_parser.add_argument("directory", type=Path, help="Directory containing traces.")
    analyze_dir_parser.add_argument(
        "--pattern",
        default="*.jsonl",
        help="Glob pattern relative to the directory. Default: *.jsonl.",
    )
    analyze_dir_parser.add_argument("--json", action="store_true", help="Print analysis as JSON.")
    analyze_dir_parser.add_argument(
        "--markdown",
        type=Path,
        help="Write a shareable Markdown summary without raw trace contents.",
    )

    diff_parser = subparsers.add_parser("diff", help="Compare two trace timelines.")
    diff_parser.add_argument("base_trace", type=Path, help="Baseline JSONL trace file.")
    diff_parser.add_argument("candidate_trace", type=Path, help="Candidate JSONL trace file.")
    diff_parser.add_argument("--json", action="store_true", help="Print diff result as JSON.")

    fork_parser = subparsers.add_parser(
        "fork",
        help="Branch a new session file from one entry of an existing session.",
    )
    fork_parser.add_argument("session", type=Path, help="Path to a JSONL session/trace file.")
    fork_parser.add_argument(
        "--at",
        required=True,
        metavar="ENTRY_ID",
        help="Entry to fork at (exact id or a unique prefix). Entries after it are dropped.",
    )
    fork_parser.add_argument(
        "--output",
        type=Path,
        help="Destination file. Defaults to <session>.fork-<entry-id>.jsonl next to the source.",
    )
    fork_parser.add_argument("--json", action="store_true", help="Print fork result as JSON.")
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
    if args.command == "analyze-dir":
        return _analyze_dir(
            args.directory,
            pattern=args.pattern,
            as_json=args.json,
            markdown_path=args.markdown,
        )
    if args.command == "diff":
        base_events = _load_trace_for_cli(args.base_trace)
        candidate_events = _load_trace_for_cli(args.candidate_trace)
        if base_events is None or candidate_events is None:
            return 2
        return _diff(base_events, candidate_events, as_json=args.json)
    if args.command == "fork":
        events = _load_trace_for_cli(args.session)
        if events is None:
            return 2
        return _fork(
            events,
            source=args.session,
            at=args.at,
            output=args.output,
            as_json=args.json,
        )
    return 2


def _load_trace_for_cli(path: Path) -> list[dict[str, Any]] | None:
    try:
        return load_trace_events(path)
    except FileNotFoundError:
        print(f"Trace not found: {path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"Invalid trace JSONL: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    raise SystemExit(main())
