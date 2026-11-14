"""生成单文件、无网络请求的审计报告；默认只导出白名单内的结构信息。"""

from __future__ import annotations

import base64
import hashlib
import html
import math
import os
import re
import tempfile
from collections.abc import Iterable
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .analysis import VERIFICATION_TOOLS, analyze_events
from .session import normalize_entries
from .writer import SENSITIVE_ENV_MARKERS, load_trace_events

_ACTIONS = frozenset(
    {
        "list_directory",
        "read_file",
        "create_file",
        "edit_file",
        "search_in_file",
        "run_python",
        "run_shell",
        "run_tests",
        "run_linter",
        "parse_ast",
        "get_function_signature",
        "find_dependencies",
        "get_code_metrics",
        "build_code_index",
        "search_symbol",
        "dependency_graph",
        "task_complete",
        "finish",
        "error",
    }
)
_STATUSES = frozenset(
    {
        "success",
        "max_steps_exceeded",
        "error",
        "failed",
        "cancelled",
        "llm_error",
        "agent_exception",
    }
)
_EXCERPT_LIMIT = 16000
_SCRIPT = """const picker = document.getElementById('run-picker');
if (picker) {
  const showRun = () => document.querySelectorAll('.run').forEach((run, index) => {
    run.hidden = index !== Number(picker.value);
  });
  picker.addEventListener('change', showRun);
  showRun();
}
"""
_STYLE = """
:root{color-scheme:light;--ink:#1d1d1f;--muted:#6e6e73;--line:#e8e8ed;
--blue:#0060c0;--green:#248a3d;--orange:#a24a00;--red:#bd241b}
*{box-sizing:border-box}body{margin:0;background:#fbfbfd;color:var(--ink);
font:15px/1.6 'Geist','Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-underline-offset:3px}a:focus-visible,summary:focus-visible,
select:focus-visible{outline:3px solid #0071e3;outline-offset:5px}
header,main,footer{max-width:1120px;margin:auto;padding:32px 40px}
header{padding-top:48px;padding-bottom:28px}.brand{font-weight:650;letter-spacing:-.02em;
display:flex;align-items:center;gap:10px}.brand-mark{display:inline-grid;place-items:center;
width:32px;height:32px;border:1px solid #d2d2d7;border-radius:9px;font:600 12px monospace}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
color:var(--muted);margin:34px 0 12px}h1{font-size:clamp(34px,5vw,54px);line-height:1.07;
letter-spacing:-.055em;font-weight:600;margin:0 0 18px}h2{font-size:24px;line-height:1.3;
letter-spacing:-.035em;margin:0}h3{font-size:16px;margin:0 0 12px;font-weight:600}
p{margin:8px 0 0}.lede{max-width:650px;font-size:17px;color:var(--muted)}
.policy{margin-top:24px;padding:15px 18px;border:1px solid var(--line);border-radius:12px;
background:white;max-width:920px;font-size:13px;color:var(--muted)}.policy strong{color:var(--ink)}
.demo{display:inline-block;color:var(--orange);font-size:12px;font-weight:600;
background:#fff5e6;border:1px solid #f4dcb7;padding:4px 10px;border-radius:6px;margin-bottom:16px}
main{padding-top:8px}.selector{display:flex;align-items:center;justify-content:space-between;
gap:20px;padding-bottom:20px;border-bottom:1px solid var(--line);margin-bottom:30px}
label{font-size:13px;font-weight:600}select{font:inherit;font-size:13px;padding:9px 36px 9px 12px;
border:1px solid #d2d2d7;background:white;border-radius:8px;max-width:70%}
.run[hidden]{display:none}.run-heading{display:flex;align-items:center;justify-content:space-between;
gap:24px}.subtle{color:var(--muted);font-size:13px}.badge{display:inline-flex;align-items:center;
gap:6px;font-size:12px;font-weight:600;border-radius:6px;padding:4px 9px;white-space:nowrap;
background:#f0f0f3;color:var(--muted)}.badge.success{background:#eaf6ed;color:var(--green)}
.badge.failure{background:#fff0ee;color:var(--red)}.badge.warning{background:#fff5e6;color:var(--orange)}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);
border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:24px 0 30px}
.metric{background:white;padding:19px 22px}.metric span{display:block;color:var(--muted);
font-size:12px}.metric strong{font-size:28px;font-weight:550;letter-spacing:-.04em}
.section{margin-top:30px}.section-head{display:flex;align-items:baseline;justify-content:space-between;
gap:16px;margin:0 0 13px}.content{border:1px solid var(--line);background:white;
border-radius:12px;padding:20px 22px}.notice{border-left:3px solid #dba864;padding-left:15px;
color:var(--orange);font-size:13px;margin:22px 0}.timeline{list-style:none;margin:0;padding:0;
border:1px solid var(--line);background:white;border-radius:12px;overflow:hidden}
.step{padding:17px 21px}.step+.step{border-top:1px solid var(--line)}.step-head{display:flex;
gap:13px;align-items:center}.number{width:27px;height:27px;border:1px solid var(--line);
border-radius:50%;display:inline-grid;place-items:center;font-size:11px;color:var(--muted);flex-shrink:0}
.action{font-family:'Geist Mono','SFMono-Regular',Consolas,monospace;font-size:13px;font-weight:500;
overflow-wrap:anywhere}.step-head .badge{margin-left:auto}details{margin-top:12px;padding-left:40px}
summary{cursor:pointer;color:var(--blue);font-size:12px;width:fit-content}pre{font:12px/1.7
'Geist Mono','SFMono-Regular',Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;
margin:12px 0 0;background:#f7f7f9;border-radius:8px;padding:16px;max-height:420px;overflow:auto}
.diff{padding:13px 16px}.diff-line{display:block;min-height:1.7em}.diff-add{background:#e8f5ec;
color:#1d6833}.diff-remove{background:#fff0ee;color:#9a3028}.diff-header{color:var(--muted)}
.evidence{display:flex;gap:12px;align-items:center;justify-content:space-between;
padding:11px 0}.evidence+.evidence{border-top:1px solid var(--line)}
footer{border-top:1px solid var(--line);padding-top:23px;margin-top:42px;font-size:12px;
color:var(--muted);display:flex;gap:20px;justify-content:space-between}
@media(max-width:640px){header,main,footer{padding-left:20px;padding-right:20px}
header{padding-top:28px}.metrics{grid-template-columns:repeat(2,1fr)}.metric{padding:15px 17px}
.run-heading{align-items:flex-start;flex-wrap:wrap}.step{padding:15px}details{padding-left:0}.selector{gap:12px}
.step-head{flex-wrap:wrap;gap:9px}.step-head .badge{font-size:11px}.content{padding:16px}
footer{flex-direction:column}.section-head{display:block}}
@media print{body{background:white}header,main,footer{max-width:none;padding:18px}
.selector{display:none}.run[hidden]{display:block}.run{break-before:page}pre{max-height:none}
details{display:block}summary{color:var(--ink)}}
"""


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _payload(entry: dict[str, Any]) -> dict[str, Any]:
    value = entry.get("payload", {})
    if not isinstance(value, dict):
        raise ValueError("Every report entry payload must be an object.")
    return value


