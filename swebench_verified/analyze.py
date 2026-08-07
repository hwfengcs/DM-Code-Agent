"""离线合并 SWE-bench prediction、trace 与官方 harness 结果。

本模块只读输入，不执行 Agent、Docker、SWE verifier 或网络请求。它把三个彼此独立的
结果轴保留下来：官方 harness 结论、逐题 harness detail，以及 Agent/trace 过程指标。
所有输出均由输入确定，不包含题面、测试名称、patch 内容或 trace 原文。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .selection import normalize_difficulty

SCHEMA_VERSION = 1

OFFICIAL_OUTCOMES = (
    "resolved",
    "unresolved",
    "empty_patch",
    "harness_error",
    "incomplete",
    "unknown",
)
HARNESS_DETAIL_STATUSES = (
    "all_passed",
    "f2p_only",
    "f2p_and_p2p",
    "p2p_only",
    "patch_apply_failure",
    "detail_unavailable",
    "unmeasured",
    "invalid",
)
AGENT_OUTCOMES = ("success", "max_steps", "exception", "unknown")
TRACE_STATUSES = ("measured", "missing", "unmeasured", "invalid")
FAILURE_LABELS = (
    "empty_patch",
    "no_edit",
    "max_steps",
    "parse_error",
    "guard_block",
    "f2p_unresolved",
    "p2p_regression",
    "harness_error",
    "unknown",
)

_PREDICTION_DIAGNOSTICS = {
    "steps": "dm_steps",
    "replans": "dm_replans",
    "parse_errors": "dm_parse_errors",
    "parse_repairs": "dm_parse_repairs",
    "parse_error_context_omitted_count": "dm_parse_error_context_omitted_count",
    "parse_error_context_omitted_chars": "dm_parse_error_context_omitted_chars",
    "truncations": "dm_truncations",
    "edit_guard_blocks": "dm_edit_guard_blocks",
    "edit_noops": "dm_edit_noops",
    "repeat_search_blocks": "dm_repeat_search_blocks",
    "edit_state_revisits": "dm_edit_state_revisits",
    "edit_cycle_blocks": "dm_edit_cycle_blocks",
}
_TRACE_COUNTER_SOURCES = {
    "parse_errors": ("parse_error_count", "parse_error"),
    "truncations": ("truncation_count", "observation_truncated"),
    "edit_guard_blocks": ("edit_guard_block_count", "edit_guard"),
    "edit_noops": ("edit_noop_count", "edit_noop"),
    "repeat_search_blocks": ("repeat_search_block_count", "swebench_repeat_search_block"),
    "edit_state_revisits": ("edit_state_revisit_count", "swebench_edit_state_revisit"),
    "edit_cycle_blocks": ("edit_cycle_block_count", "swebench_edit_cycle_block"),
}
_TRACE_EVENT_COUNTERS = {
    output_name: event_name for output_name, (_, event_name) in _TRACE_COUNTER_SOURCES.items()
}
_VERIFICATION_ACTIONS = {"run_python", "run_tests", "run_linter"}
_MUTATION_CAPABLE_ACTIONS = {"edit_file", "create_file", "run_shell", "run_python"}
_DETAIL_TEST_AXES = ("FAIL_TO_PASS", "PASS_TO_PASS")
_INVALID_TRACE_EVENT = "__analysis_invalid_trace_line__"


class AnalysisInputError(ValueError):
    """输入契约不满足时抛出的可读错误。"""


def analyze_paths(
    predictions_path: Path,
    report_path: Path,
    *,
    manifest_path: Path | None = None,
    trace_dirs: Sequence[Path] = (),
    harness_log_dir: Path | None = None,
    prefix_count: int | None = None,
    json_output: Path | None = None,
    markdown_output: Path | None = None,
) -> dict[str, Any]:
    """分析一组离线 SWE-bench 归档。

    ``json_output`` 与 ``markdown_output`` 只用于在写出前检查路径冲突；实际写文件由
    CLI 负责，便于库调用保持纯函数式、不会意外覆盖证据。
    """

    predictions_path = Path(predictions_path)
    report_path = Path(report_path)
    manifest_path = Path(manifest_path) if manifest_path is not None else None
    trace_dirs = tuple(Path(path) for path in trace_dirs)
    harness_log_dir = Path(harness_log_dir) if harness_log_dir is not None else None

    _require_file(predictions_path, "predictions JSONL")
    _require_file(report_path, "harness report JSON")
    if manifest_path is not None:
        _require_file(manifest_path, "selection manifest JSON")
    for directory in trace_dirs:
        _require_directory(directory, "trace directory")
    if harness_log_dir is not None:
        _require_directory(harness_log_dir, "harness detail directory")

    input_files = _input_files(
        predictions_path,
        report_path,
        manifest_path,
        trace_dirs,
        harness_log_dir,
    )
    _validate_output_paths(json_output, markdown_output, input_files)

    warnings: list[dict[str, Any]] = []
    predictions = _load_predictions(predictions_path)
    prediction_ids = [row["instance_id"] for row in predictions]
    prediction_map = {row["instance_id"]: row for row in predictions}

    manifest: dict[str, Any] | None = None
    manifest_ids: list[str] | None = None
    manifest_metadata: dict[str, dict[str, Any]] = {}
    if manifest_path is not None:
        manifest = _load_json_object(manifest_path, "selection manifest")
        manifest_ids, manifest_metadata = _validate_manifest(manifest, manifest_path)
        if prediction_ids != manifest_ids:
            raise AnalysisInputError(
                "predictions instance_id 顺序必须逐项等于 selection manifest.instance_ids"
            )

    report = _load_json_object(report_path, "harness report")
    report_index = _index_report(report, report_path)
    if not report_index["valid"]:
        warnings.append(
            _warning(
                "report_missing_mapping",
                "report 缺少可用于逐题映射的 ID 字段；逐题官方结论标为 unknown。",
                path=report_path,
            )
        )
    if manifest_ids is not None and report_index["valid"]:
        _validate_id_set(
            report_index["submitted_ids"],
            set(manifest_ids),
            f"report submitted_ids 与 manifest instance_ids 不一致: {report_path}",
        )

    # 以 manifest/predictions 的稳定顺序为主；没有 manifest 时 predictions 定义样本顺序。
    instance_ids = list(manifest_ids or prediction_ids)
    trace_checked = bool(trace_dirs)
    trace_index = _scan_traces(trace_dirs, set(instance_ids), warnings)
    detail_checked = harness_log_dir is not None
    detail_index = _scan_harness_details(harness_log_dir, set(instance_ids), warnings)

    if report_index["valid"]:
        extra_report_ids = sorted(set(report_index["submitted_ids"]) - set(instance_ids))
        if extra_report_ids:
            warnings.append(
                _warning(
                    "report_unknown_instance",
                    f"report 包含不在 predictions/manifest 中的 instance（{len(extra_report_ids)} 个）。",
                    path=report_path,
                )
            )

    rows: list[dict[str, Any]] = []
    for instance_id in instance_ids:
        prediction = prediction_map.get(instance_id)
        trace = trace_index.get(instance_id)
        detail = detail_index.get(instance_id)
        row = _merge_instance(
            instance_id,
            prediction,
            report_index,
            trace,
            detail,
            manifest_metadata.get(instance_id),
            trace_checked,
            detail_checked,
            warnings,
        )
        rows.append(row)
    if manifest is not None:
        _validate_manifest_aggregates(manifest, rows, manifest_path, warnings)

    # report 有效但 submitted 中缺 prediction 的情况不改变主样本分母；以 warning 明示。
    if report_index["valid"]:
        missing_predictions = sorted(set(report_index["submitted_ids"]) - set(prediction_ids))
        if missing_predictions:
            warnings.append(
                _warning(
                    "prediction_missing_instance",
                    f"report submitted_ids 中有 {len(missing_predictions)} 个 instance 缺 prediction。",
                    path=predictions_path,
                )
            )

    warnings = _sorted_warnings(warnings)
    scopes = {"all": _summarize_rows(rows)}
    if prefix_count is not None:
        if not 0 < prefix_count < len(rows):
            raise AnalysisInputError(
                f"prefix-count 必须在 1 与样本数-1 之间（当前 {prefix_count}，样本数 {len(rows)}）"
            )
        scopes[f"prefix_1_{prefix_count}"] = _summarize_rows(rows[:prefix_count])
        scopes[f"remainder_{prefix_count + 1}_{len(rows)}"] = _summarize_rows(rows[prefix_count:])

    summary: dict[str, Any] = dict(scopes)
    summary["by_repo"] = _facet_summaries(rows, "repo")
    summary["by_difficulty"] = _facet_summaries(rows, "difficulty")
    summary["by_official_outcome"] = _facet_summaries(rows, "official", "outcome")
    summary["by_failure_label"] = _label_summaries(rows)

    result = {
        "schema_version": SCHEMA_VERSION,
        "mode": "swebench_failure_analysis",
        "inputs": {
            "predictions": str(predictions_path),
            "report": str(report_path),
            "manifest": str(manifest_path) if manifest_path is not None else None,
            "trace_dirs": [str(path) for path in trace_dirs],
            "harness_log_dir": str(harness_log_dir) if harness_log_dir is not None else None,
            "prefix_count": prefix_count,
        },
        "warnings": warnings,
        "summary": summary,
        "instances": rows,
    }
    return result


def analyze_swebench(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """``analyze_paths`` 的语义别名，方便调用者按任务名发现 API。"""

    return analyze_paths(*args, **kwargs)


def render_markdown(analysis: dict[str, Any]) -> str:
    """渲染确定性的人工可读摘要，不透传 trace 原文。"""

    summary = analysis.get("summary", {})
    rows = analysis.get("instances", [])
    lines = ["# SWE-bench 离线失败分析", ""]
    lines.append(f"- 实例数：{_value(summary.get('all', {}).get('denominator'))}")
    lines.append(f"- warning 数：{len(analysis.get('warnings', []))}")
    lines.append("")
    lines.append("## 官方结果轴")
    lines.append("")
    lines.append(
        "| 范围 | 分母 | resolved | unresolved | empty patch | harness error | incomplete | unknown |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name, bucket in _scope_items(summary):
        counts = bucket.get("official_outcomes", {})
        lines.append(
            "| {name} | {denom} | {resolved} | {unresolved} | {empty} | {error} | {incomplete} | {unknown} |".format(
                name=_md(name),
                denom=_value(bucket.get("denominator")),
                resolved=_value(counts.get("resolved", 0)),
                unresolved=_value(counts.get("unresolved", 0)),
                empty=_value(counts.get("empty_patch", 0)),
                error=_value(counts.get("harness_error", 0)),
                incomplete=_value(counts.get("incomplete", 0)),
                unknown=_value(counts.get("unknown", 0)),
            )
        )
    lines.extend(
        [
            "",
            "## Harness detail 轴",
            "",
            "| 范围 | all passed | F2P-only | F2P+P2P | P2P-only | patch apply failure | detail unavailable | invalid | unmeasured |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, bucket in _scope_items(summary):
        counts = bucket.get("harness_details", {})
        lines.append(
            "| {name} | {all_passed} | {f2p_only} | {f2p_and_p2p} | {p2p_only} | {apply_failure} | {unavailable} | {invalid} | {unmeasured} |".format(
                name=_md(name),
                all_passed=_value(counts.get("all_passed", 0)),
                f2p_only=_value(counts.get("f2p_only", 0)),
                f2p_and_p2p=_value(counts.get("f2p_and_p2p", 0)),
                p2p_only=_value(counts.get("p2p_only", 0)),
                apply_failure=_value(counts.get("patch_apply_failure", 0)),
                unavailable=_value(counts.get("detail_unavailable", 0)),
                invalid=_value(counts.get("invalid", 0)),
                unmeasured=_value(counts.get("unmeasured", 0)),
            )
        )
    lines.extend(
        [
            "",
            "## Agent / trace 轴",
            "",
            "| 范围 | success | max-steps | exception | unknown | steps（已测） | parse errors（已测） | repeat-search blocks（已测） | trace max-steps（已测） |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, bucket in _scope_items(summary):
        agent_counts = bucket.get("agent_outcomes", {})
        metrics = bucket.get("agent_metrics", {})
        trace = bucket.get("trace", {})
        lines.append(
            "| {name} | {success} | {max_steps} | {exception} | {unknown} | {steps} | {parse} | {repeat} | {trace_max} |".format(
                name=_md(name),
                success=_value(agent_counts.get("success", 0)),
                max_steps=_value(agent_counts.get("max_steps", 0)),
                exception=_value(agent_counts.get("exception", 0)),
                unknown=_value(agent_counts.get("unknown", 0)),
                steps=_metric_cell(metrics.get("steps")),
                parse=_metric_cell(metrics.get("parse_errors")),
                repeat=_metric_cell(metrics.get("repeat_search_blocks")),
                trace_max=_metric_cell(trace.get("max_steps")),
            )
        )

    lines.extend(["", "## Repo / difficulty 分层", ""])
    lines.append("### Repo")
    lines.append("")
    lines.append("| repo | 分母 | resolved | unresolved | empty patch | labels |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for key, bucket in (summary.get("by_repo", {}) or {}).items():
        lines.append(_facet_row(key, bucket))
    lines.extend(
        [
            "",
            "### Difficulty",
            "",
            "| difficulty | 分母 | resolved | unresolved | empty patch | labels |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for key, bucket in (summary.get("by_difficulty", {}) or {}).items():
        lines.append(_facet_row(key, bucket))

    lines.extend(["", "## 失败标签", "", "| 标签 | 命中数 | 总分母 |", "| --- | ---: | ---: |"])
    for label, bucket in (summary.get("by_failure_label", {}) or {}).items():
        lines.append(
            f"| {_md(label)} | {_value(bucket.get('count'))} | {_value(bucket.get('denominator'))} |"
        )

    lines.extend(
        [
            "",
            "## 逐题结果",
            "",
            "| # | instance | repo | difficulty | official | detail | agent | patch chars | labels | trace |",
            "| ---: | --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for index, row in enumerate(rows, start=1):
        patch = row.get("patch", {})
        trace = row.get("trace", {})
        lines.append(
            "| {index} | {instance} | {repo} | {difficulty} | {official} | {detail} | {agent} | {chars} | {labels} | {trace_status} |".format(
                index=index,
                instance=_md(row.get("instance_id")),
                repo=_md(row.get("repo") or "unknown"),
                difficulty=_md(row.get("difficulty") or "unknown"),
                official=_md(row.get("official", {}).get("outcome") or "unknown"),
                detail=_md(row.get("harness_detail", {}).get("status") or "unmeasured"),
                agent=_md(row.get("agent", {}).get("outcome") or "unknown"),
                chars=_value(patch.get("chars")),
                labels=_md(", ".join(row.get("failure_labels", [])) or "—"),
                trace_status=_md(trace.get("status") or "unmeasured"),
            )
        )
    lines.extend(
        [
            "",
            "### Agent 逐题诊断",
            "",
            "| # | instance | status | failure | steps | duration s | replans | parse errors | repairs | truncations | guard blocks | noops | repeat blocks | revisits | cycles |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, row in enumerate(rows, start=1):
        agent = row.get("agent", {})
        counters = agent.get("counters", {})
        lines.append(
            "| {index} | {instance} | {status} | {failure} | {steps} | {duration} | {replans} | {parse_errors} | {repairs} | {truncations} | {guards} | {noops} | {repeat} | {revisits} | {cycles} |".format(
                index=index,
                instance=_md(row.get("instance_id")),
                status=_md(agent.get("outcome") or "unknown"),
                failure=_md(agent.get("failure") or "—"),
                steps=_value(agent.get("steps")),
                duration=_value(agent.get("duration_seconds")),
                replans=_value(agent.get("replans")),
                parse_errors=_value(counters.get("parse_errors")),
                repairs=_value(counters.get("parse_repairs")),
                truncations=_value(counters.get("truncations")),
                guards=_value(counters.get("edit_guard_blocks")),
                noops=_value(counters.get("edit_noops")),
                repeat=_value(counters.get("repeat_search_blocks")),
                revisits=_value(counters.get("edit_state_revisits")),
                cycles=_value(counters.get("edit_cycle_blocks")),
            )
        )
    lines.extend(
        [
            "",
            "### Trace 审计信号",
            "",
            "| # | instance | trace | max steps | direct writes | mutation-capable calls | repeated signatures | repeated calls | verification gap |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for index, row in enumerate(rows, start=1):
        trace = row.get("trace", {})
        lines.append(
            "| {index} | {instance} | {status} | {max_steps} | {writes} | {mutations} | {signatures} | {calls} | {gap} |".format(
                index=index,
                instance=_md(row.get("instance_id")),
                status=_md(trace.get("status") or "unmeasured"),
                max_steps=_value(trace.get("max_steps")),
                writes=_value(trace.get("direct_write_calls")),
                mutations=_value(trace.get("mutation_capable_calls")),
                signatures=_value(trace.get("repeated_tool_signature_count")),
                calls=_value(trace.get("repeated_tool_call_count")),
                gap=_value(trace.get("verification_gap")),
            )
        )
    if analysis.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in analysis["warnings"]:
            instance = f" [{_md(warning['instance_id'])}]" if warning.get("instance_id") else ""
            lines.append(
                f"- `{_md(warning.get('code', 'warning'))}`{instance}：{_md(warning.get('message', ''))}"
            )
    return "\n".join(lines) + "\n"


def render_json(analysis: dict[str, Any]) -> str:
    """以稳定字段顺序/缩进渲染 JSON。"""

    return json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="离线合并 SWE-bench prediction、trace 与 harness 结果。"
    )
    parser.add_argument("--predictions", type=Path, required=True, help="predictions JSONL 路径")
    parser.add_argument("--report", type=Path, required=True, help="官方 harness report JSON 路径")
    parser.add_argument("--manifest", type=Path, default=None, help="可选 selection manifest JSON")
    parser.add_argument(
        "--trace-dir", type=Path, action="append", default=[], help="可重复的 trace 根目录"
    )
    parser.add_argument(
        "--harness-log-dir", type=Path, default=None, help="可选逐题 harness detail 目录"
    )
    parser.add_argument(
        "--prefix-count", type=int, default=None, help="额外输出前缀与 remainder 分析"
    )
    parser.add_argument(
        "--json", dest="json_output", type=Path, default=None, help="写机器可读 JSON"
    )
    parser.add_argument(
        "--markdown", dest="markdown_output", type=Path, default=None, help="写 Markdown 报告"
    )
    args = parser.parse_args(argv)

    try:
        analysis = analyze_paths(
            args.predictions,
            args.report,
            manifest_path=args.manifest,
            trace_dirs=args.trace_dir,
            harness_log_dir=args.harness_log_dir,
            prefix_count=args.prefix_count,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
        json_text = render_json(analysis)
        markdown_text = render_markdown(analysis)
        if args.json_output is not None:
            _write_output(args.json_output, json_text)
        if args.markdown_output is not None:
            _write_output(args.markdown_output, markdown_text)
        sys.stdout.write(markdown_text)
        return 0
    except (AnalysisInputError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise AnalysisInputError(f"{label} 不存在: {path}")
    if not path.is_file():
        raise AnalysisInputError(f"{label} 不是文件: {path}")


def _require_directory(path: Path, label: str) -> None:
    if not path.exists():
        raise AnalysisInputError(f"显式传入的 {label} 不存在: {path}")
    if not path.is_dir():
        raise AnalysisInputError(f"显式传入的 {label} 不是目录: {path}")


def _input_files(
    predictions: Path,
    report: Path,
    manifest: Path | None,
    trace_dirs: Sequence[Path],
    detail_dir: Path | None,
) -> set[Path]:
    files = {predictions.resolve(), report.resolve()}
    if manifest is not None:
        files.add(manifest.resolve())
    for directory in trace_dirs:
        files.update(path.resolve() for path in directory.rglob("*.jsonl") if path.is_file())
    if detail_dir is not None:
        files.update(path.resolve() for path in detail_dir.rglob("report.json") if path.is_file())
    return files


def _validate_output_paths(
    json_output: Path | None,
    markdown_output: Path | None,
    input_files: set[Path],
) -> None:
    outputs = [path.resolve() for path in (json_output, markdown_output) if path is not None]
    if len(set(outputs)) != len(outputs):
        raise AnalysisInputError("--json 与 --markdown 不能指向同一个文件")
    collisions = [path for path in outputs if path in input_files]
    if collisions:
        raise AnalysisInputError(f"输出路径不能覆盖只读输入: {collisions[0]}")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnalysisInputError(
            f"{label} JSON 无效 {path}（第 {exc.lineno} 行，第 {exc.colno} 列）"
        ) from exc
    except OSError as exc:
        raise AnalysisInputError(f"读取 {label} 失败 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnalysisInputError(f"{label} 顶层必须是 JSON object: {path}")
    return value


def _load_predictions(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AnalysisInputError(f"读取 predictions 失败 {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnalysisInputError(
                f"predictions JSONL 无效 {path} 第 {line_number} 行（第 {exc.colno} 列）"
            ) from exc
        if not isinstance(value, dict):
            raise AnalysisInputError(f"predictions 第 {line_number} 行必须是 JSON object: {path}")
        instance_id = value.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise AnalysisInputError(f"predictions 第 {line_number} 行缺少有效 instance_id: {path}")
        if instance_id in seen:
            raise AnalysisInputError(f"predictions 重复 instance_id={instance_id}: {path}")
        seen.add(instance_id)
        rows.append(value)
    if not rows:
        raise AnalysisInputError(f"predictions 为空: {path}")
    return rows


def _validate_manifest(
    manifest: dict[str, Any], path: Path
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    ids = manifest.get("instance_ids")
    if not isinstance(ids, list) or not all(isinstance(item, str) and item for item in ids):
        raise AnalysisInputError(f"manifest.instance_ids 必须是非空字符串数组: {path}")
    if len(set(ids)) != len(ids):
        raise AnalysisInputError(f"manifest.instance_ids 含重复 ID: {path}")
    selected_count = manifest.get("selected_count")
    if selected_count is not None and (
        not _is_int(selected_count) or int(selected_count) != len(ids)
    ):
        raise AnalysisInputError(f"manifest.selected_count 与 instance_ids 长度不一致: {path}")
    for field in ("repo_counts", "difficulty_counts"):
        value = manifest.get(field)
        if value is None:
            continue
        if not isinstance(value, dict) or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in value.values()
        ):
            raise AnalysisInputError(f"manifest.{field} 必须是非负计数字典: {path}")
        if sum(value.values()) != len(ids):
            raise AnalysisInputError(f"manifest.{field} 分母与 selected_count 不一致: {path}")

    metadata: dict[str, dict[str, Any]] = {}
    for field in ("instances", "selected_instances", "rows"):
        value = manifest.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            raise AnalysisInputError(f"manifest.{field} 必须是数组: {path}")
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get("instance_id"), str):
                raise AnalysisInputError(f"manifest.{field} 含无效逐题元数据: {path}")
            instance_id = item["instance_id"]
            if instance_id in metadata:
                raise AnalysisInputError(
                    f"manifest 逐题元数据重复 instance_id={instance_id}: {path}"
                )
            if instance_id not in ids:
                raise AnalysisInputError(
                    f"manifest 逐题元数据包含未知 instance_id={instance_id}: {path}"
                )
            metadata[instance_id] = {
                "repo": item.get("repo"),
                "difficulty": item.get("difficulty"),
            }
        break
    return list(ids), metadata


def _validate_manifest_aggregates(
    manifest: dict[str, Any],
    rows: Sequence[dict[str, Any]],
    path: Path | None,
    warnings: list[dict[str, Any]],
) -> None:
    for manifest_field, row_field in (
        ("repo_counts", "repo"),
        ("difficulty_counts", "difficulty"),
    ):
        expected = manifest.get(manifest_field)
        if not isinstance(expected, dict):
            continue
        values = [row.get(row_field) for row in rows]
        if any(value in (None, "") for value in values):
            warnings.append(
                _warning(
                    "manifest_aggregate_unchecked",
                    f"存在缺失逐题 {row_field}，无法核对 manifest.{manifest_field}。",
                    path=path,
                )
            )
            continue
        actual = Counter(str(value) for value in values)
        expected_counts = Counter({str(key): int(value) for key, value in expected.items()})
        if actual != expected_counts:
            raise AnalysisInputError(
                f"逐题 {row_field} 聚合与 manifest.{manifest_field} 不一致: {path}"
            )


def _index_report(report: dict[str, Any], path: Path) -> dict[str, Any]:
    required = (
        "submitted_ids",
        "completed_ids",
        "resolved_ids",
        "unresolved_ids",
        "empty_patch_ids",
        "error_ids",
    )
    missing = [field for field in required if field not in report]
    if missing:
        fields = ", ".join(missing)
        raise AnalysisInputError(f"report 缺少逐题 ID 数组（{fields}）: {path}")

    arrays: dict[str, list[str]] = {}
    for field in required:
        value = report.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise AnalysisInputError(f"report.{field} 必须是字符串数组: {path}")
        if len(set(value)) != len(value):
            raise AnalysisInputError(f"report.{field} 含重复 ID: {path}")
        arrays[field] = list(value)

    counts = (
        ("submitted_instances", "submitted_ids"),
        ("completed_instances", "completed_ids"),
        ("resolved_instances", "resolved_ids"),
        ("unresolved_instances", "unresolved_ids"),
        ("empty_patch_instances", "empty_patch_ids"),
        ("error_instances", "error_ids"),
    )
    for count_field, ids_field in counts:
        if count_field not in report:
            raise AnalysisInputError(f"report 缺少计数字段 {count_field}: {path}")
        if not _is_int(report[count_field]) or int(report[count_field]) != len(arrays[ids_field]):
            raise AnalysisInputError(f"report.{count_field} 与 {ids_field} 长度不一致: {path}")

    submitted = set(arrays["submitted_ids"])
    category_fields = ("resolved_ids", "unresolved_ids", "empty_patch_ids", "error_ids")
    categories = [set(arrays[field]) for field in category_fields]
    union: set[str] = set()
    for field, category in zip(category_fields, categories, strict=True):
        overlap = union & category
        if overlap:
            raise AnalysisInputError(f"report 结论类别重叠（{field}）: {path}")
        union.update(category)
    if union != submitted:
        raise AnalysisInputError(f"report 四类结论并集不等于 submitted_ids: {path}")

    completed = set(arrays["completed_ids"])
    resolved = set(arrays["resolved_ids"])
    unresolved = set(arrays["unresolved_ids"])
    if completed != resolved | unresolved:
        raise AnalysisInputError(
            f"report completed_ids 不等于 resolved_ids ∪ unresolved_ids: {path}"
        )

    outcomes: dict[str, str] = {}
    for field, outcome in (
        ("resolved_ids", "resolved"),
        ("unresolved_ids", "unresolved"),
        ("empty_patch_ids", "empty_patch"),
        ("error_ids", "harness_error"),
    ):
        for instance_id in arrays[field]:
            outcomes[instance_id] = outcome
    return {
        "valid": True,
        "submitted_ids": arrays["submitted_ids"],
        "outcomes": outcomes,
        "completed": completed,
        "reason": "",
    }


def _validate_id_set(actual: Sequence[str], expected: set[str], message: str) -> None:
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise AnalysisInputError(message)


def _scan_traces(
    trace_dirs: Sequence[Path], expected_ids: set[str], warnings: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not trace_dirs:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for directory in trace_dirs:
        paths = sorted(
            (path for path in directory.rglob("*.jsonl") if path.is_file()),
            key=lambda path: path.as_posix().casefold(),
        )
        for path in paths:
            events: list[dict[str, Any]] = []
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                warnings.append(_warning("trace_read_error", "trace 无法读取，已跳过。", path=path))
                continue
            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    events.append({"event": _INVALID_TRACE_EVENT, "line_number": line_number})
                    warnings.append(
                        _warning(
                            "trace_bad_json",
                            f"trace 第 {line_number} 行 JSON 无效，所选 run 将标为 invalid。",
                            path=path,
                        )
                    )
                    continue
                if not isinstance(value, dict):
                    events.append({"event": _INVALID_TRACE_EVENT, "line_number": line_number})
                    warnings.append(
                        _warning(
                            "trace_bad_event",
                            f"trace 第 {line_number} 行不是 object，所选 run 将标为 invalid。",
                            path=path,
                        )
                    )
                    continue
                events.append(value)
            runtime_ids = _runtime_ids(events)
            if len(runtime_ids) > 1:
                warnings.append(
                    _warning(
                        "trace_multiple_runtime_ids",
                        "trace 含多个不同 runtime instance_id，已跳过。",
                        path=path,
                    )
                )
                continue
            instance_id = next(iter(runtime_ids), "")
            if not instance_id:
                instance_id = path.stem
                warnings.append(
                    _warning(
                        "trace_filename_fallback",
                        "trace 缺少 runtime.payload.instance_id，使用文件名作为旧格式 fallback。",
                        instance_id=instance_id,
                        path=path,
                    )
                )
            elif instance_id != path.stem:
                warnings.append(
                    _warning(
                        "trace_runtime_filename_mismatch",
                        "trace 以 runtime.payload.instance_id 为权威映射，文件名仅作提示。",
                        instance_id=instance_id,
                        path=path,
                    )
                )
            if instance_id not in expected_ids:
                warnings.append(
                    _warning(
                        "trace_unknown_instance",
                        "trace instance 不在本批输入中，已忽略。",
                        instance_id=instance_id,
                        path=path,
                    )
                )
                continue
            if instance_id in index:
                raise AnalysisInputError(f"同一 instance 出现在多个 trace 文件/目录: {instance_id}")
            selected_events, complete = _select_trace_run(events, path, instance_id, warnings)
            malformed = any(event.get("event") == _INVALID_TRACE_EVENT for event in selected_events)
            selected_events = [
                event for event in selected_events if event.get("event") != _INVALID_TRACE_EVENT
            ]
            index[instance_id] = _trace_record(
                instance_id,
                path,
                selected_events,
                malformed=malformed or not complete,
            )
    missing = expected_ids - set(index)
    if missing:
        warnings.append(
            _warning(
                "trace_missing_instances",
                f"显式 trace 目录合计缺少 {len(missing)} 个本批 instance；对应指标保持 unmeasured。",
            )
        )
    return index


def _runtime_ids(events: Sequence[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        if event.get("event") != "runtime":
            continue
        payload = event.get("payload")
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("instance_id"), str)
            and payload["instance_id"].strip()
        ):
            ids.add(payload["instance_id"])
    return ids


def _select_trace_run(
    events: Sequence[dict[str, Any]],
    path: Path,
    instance_id: str,
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """选择 append-only trace 中最后一个完整 run，避免复跑数据串线。"""

    starts = [index for index, event in enumerate(events) if event.get("event") == "run_start"]
    if not starts:
        warnings.append(
            _warning(
                "trace_missing_run_start",
                "trace 没有 run_start，文件保留为 invalid 且不使用派生指标。",
                instance_id=instance_id,
                path=path,
            )
        )
        return list(events), False

    segments: list[tuple[list[dict[str, Any]], bool]] = []
    trailing_without_start: list[dict[str, Any]] | None = None
    for position, start in enumerate(starts):
        stop = len(events)
        if position + 1 < len(starts):
            next_start = starts[position + 1]
            next_runtime_indexes = [
                index
                for index in range(start + 1, next_start)
                if events[index].get("event") == "runtime"
            ]
            stop = next_runtime_indexes[-1] if next_runtime_indexes else next_start
        else:
            run_end_indexes = [
                index for index in range(start + 1, len(events)) if _is_valid_run_end(events[index])
            ]
            if run_end_indexes:
                trailing_runtime_indexes = [
                    index
                    for index in range(run_end_indexes[-1] + 1, len(events))
                    if events[index].get("event") == "runtime"
                ]
                if trailing_runtime_indexes:
                    stop = trailing_runtime_indexes[0]
                    trailing_without_start = list(events[stop:])
        segment = list(events[start:stop])
        run_id = events[start].get("run_id")
        runtime = _runtime_before_start(
            events,
            start,
            run_id if isinstance(run_id, str) and run_id else None,
        )
        if runtime is not None:
            segment.insert(0, runtime)
        run_ends = [event for event in segment if _is_valid_run_end(event)]
        segments.append((segment, len(run_ends) == 1))
    if trailing_without_start is not None:
        segments.append((trailing_without_start, False))

    complete_indexes = [index for index, (_, complete) in enumerate(segments) if complete]
    if len(segments) > 1:
        warnings.append(
            _warning(
                "trace_multiple_runs",
                f"trace 含 {len(segments)} 个 run 区间，按文件顺序选择最后一个完整 run。",
                instance_id=instance_id,
                path=path,
            )
        )
    if complete_indexes:
        selected = complete_indexes[-1]
        if selected < len(segments) - 1:
            warnings.append(
                _warning(
                    "trace_trailing_incomplete_run",
                    "trace 尾部 run 不完整，已回退到最后一个完整 run。",
                    instance_id=instance_id,
                    path=path,
                )
            )
        return segments[selected][0], True

    warnings.append(
        _warning(
            "trace_incomplete_run",
            "trace 没有带有效 status 的完整 run_end，文件保留为 invalid。",
            instance_id=instance_id,
            path=path,
        )
    )
    return segments[-1][0], False


def _is_valid_run_end(event: dict[str, Any]) -> bool:
    payload = event.get("payload")
    return bool(
        event.get("event") == "run_end"
        and isinstance(payload, dict)
        and isinstance(payload.get("status"), str)
        and payload["status"].strip()
    )


def _runtime_before_start(
    events: Sequence[dict[str, Any]], start: int, run_id: str | None
) -> dict[str, Any] | None:
    candidates = [event for event in events[:start] if event.get("event") == "runtime"]
    if run_id is not None:
        matching = [event for event in candidates if event.get("run_id") == run_id]
        if matching:
            return matching[-1]
    return candidates[-1] if candidates else None


def _trace_record(
    instance_id: str, path: Path, events: list[dict[str, Any]], malformed: bool
) -> dict[str, Any]:
    runtime = next((event for event in events if event.get("event") == "runtime"), None)
    run_end = next((event for event in reversed(events) if event.get("event") == "run_end"), None)
    runtime_payload = runtime.get("payload", {}) if isinstance(runtime, dict) else {}
    end_payload = run_end.get("payload", {}) if isinstance(run_end, dict) else {}
    metadata = (
        end_payload.get("metadata", {}) if isinstance(end_payload.get("metadata"), dict) else {}
    )
    status_raw = end_payload.get("status") if isinstance(end_payload, dict) else None
    step_events = [event for event in events if event.get("event") == "step"]
    tool_events = [event for event in events if event.get("event") == "tool_call"]
    action_events = [event for event in tool_events if isinstance(event.get("payload"), dict)]
    signatures: Counter[str] = Counter()
    direct_writes = 0
    mutation_calls = 0
    for event in action_events:
        payload = event["payload"]
        action = str(payload.get("action") or "")
        if action in {"edit_file", "create_file"}:
            direct_writes += 1
        if action in _MUTATION_CAPABLE_ACTIONS:
            mutation_calls += 1
        signature = json.dumps(
            {"action": action, "action_input": payload.get("action_input")},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        signatures[signature] += 1

    counters: dict[str, int | None] = {}
    for output_name, (metadata_key, event_name) in _TRACE_COUNTER_SOURCES.items():
        counters[output_name] = _counter_value(metadata, metadata_key, events, event_name)
    counters["replans"] = _counter_value(metadata, "replan_count", events, "replan")
    counters["parse_repairs"] = _optional_int(metadata.get("parse_repair_count"))
    counters["parse_error_context_omitted_count"] = _optional_int(
        metadata.get("parse_error_context_omitted_count")
    )
    counters["parse_error_context_omitted_chars"] = _optional_int(
        metadata.get("parse_error_context_omitted_chars")
    )

    verification_actions: list[dict[str, Any]] = []
    finish_step: int | None = None
    for index, event in enumerate(step_events, start=1):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        action = str(payload.get("action") or "")
        step_number = _optional_int(payload.get("step_number")) or index
        if action in _VERIFICATION_ACTIONS:
            verification_actions.append({"step_number": step_number, "action": action})
        if action in {"finish", "task_complete"} and finish_step is None:
            finish_step = step_number
    before_finish = bool(
        verification_actions
        and (
            finish_step is None
            or any(item["step_number"] < finish_step for item in verification_actions)
        )
    )
    if run_end is None or not isinstance(status_raw, str):
        verification_gap: bool | None = None
    else:
        verification_gap = status_raw == "success" and not before_finish

    repeated_signatures = sum(count - 1 for count in signatures.values() if count > 1)
    repeated_signature_count = sum(1 for count in signatures.values() if count > 1)
    return {
        "status": "invalid" if malformed else "measured",
        "path": str(path),
        "runtime_repo": runtime_payload.get("repo") if isinstance(runtime_payload, dict) else None,
        "agent_status": _normalize_agent_outcome(status_raw),
        "agent_status_raw": status_raw if isinstance(status_raw, str) else None,
        "failure": _safe_text(metadata.get("failure_reason")),
        "steps": len(step_events),
        "duration_seconds": _optional_number(end_payload.get("duration_seconds")),
        "replans": counters.pop("replans"),
        "counters": counters,
        "max_steps": status_raw == "max_steps_exceeded" if isinstance(status_raw, str) else None,
        "direct_write_calls": direct_writes,
        "mutation_capable_calls": mutation_calls,
        "repeated_tool_signature_count": repeated_signature_count,
        "repeated_tool_call_count": repeated_signatures,
        "verification_actions": verification_actions,
        "verification_before_finish": before_finish if run_end is not None else None,
        "verification_gap": verification_gap,
        "event_count": len(events),
        "json_malformed": malformed,
    }


def _counter_value(
    metadata: dict[str, Any], metadata_key: str, events: Sequence[dict[str, Any]], event_name: str
) -> int | None:
    if metadata_key in metadata:
        return _optional_int(metadata.get(metadata_key))
    event_count = sum(1 for event in events if event.get("event") == event_name)
    return event_count if event_count > 0 else None


def _scan_harness_details(
    directory: Path | None, expected_ids: set[str], warnings: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if directory is None:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for path in sorted(
        (path for path in directory.rglob("report.json") if path.is_file()),
        key=lambda path: path.as_posix().casefold(),
    ):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _store_invalid_detail(
                path,
                expected_ids,
                index,
                warnings,
                code="harness_detail_bad_json",
                message="逐题 harness detail JSON 无效，已隔离该实例。",
            )
            continue
        if not isinstance(value, dict):
            _store_invalid_detail(
                path,
                expected_ids,
                index,
                warnings,
                code="harness_detail_bad_shape",
                message="逐题 harness detail 顶层不是 object，已隔离该实例。",
            )
            continue
        for instance_id, detail in value.items():
            if not isinstance(instance_id, str):
                warnings.append(
                    _warning(
                        "harness_detail_bad_instance",
                        "逐题 harness detail 含无效 instance，已跳过。",
                        path=path,
                    )
                )
                continue
            if not isinstance(detail, dict):
                if instance_id in expected_ids:
                    if instance_id in index:
                        raise AnalysisInputError(
                            f"同一 instance 出现在多个 harness detail report: {instance_id}"
                        )
                    index[instance_id] = _invalid_detail_record(path)
                warnings.append(
                    _warning(
                        "harness_detail_bad_instance",
                        "逐题 harness detail instance 不是 object，已隔离该实例。",
                        instance_id=instance_id,
                        path=path,
                    )
                )
                continue
            if instance_id not in expected_ids:
                warnings.append(
                    _warning(
                        "harness_detail_unknown_instance",
                        "harness detail instance 不在本批输入中，已忽略。",
                        instance_id=instance_id,
                        path=path,
                    )
                )
                continue
            if instance_id in index:
                raise AnalysisInputError(
                    f"同一 instance 出现在多个 harness detail report: {instance_id}"
                )
            record = _detail_record(detail, path)
            if record.get("status") == "invalid":
                warnings.append(
                    _warning(
                        "harness_detail_invalid",
                        "逐题 harness detail 缺少可解释的 tests_status 计数。",
                        instance_id=instance_id,
                        path=path,
                    )
                )
            index[instance_id] = record
    return index


def _store_invalid_detail(
    path: Path,
    expected_ids: set[str],
    index: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
    *,
    code: str,
    message: str,
) -> None:
    instance_id = path.parent.name
    mapped_id = instance_id if instance_id in expected_ids else None
    warnings.append(_warning(code, message, instance_id=mapped_id, path=path))
    if mapped_id is None:
        return
    if mapped_id in index:
        raise AnalysisInputError(f"同一 instance 出现在多个 harness detail report: {mapped_id}")
    index[mapped_id] = _invalid_detail_record(path)


def _invalid_detail_record(path: Path) -> dict[str, Any]:
    return {
        "status": "invalid",
        "path": str(path),
        "patch_successfully_applied": None,
        "f2p_failed": None,
        "p2p_failed": None,
        "resolved": None,
    }


def _detail_record(detail: dict[str, Any], path: Path) -> dict[str, Any]:
    if detail.get("patch_successfully_applied") is False:
        return {
            "status": "patch_apply_failure",
            "path": str(path),
            "patch_successfully_applied": False,
            "f2p_failed": None,
            "p2p_failed": None,
        }
    tests_status = detail.get("tests_status")
    if not isinstance(tests_status, dict) or any(
        not isinstance(tests_status.get(axis), dict) for axis in _DETAIL_TEST_AXES
    ):
        return {
            "status": "invalid",
            "path": str(path),
            "patch_successfully_applied": _optional_bool(detail.get("patch_successfully_applied")),
            "f2p_failed": None,
            "p2p_failed": None,
        }
    f2p_failed = _list_length(tests_status["FAIL_TO_PASS"].get("failure"))
    p2p_failed = _list_length(tests_status["PASS_TO_PASS"].get("failure"))
    if f2p_failed is None or p2p_failed is None:
        status = "invalid"
    elif f2p_failed == 0 and p2p_failed == 0:
        status = "all_passed"
    elif f2p_failed > 0 and p2p_failed == 0:
        status = "f2p_only"
    elif f2p_failed > 0 and p2p_failed > 0:
        status = "f2p_and_p2p"
    else:
        status = "p2p_only"
    return {
        "status": status,
        "path": str(path),
        "patch_successfully_applied": _optional_bool(detail.get("patch_successfully_applied")),
        "f2p_failed": f2p_failed,
        "p2p_failed": p2p_failed,
        "resolved": _optional_bool(detail.get("resolved")),
    }


def _merge_instance(
    instance_id: str,
    prediction: dict[str, Any] | None,
    report: dict[str, Any],
    trace: dict[str, Any] | None,
    detail: dict[str, Any] | None,
    manifest_metadata: dict[str, Any] | None,
    trace_checked: bool,
    detail_checked: bool,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    prediction = prediction or {}
    official_outcome = report["outcomes"].get(instance_id) if report.get("valid") else "unknown"
    if report.get("valid") and instance_id not in report["outcomes"]:
        official_outcome = "incomplete"
    if detail is None:
        detail_status = "detail_unavailable" if detail_checked else "unmeasured"
        if detail_checked and official_outcome not in {"empty_patch", "unknown", "incomplete"}:
            warnings.append(
                _warning(
                    "harness_detail_missing",
                    "显式 harness detail 目录中缺少该实例的 report.json，detail 轴未测量。",
                    instance_id=instance_id,
                )
            )
    else:
        detail_status = detail.get("status", "invalid")

    repo, repo_source = _metadata_value(
        manifest_metadata,
        "repo",
        trace.get("runtime_repo") if trace and trace.get("status") == "measured" else None,
        _repo_from_instance_id(instance_id),
    )
    difficulty, difficulty_source = _metadata_difficulty(manifest_metadata, prediction)

    model_patch = prediction.get("model_patch")
    if model_patch is not None and not isinstance(model_patch, str):
        warnings.append(
            _warning(
                "prediction_bad_patch",
                "model_patch 不是字符串，patch 指标标为 unknown。",
                instance_id=instance_id,
            )
        )
        model_patch = None
    actual_chars = len(model_patch) if isinstance(model_patch, str) else None
    declared_chars = _optional_int(prediction.get("dm_patch_chars"))
    chars = actual_chars if actual_chars is not None else declared_chars
    chars_source = (
        "model_patch"
        if actual_chars is not None
        else ("declared" if declared_chars is not None else None)
    )
    mismatch = (
        actual_chars is not None and declared_chars is not None and actual_chars != declared_chars
    )
    if mismatch:
        warnings.append(
            _warning(
                "prediction_patch_chars_mismatch",
                "dm_patch_chars 与 model_patch 长度不一致，以 model_patch 为准。",
                instance_id=instance_id,
            )
        )
    patch_empty = None if model_patch is None else not bool(model_patch.strip())

    trace_status = (
        ("missing" if trace is None and trace_checked else "unmeasured")
        if trace is None
        else trace.get("status", "invalid")
    )
    agent = _merge_agent(prediction, trace)
    harness = {
        "status": detail_status,
        "patch_successfully_applied": detail.get("patch_successfully_applied") if detail else None,
        "f2p_failed": detail.get("f2p_failed") if detail else None,
        "p2p_failed": detail.get("p2p_failed") if detail else None,
        "resolved": detail.get("resolved") if detail else None,
        "path": detail.get("path") if detail else None,
    }
    trace_output = _trace_output(trace, trace_status)
    if patch_empty is not None and trace_output.get("status") == "measured":
        trace_output["direct_write_with_empty_patch_advisory"] = bool(
            patch_empty and _positive(trace_output.get("direct_write_calls"))
        )
        trace_output["no_observed_mutation_with_empty_patch_advisory"] = bool(
            patch_empty and trace_output.get("mutation_capable_calls") == 0
        )
    else:
        trace_output["direct_write_with_empty_patch_advisory"] = None
        trace_output["no_observed_mutation_with_empty_patch_advisory"] = None
    row: dict[str, Any] = {
        "instance_id": instance_id,
        "repo": repo,
        "repo_source": repo_source,
        "difficulty": difficulty,
        "difficulty_source": difficulty_source,
        "official": {
            "outcome": official_outcome,
            "completed": (
                instance_id in report.get("completed", set()) if report.get("valid") else None
            ),
        },
        "patch": {
            "is_empty": patch_empty,
            "chars": chars,
            "chars_source": chars_source,
            "declared_chars": declared_chars,
            "chars_mismatch": mismatch,
        },
        "harness_detail": harness,
        "agent": agent,
        "trace": trace_output,
    }
    row["failure_labels"] = _failure_labels(row)
    return row


def _metadata_value(
    manifest: dict[str, Any] | None,
    key: str,
    trace_value: Any,
    fallback: Any,
) -> tuple[str | None, str | None]:
    if manifest and isinstance(manifest.get(key), str) and manifest[key].strip():
        return manifest[key].strip(), "manifest"
    if isinstance(trace_value, str) and trace_value.strip():
        return trace_value.strip(), "trace"
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip(), "instance_id"
    return None, None


def _metadata_difficulty(
    manifest: dict[str, Any] | None, prediction: dict[str, Any]
) -> tuple[str | None, str | None]:
    if manifest and manifest.get("difficulty") not in (None, ""):
        return _optional_difficulty(manifest.get("difficulty")), "manifest"
    if prediction.get("dm_difficulty") not in (None, ""):
        return _optional_difficulty(prediction.get("dm_difficulty")), "prediction"
    return None, None


def _merge_agent(prediction: dict[str, Any], trace: dict[str, Any] | None) -> dict[str, Any]:
    diagnostics_version = _optional_int(prediction.get("dm_diagnostics_version"))
    prediction_diagnostics_measured = diagnostics_version == 1
    trace_measured = trace is not None and trace.get("status") == "measured"
    raw_status = prediction.get("dm_status")
    if not isinstance(raw_status, str) or not raw_status.strip():
        raw_status = trace.get("agent_status_raw") if trace_measured and trace else None
    outcome = _normalize_agent_outcome(raw_status)
    values: dict[str, Any] = {}
    trace_counters = trace.get("counters", {}) if trace_measured and trace else {}
    for output_name, prediction_name in _PREDICTION_DIAGNOSTICS.items():
        value = (
            _optional_number_or_int(prediction.get(prediction_name))
            if prediction_diagnostics_measured
            else None
        )
        if value is None and trace_measured and trace is not None:
            if output_name == "steps":
                value = trace.get("steps")
            elif output_name == "replans":
                value = trace.get("replans")
            else:
                value = trace_counters.get(output_name)
        values[output_name] = value
    prediction_duration = _optional_number(prediction.get("dm_duration_seconds"))
    trace_duration = trace.get("duration_seconds") if trace_measured and trace else None
    duration = prediction_duration if prediction_duration is not None else trace_duration
    failure = _safe_text(prediction.get("dm_failure"))
    if not failure and trace_measured and trace:
        failure = trace.get("failure") or None
    if prediction_diagnostics_measured or trace_measured:
        diagnostics_status = "measured"
    elif diagnostics_version is not None or trace is not None:
        diagnostics_status = "partial"
    else:
        diagnostics_status = "unmeasured"
    return {
        "outcome": outcome,
        "status_raw": raw_status if isinstance(raw_status, str) else None,
        "failure": failure or None,
        "diagnostics_version": diagnostics_version,
        "diagnostics_status": diagnostics_status,
        "steps": values.pop("steps"),
        "duration_seconds": duration,
        "prediction_duration_seconds": prediction_duration,
        "trace_duration_seconds": trace_duration,
        "replans": values.pop("replans"),
        "counters": values,
    }


def _trace_output(trace: dict[str, Any] | None, status: str) -> dict[str, Any]:
    if trace is None:
        return {
            "exists": None if status == "unmeasured" else False,
            "status": status,
            "path": None,
            "agent_status": None,
            "max_steps": None,
            "direct_write_calls": None,
            "mutation_capable_calls": None,
            "repeated_tool_signature_count": None,
            "repeated_tool_call_count": None,
            "verification_actions": None,
            "verification_before_finish": None,
            "verification_gap": None,
            "steps": None,
            "duration_seconds": None,
            "event_count": None,
            "counters": {key: None for key in _TRACE_EVENT_COUNTERS},
        }
    if status != "measured":
        return {
            "exists": True,
            "status": status,
            "path": trace.get("path"),
            "agent_status": None,
            "max_steps": None,
            "direct_write_calls": None,
            "mutation_capable_calls": None,
            "repeated_tool_signature_count": None,
            "repeated_tool_call_count": None,
            "verification_actions": None,
            "verification_before_finish": None,
            "verification_gap": None,
            "steps": None,
            "duration_seconds": None,
            "event_count": None,
            "counters": {key: None for key in _TRACE_EVENT_COUNTERS},
        }
    counters = dict(trace.get("counters", {}))
    return {
        "exists": True,
        "status": status,
        "path": trace.get("path"),
        "agent_status": trace.get("agent_status"),
        "max_steps": trace.get("max_steps"),
        "direct_write_calls": trace.get("direct_write_calls"),
        "mutation_capable_calls": trace.get("mutation_capable_calls"),
        "repeated_tool_signature_count": trace.get("repeated_tool_signature_count"),
        "repeated_tool_call_count": trace.get("repeated_tool_call_count"),
        "verification_actions": trace.get("verification_actions"),
        "verification_before_finish": trace.get("verification_before_finish"),
        "verification_gap": trace.get("verification_gap"),
        "steps": trace.get("steps"),
        "duration_seconds": trace.get("duration_seconds"),
        "event_count": trace.get("event_count"),
        "counters": counters,
    }


def _failure_labels(row: dict[str, Any]) -> list[str]:
    official = row["official"].get("outcome")
    patch = row["patch"]
    harness = row["harness_detail"]
    agent = row["agent"]
    trace = row["trace"]
    labels: set[str] = set()
    if official == "empty_patch" or patch.get("is_empty") is True:
        labels.add("empty_patch")
    if (
        patch.get("is_empty") is True
        and trace.get("status") == "measured"
        and trace.get("mutation_capable_calls") == 0
    ):
        labels.add("no_edit")
    if agent.get("outcome") == "max_steps":
        labels.add("max_steps")
    counters = agent.get("counters", {})
    if _positive(counters.get("parse_errors")):
        labels.add("parse_error")
    if any(
        _positive(counters.get(name))
        for name in ("edit_guard_blocks", "repeat_search_blocks", "edit_cycle_blocks")
    ):
        labels.add("guard_block")
    if harness.get("status") in {"f2p_only", "f2p_and_p2p"}:
        labels.add("f2p_unresolved")
    if harness.get("status") in {"f2p_and_p2p", "p2p_only"}:
        labels.add("p2p_regression")
    if official == "harness_error":
        labels.add("harness_error")
    if (
        official in {"unknown", "incomplete"}
        or agent.get("outcome") == "unknown"
        or (
            official == "unresolved"
            and harness.get("status") in {"detail_unavailable", "unmeasured", "invalid"}
        )
    ):
        labels.add("unknown")
    return [label for label in FAILURE_LABELS if label in labels]


def _summarize_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    return {
        "denominator": denominator,
        "official_outcomes": _axis_counts(
            (row.get("official", {}).get("outcome") for row in rows), OFFICIAL_OUTCOMES
        ),
        "harness_details": _axis_counts(
            (row.get("harness_detail", {}).get("status") for row in rows),
            HARNESS_DETAIL_STATUSES,
        ),
        "agent_outcomes": _axis_counts(
            (row.get("agent", {}).get("outcome") for row in rows), AGENT_OUTCOMES
        ),
        "trace_statuses": _axis_counts(
            (row.get("trace", {}).get("status") for row in rows), TRACE_STATUSES
        ),
        "failure_labels": _count_labels(rows),
        "patch": {
            "empty_count": sum(1 for row in rows if row.get("patch", {}).get("is_empty") is True),
            "nonempty_count": sum(
                1 for row in rows if row.get("patch", {}).get("is_empty") is False
            ),
            "unmeasured_count": sum(
                1 for row in rows if row.get("patch", {}).get("is_empty") is None
            ),
            "chars": _numeric_metric(rows, "patch", "chars"),
        },
        "agent_metrics": {
            name: _numeric_metric(rows, "agent", name)
            for name in (
                "steps",
                "duration_seconds",
                "replans",
                "parse_errors",
                "parse_repairs",
                "parse_error_context_omitted_count",
                "parse_error_context_omitted_chars",
                "truncations",
                "edit_guard_blocks",
                "edit_noops",
                "repeat_search_blocks",
                "edit_state_revisits",
                "edit_cycle_blocks",
            )
        },
        "trace": {
            "max_steps": _boolean_metric(rows, "trace", "max_steps"),
            "direct_write_calls": _numeric_metric(rows, "trace", "direct_write_calls"),
            "mutation_capable_calls": _numeric_metric(rows, "trace", "mutation_capable_calls"),
            "repeated_tool_signature_count": _numeric_metric(
                rows, "trace", "repeated_tool_signature_count"
            ),
            "repeated_tool_call_count": _numeric_metric(rows, "trace", "repeated_tool_call_count"),
            "verification_gap": _boolean_metric(rows, "trace", "verification_gap"),
        },
    }


def _facet_summaries(
    rows: Sequence[dict[str, Any]], section: str, field: str | None = None
) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value: Any = row.get(section)
        if field is not None and isinstance(value, dict):
            value = value.get(field)
        key = str(value) if value not in (None, "") else "unknown"
        buckets.setdefault(key, []).append(row)
    return {key: _summarize_rows(buckets[key]) for key in sorted(buckets)}


def _label_summaries(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    result: dict[str, Any] = {}
    for label in FAILURE_LABELS:
        matched = [row for row in rows if label in row.get("failure_labels", [])]
        result[label] = {
            "count": len(matched),
            "denominator": denominator,
            "official_outcomes": _axis_counts(
                (row.get("official", {}).get("outcome") for row in matched),
                OFFICIAL_OUTCOMES,
            ),
        }
    return result


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for value in values:
        key = str(value) if value not in (None, "") else "unknown"
        counter[key] += 1
    return {key: counter[key] for key in sorted(counter)}


def _axis_counts(values: Iterable[Any], known_order: Sequence[str]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for value in values:
        key = str(value) if value not in (None, "") else "unknown"
        counter[key] += 1
    counts = {key: counter.get(key, 0) for key in known_order}
    for key in sorted(set(counter) - set(known_order)):
        counts[key] = counter[key]
    return counts


def _count_labels(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {label: 0 for label in FAILURE_LABELS}
    for row in rows:
        for label in row.get("failure_labels", []):
            counts[label] = counts.get(label, 0) + 1
    return {key: counts[key] for key in FAILURE_LABELS}


def _numeric_metric(rows: Sequence[dict[str, Any]], section: str, field: str) -> dict[str, Any]:
    values: list[float] = []
    for row in rows:
        section_value = row.get(section, {})
        if section == "agent" and isinstance(section_value, dict):
            counters = section_value.get("counters", {})
            value = counters.get(field) if field in counters else section_value.get(field)
        else:
            value = section_value.get(field) if isinstance(section_value, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        values.append(float(value))
    total: int | float | None
    if not values:
        total = None
    elif all(value.is_integer() for value in values):
        total = int(sum(values))
    else:
        total = round(sum(values), 6)
    return {
        "sum": total,
        "measured_count": len(values),
        "unmeasured_count": len(rows) - len(values),
        "denominator": len(rows),
    }


def _boolean_metric(rows: Sequence[dict[str, Any]], section: str, field: str) -> dict[str, Any]:
    values = [row.get(section, {}).get(field) for row in rows]
    true_count = sum(value is True for value in values)
    false_count = sum(value is False for value in values)
    measured = true_count + false_count
    return {
        "true_count": true_count,
        "false_count": false_count,
        "unmeasured_count": len(rows) - measured,
        "measured_count": measured,
        "denominator": len(rows),
    }


def _optional_difficulty(value: Any) -> str | None:
    if value is None or not isinstance(value, (str, int, float)) or not str(value).strip():
        return None
    return normalize_difficulty(value)


def _repo_from_instance_id(instance_id: str) -> str | None:
    if "__" not in instance_id:
        return None
    owner, repository_with_issue = instance_id.split("__", 1)
    repository, separator, issue = repository_with_issue.rpartition("-")
    if not owner or not repository or not separator or not issue:
        return None
    return f"{owner}/{repository}"


def _normalize_agent_outcome(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    lowered = value.strip().lower()
    if lowered in {"success", "ok", "completed"}:
        return "success"
    if lowered in {"max_steps", "max_steps_exceeded", "max-step", "max steps"}:
        return "max_steps"
    if "exception" in lowered or lowered in {"error", "failed"}:
        return "exception"
    return "unknown"


def _safe_text(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    text = value.replace("\r", " ").replace("\n", " ").strip()
    for name, secret in os.environ.items():
        if len(secret) >= 6 and any(
            marker in name.upper()
            for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        ):
            text = text.replace(secret, f"<redacted-env:{name}>")
    home = str(Path.home())
    if home:
        text = text.replace(home, "~")
    text = re.sub(
        r"(?i)\b(?:FAIL_TO_PASS|PASS_TO_PASS)(?:\s*[:=]\s*[^\s,;]+|\s+[A-Za-z0-9_.:/-]+)?",
        "<redacted-test-field>",
        text,
    )
    text = re.sub(
        r"(?i)(api[_-]?key|token|secret|password)(\s*[=:]\s*)[^\s,;]+", r"\1\2<redacted>", text
    )
    text = re.sub(r"(?i)(bearer\s+)[a-z0-9._-]+", r"\1<redacted>", text)
    text = re.sub(
        r"(?i)([?&](?:access_token|api[_-]?key|token|secret|password)=)[^&\s]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(r"(?i)\b(?:sk|rk)-[a-z0-9_-]{8,}\b", "<redacted-secret>", text)
    text = re.sub(r"\bgh[pousr]_[0-9A-Za-z]{8,}\b", "<redacted-secret>", text)
    text = re.sub(r"(?i)\bxox[baprs]-[a-z0-9_-]{8,}\b", "<redacted-secret>", text)
    text = re.sub(r"\bAIza[0-9A-Za-z_-]{20,}\b", "<redacted-secret>", text)
    text = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "<redacted-secret>", text)
    return text[:limit]


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _optional_number_or_int(value: Any) -> int | float | None:
    return _optional_number(value)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _list_length(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _warning(
    code: str,
    message: str,
    *,
    instance_id: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "instance_id": instance_id,
        "path": str(path) if path is not None else None,
    }


def _sorted_warnings(warnings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        warnings,
        key=lambda item: (
            str(item.get("code") or ""),
            str(item.get("instance_id") or ""),
            str(item.get("path") or ""),
            str(item.get("message") or ""),
        ),
    )


def _scope_items(summary: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    preferred = [key for key in ("all",) if key in summary]
    preferred.extend(
        key for key in summary if key.startswith("prefix_") or key.startswith("remainder_")
    )
    return [(key, summary[key]) for key in preferred]


def _metric_cell(metric: dict[str, Any] | None) -> str:
    if not metric:
        return "—"
    total = metric.get("sum")
    measured = metric.get("measured_count", 0)
    denominator = metric.get("denominator", 0)
    return f"{_value(total)} ({measured}/{denominator})"


def _facet_row(key: str, bucket: dict[str, Any]) -> str:
    official = bucket.get("official_outcomes", {})
    labels = (
        ", ".join(
            f"{label}={count}" for label, count in bucket.get("failure_labels", {}).items() if count
        )
        or "—"
    )
    return "| {key} | {denom} | {resolved} | {unresolved} | {empty} | {labels} |".format(
        key=_md(key),
        denom=_value(bucket.get("denominator")),
        resolved=_value(official.get("resolved", 0)),
        unresolved=_value(official.get("unresolved", 0)),
        empty=_value(official.get("empty_patch", 0)),
        labels=_md(labels),
    )


def _value(value: Any) -> str:
    return "—" if value is None else str(value)


def _md(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").replace("`", "' ")


def _write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
