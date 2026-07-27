"""运行报告：Markdown 报告生成与工作区 git 状态采集。"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config, format_advanced_feature_status


def collect_git_status() -> list[str]:
    """Return short git status lines for the current workspace, if available."""
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def write_run_report(
    path: Path,
    *,
    config: Config,
    task: str,
    result: dict[str, Any],
    trace_path: Path | None = None,
    git_status_before: list[str] | None = None,
    git_status_after: list[str] | None = None,
) -> None:
    """Write a human-readable Markdown report for one agent run."""
    metadata = result.get("metadata", {})
    steps = result.get("steps", [])
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# DM-Code-Agent Run Report",
        "",
        "## Task",
        "",
        task,
        "",
        "## Runtime",
        "",
        f"- Provider: `{config.provider}`",
        f"- Model: `{config.model}`",
        f"- Status: `{metadata.get('status', 'unknown')}`",
        f"- Duration: `{float(metadata.get('duration_seconds', 0.0)):.2f}s`",
        f"- Steps: `{len(steps)}`",
        f"- Tool errors: `{metadata.get('tool_error_count', 0)}`",
        f"- Replans: `{metadata.get('replan_count', 0)}`",
        f"- Advanced features: `{format_advanced_feature_status(config)}`",
    ]
    if trace_path:
        lines.append(f"- Trace: `{trace_path}`")

    before = git_status_before or []
    after = git_status_after or []
    lines.extend(["", "## Workspace Status", ""])
    if not before and not after:
        lines.append("No git status information available.")
    else:
        lines.append(f"- Dirty entries before run: `{len(before)}`")
        lines.append(f"- Dirty entries after run: `{len(after)}`")
        if before:
            lines.extend(["", "Before:", ""])
            lines.extend(f"- `{line}`" for line in before)
        if after:
            lines.extend(["", "After:", ""])
            lines.extend(f"- `{line}`" for line in after)

    lines.extend(
        [
            "",
            "## Steps",
            "",
            "| # | Action | Observation |",
            "| ---: | --- | --- |",
        ]
    )
    for index, step in enumerate(steps, start=1):
        observation = str(step.get("observation", "")).replace("\n", " ")
        if len(observation) > 180:
            observation = observation[:177] + "..."
        lines.append(f"| {index} | `{step.get('action', '')}` | {observation} |")

    lines.extend(
        [
            "",
            "## Final Answer",
            "",
            str(result.get("final_answer", "")),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def default_report_path(task: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:32] or "task"
    return Path(".dm_agent") / "run_reports" / f"{timestamp}-{slug}.md"