def _runs(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """run_start 划分运行尝试；仅继承 runtime，不混用前轮的任务、步骤或结果。"""
    result: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    runtime: dict[str, Any] | None = None
    for entry in entries:
        if entry.get("event") == "runtime":
            runtime = entry
        if entry.get("event") == "run_start" and current:
            if any(item.get("event") != "runtime" for item in current):
                result.append(current)
            current = [runtime] if runtime is not None else []
        current.append(entry)
    if current:
        result.append(current)
    return result


def _redact(text: str, *, roots: Iterable[str]) -> str:
    """按模式脱敏显式选择的正文；无法识别所有商业/个人信息，仍需用户审阅。"""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]", "", text)
    for name, value in os.environ.items():
        if len(value) >= 6 and any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS):
            text = text.replace(value, "[secret redacted]")
    for root in sorted(set(roots), key=len, reverse=True):
        if root and root not in {"/", "\\"}:
            text = text.replace(root, "[local path]")
            text = text.replace(root.replace("\\", "/"), "[local path]")
    text = re.sub(r"(?i)\b(?:https?|ftp)://[^\s<>\"']+", "[URL redacted]", text)
    text = re.sub(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 [secret redacted]", text)
    text = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[private key redacted]",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"""(?ix)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization)\b
        ["']?\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}]+)""",
        r"\1[secret redacted]",
        text,
    )
    text = re.sub(
        r"\b(?:sk[-_][A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|"
        r"github_pat_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16}|"
        r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b",
        "[secret redacted]",
        text,
    )
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[email redacted]", text)
    text = re.sub(r"""(?<!\w)(?:[A-Za-z]:[\\/]|\\\\)[^\r\n"'<>]*""", "[local path]", text)
    text = re.sub(r"""(?<![\w/<])/(?:[^\s/"'<>]+/)*[^\s/"'<>]+""", "[local path]", text)
    if len(text) > _EXCERPT_LIMIT:
        text = text[:_EXCERPT_LIMIT] + "\n[Report excerpt truncated; source log unchanged.]"
    return text


