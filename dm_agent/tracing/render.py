"""Human, JSON, and Markdown rendering for trace inspection commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analysis import analyze_events, analyze_trace_directory
from .summary import diff_events, summarize_events


def _view(events: list[dict[str, Any]], *, as_json: bool, raw: bool) -> int:
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


def _analyze(
    events: list[dict[str, Any]],
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
    hallucination = analysis.get("hallucination_signals", {})
    print(
        "Hallucination signals: "
        f"edit_without_read={hallucination.get('edit_without_read_count', 0)}, "
        f"guard_blocks={hallucination.get('edit_guard_blocks', 0)}, "
        f"truncations={hallucination.get('truncation_hits', 0)}, "
        f"missing_paths={hallucination.get('missing_path_reference_count', 0)}"
    )
    print(f"Health: {health['grade']} ({health['score']:.2f})")
    if health["issues"]:
        print("Issues:")
        for issue in health["issues"]:
            print(f"- {issue}")
    return 0


def _analyze_dir(
    directory: Path,
    *,
    pattern: str,
    as_json: bool,
    markdown_path: Path | None = None,
) -> int:
    report = analyze_trace_directory(directory, pattern=pattern)
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_trace_directory_markdown(report), encoding="utf-8")
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if not report["errors"] else 1

    summary = report["summary"]
    print("Trace directory analysis")
    print(f"Directory: {report['directory']}")
    print(f"Pattern: {report['pattern']}")
    print(f"Traces: {summary['analyzed_traces']}/{summary['total_files']} analyzed")
    print(f"Errors: {summary['error_count']}")
    print(f"Verification gaps: {summary['verification_gap_count']}")
    recovery_rate = summary.get("recovery_success_rate")
    if recovery_rate is not None:
        print(
            f"Recovery: {summary.get('recovered_runs', 0)}/"
            f"{summary.get('runs_with_failures', 0)} ({recovery_rate:.1%})"
        )
    hallucination = summary.get("hallucination_signals", {})
    if hallucination:
        print(
            "Hallucination signals: "
            f"edit_without_read={hallucination.get('edit_without_read_count', 0)}, "
            f"guard_blocks={hallucination.get('edit_guard_blocks', 0)}, "
            f"truncations={hallucination.get('truncation_hits', 0)}, "
            f"missing_paths={hallucination.get('missing_path_reference_count', 0)}"
        )
    print("Trace health:")
    for grade, count in summary["trace_health_counts"].items():
        print(f"- {grade}: {count}")
    print("Final failure stages:")
    for stage, count in summary["final_failure_stage_counts"].items():
        print(f"- {stage}: {count}")
    if markdown_path:
        print(f"Markdown report: {markdown_path}")
    return 0 if not report["errors"] else 1


def render_trace_directory_markdown(report: dict[str, Any]) -> str:
    """Render trace-directory analysis without raw prompt, observation, or answer text."""

    summary = report.get("summary") or {}
    lines = [
        "# Trace Directory Analysis",
        "",
        "This report is generated from trace metadata only. It omits raw prompts, observations, "
        "tool outputs, and final answers.",
        "",
        f"- Directory: `{report.get('directory', '')}`",
        f"- Pattern: `{report.get('pattern', '')}`",
        f"- Traces analyzed: `{summary.get('analyzed_traces', 0)}/{summary.get('total_files', 0)}`",
        f"- Errors: `{summary.get('error_count', 0)}`",
        f"- Verification gaps: `{summary.get('verification_gap_count', 0)}`",
        "",
        "## Trace Health",
        "",
    ]
    for grade, count in (summary.get("trace_health_counts") or {}).items():
        lines.append(f"- `{grade}`: `{count}`")

    recovery_rate = summary.get("recovery_success_rate")
    hallucination = summary.get("hallucination_signals") or {}
    lines.extend(["", "## Recovery & Hallucination Signals", ""])
    if recovery_rate is not None:
        lines.append(
            f"- Recovery success rate: `{recovery_rate:.1%}` "
            f"(`{summary.get('recovered_runs', 0)}/{summary.get('runs_with_failures', 0)}`)"
        )
    else:
        lines.append("- Recovery success rate: `n/a` (no runs with failures)")
    lines.extend(
        [
            f"- Edits without a prior read: `{hallucination.get('edit_without_read_count', 0)}`",
            f"- Edit-guard blocks: `{hallucination.get('edit_guard_blocks', 0)}`",
            f"- Truncated observations: `{hallucination.get('truncation_hits', 0)}`",
            "- Missing-path references: "
            f"`{hallucination.get('missing_path_reference_count', 0)}`",
        ]
    )

    lines.extend(["", "## Final Failure Stages", ""])
    for stage, count in (summary.get("final_failure_stage_counts") or {}).items():
        lines.append(f"- `{stage}`: `{count}`")

    lines.extend(
        [
            "",
            "## Trace Details",
            "",
            "| Trace | Status | Health | Final failure | Verification gap | Replans |",
            "| --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for item in report.get("analyses", []):
        analysis = item.get("analysis") or {}
        health = analysis.get("trace_health") or {}
        verification = analysis.get("verification") or {}
        recovery = analysis.get("recovery") or {}
        lines.append(
            "| {path} | {status} | {health} | {final_failure} | {gap} | {replans} |".format(
                path=f"`{_display_trace_path(str(item.get('path', '')), report)}`",
                status=f"`{analysis.get('status', '')}`",
                health=f"`{health.get('grade', 'unknown')}`",
                final_failure=f"`{analysis.get('final_failure_stage', 'unknown')}`",
                gap="yes" if verification.get("gap") else "no",
                replans=int(recovery.get("replan_count") or 0),
            )
        )

    errors = report.get("errors") or []
    if errors:
        lines.extend(["", "## Errors", ""])
        for item in errors:
            lines.append(f"- `{_display_trace_path(str(item.get('path', '')), report)}`: error")

    return "\n".join(lines) + "\n"


def _diff(
    base_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
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


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _display_trace_path(path: str, report: dict[str, Any]) -> str:
    directory = Path(str(report.get("directory") or ""))
    trace_path = Path(path)
    try:
        return trace_path.relative_to(directory).as_posix()
    except (ValueError, OSError):
        return trace_path.name


def _signed(value: int) -> str:
    return f"{value:+d}"