def _action(value: Any, *, include_content: bool, roots: list[str]) -> str:
    name = _text(value)
    if name in _ACTIONS:
        return name
    if include_content:
        return _redact(name, roots=roots) or "Unknown action"
    return "MCP tool" if name.startswith("mcp_") else "Custom action"


def _badge(label: str, kind: str = "") -> str:
    return f'<span class="badge {kind}">{html.escape(label)}</span>'


def _code(text: str) -> str:
    return f"<pre>{html.escape(text)}</pre>"


def _replacement_diff(arguments: Any, roots: list[str]) -> str:
    if not isinstance(arguments, dict):
        return ""
    old, new = arguments.get("old_string"), arguments.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        return ""
    lines = unified_diff(
        _redact(old, roots=roots).splitlines(),
        _redact(new, roots=roots).splitlines(),
        fromfile="before excerpt",
        tofile="after excerpt",
        lineterm="",
    )
    rendered = []
    for line in lines:
        kind = (
            "header"
            if line.startswith(("---", "+++", "@@"))
            else (
                "add" if line.startswith("+") else "remove" if line.startswith("-") else "context"
            )
        )
        rendered.append(f'<span class="diff-line diff-{kind}">{html.escape(line)}</span>')
    if not rendered:
        return ""
    return (
        "<details open><summary>Replacement excerpt</summary>"
        '<p class="subtle">Recorded replacement arguments, not a full repository diff. '
        "Check the tool receipt to see whether the edit was applied.</p>"
        '<pre class="diff">' + "".join(rendered) + "</pre></details>"
    )


def _render_run(
    run: list[dict[str, Any]], number: int, *, include_content: bool, roots: list[str]
) -> str:
    start = next((_payload(e) for e in run if e.get("event") == "run_start"), {})
    end_entry = next((e for e in reversed(run) if e.get("event") == "run_end"), None)
    end = _payload(end_entry) if end_entry is not None else {}
    if not isinstance(end.get("metadata", {}), dict):
        raise ValueError("Run metadata must be an object.")
    for entry in run:
        if entry.get("event") in ("step", "tool_call"):
            payload = _payload(entry)
            if not isinstance(payload.get("action", ""), str) or not isinstance(
                payload.get("step_number", 0), int
            ):
                raise ValueError("Recorded actions must be text and step numbers must be integers.")
    completed = {
        (_payload(entry).get("step_number"), _payload(entry).get("action"))
        for entry in run
        if entry.get("event") == "step"
    }
    # An interrupted run can contain a tool receipt without the following step event.
    analysis_run = []
    steps = []
    for entry in run:
        payload = _payload(entry)
        analysis_run.append(entry)
        if entry.get("event") == "step":
            steps.append(payload)
        elif (
            entry.get("event") == "tool_call"
            and (payload.get("step_number"), payload.get("action")) not in completed
        ):
            steps.append(payload)
            analysis_run.append({"event": "step", "payload": payload})
    try:
        analysis = analyze_events(analysis_run)
    except (TypeError, ValueError, AttributeError, KeyError, OverflowError) as exc:
        raise ValueError(
            "Session contains unsupported event fields; inspect the source log."
        ) from exc
    status = _text(end.get("status"))
    status = status if status in _STATUSES else "unknown" if end_entry is not None else "incomplete"
    status_label = (
        "Success reported" if status == "success" else status.replace("_", " ").capitalize()
    )
    status_kind = "success" if status == "success" else "warning"
    calls = [_payload(e) for e in run if e.get("event") == "tool_call"]
    calls_by_step = {(c.get("step_number"), c.get("action")): c for c in calls}
    verification = analysis["verification"]
    duration = end.get("duration_seconds")
    seconds = (
        f"{duration:.2f}s"
        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and 0 <= duration <= 1e12
            and math.isfinite(duration)
        )
        else "—"
    )
    metrics = (
        ("Recorded steps", len(steps)),
        ("Verification actions", verification["count"]),
        ("Replans", analysis["recovery"]["replan_count"]),
        ("Recorded duration", seconds),
    )
    provenance = start.get("metadata", {})
    scripted = (
        isinstance(provenance, dict)
        and provenance.get("demo") is True
        and provenance.get("source") == "scripted"
    )
    subheading = (
        _badge("Scripted demo · no model call", "warning") if scripted else "Recorded task attempt"
    )
    result = [
        f'<section class="run" id="run-{number}" aria-label="Run {number}">',
        '<div class="run-heading"><div>',
        f"<h2>Run {number:02d}</h2>",
        f'<p class="subtle">{subheading}</p></div>',
        _badge(status_label, status_kind),
        '</div><div class="metrics">',
    ]
    result.extend(
        f'<div class="metric"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in metrics
    )
    result.append("</div>")
    if include_content:
        result.append(
            '<div class="content"><h3>Task</h3>'
            + _code(_redact(_text(start.get("task")), roots=roots))
            + "</div>"
        )
        if _text(end.get("final_answer")):
            result.append(
                '<div class="section content"><h3>Final answer</h3>'
                + _code(_redact(end["final_answer"], roots=roots))
                + "</div>"
            )
    if verification["gap"]:
        result.append(
            '<p class="notice">Verification gap: success was reported without a recorded local verification action before completion.</p>'
        )
    elif end_entry is None:
        result.append(
            '<p class="notice">No run_end event is present. This report does not claim that the process is still running.</p>'
        )
    result.append(
        '<section class="section"><div class="section-head"><h3>Verification evidence</h3><span class="subtle">Recorded commands, not a coverage guarantee</span></div><div class="content">'
    )
    checks = [step for step in steps if step.get("action") in VERIFICATION_TOOLS]
    if not checks:
        result.append('<p class="subtle">No local verification action recorded.</p>')
    for step in checks:
        codes = re.findall(
            r"^returncode:\s*(-?\d{1,12})\s*$", _text(step.get("observation")), re.MULTILINE
        )
        label = f"Exit {int(codes[-1])}" if codes else "Exit not recorded"
        kind = "success" if codes and int(codes[-1]) == 0 else "failure" if codes else "warning"
        result.append(
            '<div class="evidence"><span class="action">'
            + html.escape(_text(step["action"]))
            + "</span>"
            + _badge(label, kind)
            + "</div>"
        )
    result.append(
        '</div></section><section class="section"><div class="section-head"><h3>Execution trail</h3><span class="subtle">Original log remains unchanged</span></div><ol class="timeline">'
    )
    for index, step in enumerate(steps, 1):
        call = calls_by_step.get((step.get("step_number"), step.get("action")), {})
        failed = call.get("failed") is True or step.get("action") == "error"
        outcome = "Failed" if failed else "Completed" if call.get("failed") is False else "Recorded"
        result.append(
            f'<li class="step"><div class="step-head"><span class="number">{index:02d}</span><span class="action">'
            + html.escape(_action(step.get("action"), include_content=include_content, roots=roots))
            + "</span>"
            + _badge(outcome, "failure" if failed else "")
            + "</div>"
        )
        if include_content:
            if step.get("action") == "edit_file":
                result.append(_replacement_diff(step.get("action_input"), roots))
            observation = _text(step.get("observation"))
            if observation:
                result.append(
                    "<details><summary>Tool receipt</summary>"
                    + _code(_redact(observation, roots=roots))
                    + "</details>"
                )
        result.append("</li>")
    if not steps:
        result.append('<li class="step subtle">No steps recorded.</li>')
    result.append("</ol></section></section>")
    return "".join(result)


def export_session_report(
    entries: Iterable[dict[str, Any]],
    *,
    source_name: str = "Session",
    include_content: bool = False,
    demo: bool = False,
) -> str:
    """返回独立 HTML；正文只在显式 include_content 时进入，源条目永不修改。"""
    collected = normalize_entries(entries)
    runs = _runs(collected)
    roots = [str(Path.home())]
    roots.extend(_text(_payload(e).get("cwd")) for e in collected if e.get("event") == "run_start")
    title = "Run evidence, ready to inspect."
    policy = (
        "Content included · pattern-based redaction applied. Task text, final answers, tool receipts and replacement excerpts are included. Review this file locally before sharing; redaction cannot detect every private detail."
        if include_content
        else "Summary only · task text, source names, answers, code, paths, tool output and arbitrary metadata are omitted. No hidden raw payloads are embedded."
    )
    digest = base64.b64encode(hashlib.sha256(_SCRIPT.encode()).digest()).decode()
    page = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-"
        + digest
        + "'; base-uri 'none'; form-action 'none'\">",
        "<title>DM-Code-Agent · Run report</title><style>" + _STYLE + "</style></head><body>",
        '<header><div class="brand"><span class="brand-mark">DM</span> DM-Code-Agent</div>',
        '<p class="eyebrow">Standalone run report</p>',
    ]
    if demo:
        page.append('<span class="demo">Scripted demo · real local tools · no model call</span>')
    page.extend(
        [
            "<h1>" + title + "</h1>",
            '<p class="lede">Follow the changes. Inspect the checks. Keep the evidence.</p>',
            '<div class="policy"><strong>Sharing policy</strong><br>'
            + html.escape(policy)
            + "<br>Checkpoint state, raw LLM messages and system prompts are never exported. This file makes no network requests.</div>",
        ]
    )
    if include_content:
        name = source_name.replace("\\", "/").rsplit("/", 1)[-1]
        page.append('<p class="subtle">Source: ' + html.escape(_redact(name, roots=roots)) + "</p>")
    page.append("</header><main>")
    if runs:
        page.append(
            '<div class="selector"><label for="run-picker">Inspect a run</label><select id="run-picker">'
        )
        page.extend(
            f'<option value="{i}">Run {i + 1:02d} of {len(runs):02d}</option>'
            for i in range(len(runs))
        )
        page.append("</select></div>")
        page.extend(
            _render_run(run, i, include_content=include_content, roots=roots)
            for i, run in enumerate(runs, 1)
        )
    else:
        page.append(
            '<div class="content"><h2>No entries recorded.</h2><p class="subtle">The source contains no session events.</p></div>'
        )
    page.extend(
        [
            "</main><footer><span>Derived from recorded events. No model calls, replay or file edits.</span>",
            '<a href="https://github.com/hwfengcs/DM-Code-Agent" rel="noreferrer">Built with DM-Code-Agent ↗</a></footer>',
            "<script>" + _SCRIPT + "</script></body></html>",
        ]
    )
    return "".join(page)


def save_session_report(
    source: str | Path, output: str | Path, *, include_content: bool = False, force: bool = False
) -> Path:
    """读取会话，安全创建派生报告；显式 force 也不能覆盖源文件或其别名。"""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve() or (output.exists() and source.samefile(output)):
        raise ValueError("The HTML output must not overwrite the source session.")
    if output.exists() and not force:
        raise ValueError("Report already exists. Choose a new output or use --force.")
    page = export_session_report(
        load_trace_events(source), source_name=source.name, include_content=include_content
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if not force:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(page)
        return output
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(page)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output
