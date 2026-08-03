"""离线对比两份 benchmark 报告：分数差、逐题翻转、token 成本。

这是「改了策略之后到底有没有变好」的判据。只读已有的 JSON 报告，
不跑 benchmark、不调模型、不联网——和 ``manifest_diff`` 同样是纯离线工具。

三条设计约定：

- **逐题翻转比总分更有指导性**。总分从 0.46 变 0.54 只说明「多过了一题」，
  而「哪题修好了、哪题跑坏了」才指向下一步该看什么。回归（原本过、现在挂）
  永远单独列出，即使总分上升。
- **噪声口径直接印在输出里**。13 题规模下一题翻转就是 ±7.7 个百分点，
  不写出来的话这个分会骗人——看到 +7.7% 会以为是改进，其实是一题的抖动。
- **manifest 不兼容时拒绝比较**。两份报告如果任务集不同，分数差没有意义。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 低于这个翻转数的差异不构成证据（见模块文档第二条）。
NOISE_FLIP_THRESHOLD = 2


@dataclass(frozen=True)
class TaskFlip:
    """一道题在两份报告间的 pass/fail 变化。"""

    task_id: str
    variant: str
    before: bool
    after: bool

    @property
    def is_fix(self) -> bool:
        return self.after and not self.before

    @property
    def is_regression(self) -> bool:
        return self.before and not self.after


@dataclass(frozen=True)
class ScoreComparison:
    """两份 benchmark 报告的结构化对比。"""

    comparable: bool
    incomparable_reason: str
    left_label: str
    right_label: str
    left_pass_rate: float
    right_pass_rate: float
    left_passed: int
    right_passed: int
    total: int
    fixes: list[TaskFlip] = field(default_factory=list)
    regressions: list[TaskFlip] = field(default_factory=list)
    left_tokens: int = 0
    right_tokens: int = 0
    left_cost_usd: float = 0.0
    right_cost_usd: float = 0.0

    @property
    def pass_rate_delta(self) -> float:
        return self.right_pass_rate - self.left_pass_rate

    @property
    def flip_count(self) -> int:
        return len(self.fixes) + len(self.regressions)

    @property
    def within_noise(self) -> bool:
        """翻转数低于阈值时，差异不构成证据。"""
        return self.flip_count < NOISE_FLIP_THRESHOLD

    @property
    def per_task_points(self) -> float:
        """一题翻转对应多少个百分点——噪声口径的分母。"""
        return 100.0 / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparable": self.comparable,
            "incomparable_reason": self.incomparable_reason,
            "left_label": self.left_label,
            "right_label": self.right_label,
            "total": self.total,
            "left_passed": self.left_passed,
            "right_passed": self.right_passed,
            "left_pass_rate": self.left_pass_rate,
            "right_pass_rate": self.right_pass_rate,
            "pass_rate_delta": self.pass_rate_delta,
            "flip_count": self.flip_count,
            "within_noise": self.within_noise,
            "per_task_points": self.per_task_points,
            "fixes": [{"task_id": flip.task_id, "variant": flip.variant} for flip in self.fixes],
            "regressions": [
                {"task_id": flip.task_id, "variant": flip.variant} for flip in self.regressions
            ],
            "left_tokens": self.left_tokens,
            "right_tokens": self.right_tokens,
            "left_cost_usd": self.left_cost_usd,
            "right_cost_usd": self.right_cost_usd,
        }


def _outcomes(report: dict[str, Any]) -> dict[tuple[str, str], bool]:
    """把报告压成 ``(task_id, variant) -> success``。

    同一 (task, variant) 有多次 repeat 时按「全过才算过」聚合：repeat 存在的
    意义就是暴露不稳定，任意一次挂掉就不该记成通过。
    """
    outcomes: dict[tuple[str, str], bool] = {}
    for result in report.get("results", []):
        key = (str(result.get("task_id", "")), str(result.get("variant", "")))
        success = bool(result.get("success"))
        outcomes[key] = success if key not in outcomes else (outcomes[key] and success)
    return outcomes


def _manifest_signature(report: dict[str, Any]) -> str:
    manifest = report.get("manifest")
    if isinstance(manifest, dict):
        return str(manifest.get("suite_signature", ""))
    return ""


def _totals(report: dict[str, Any]) -> tuple[int, float]:
    tokens = sum(int(r.get("estimated_tokens", 0) or 0) for r in report.get("results", []))
    cost = sum(float(r.get("estimated_cost_usd", 0.0) or 0.0) for r in report.get("results", []))
    return tokens, cost


def compare_reports(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_label: str = "before",
    right_label: str = "after",
) -> ScoreComparison:
    """对比两份报告。任务集不同时返回 ``comparable=False``。"""
    left_outcomes = _outcomes(left)
    right_outcomes = _outcomes(right)
    shared = sorted(set(left_outcomes) & set(right_outcomes))

    reason = ""
    left_sig, right_sig = _manifest_signature(left), _manifest_signature(right)
    if left_sig and right_sig and left_sig != right_sig:
        reason = (
            f"任务集不同（suite_signature {left_sig} vs {right_sig}）；"
            "分数差无意义，先用 dm-agent-manifest-diff 查清漂移。"
        )
    elif not shared:
        reason = "两份报告没有共同的 (task_id, variant)，无法对比。"

    left_tokens, left_cost = _totals(left)
    right_tokens, right_cost = _totals(right)

    if reason:
        return ScoreComparison(
            comparable=False,
            incomparable_reason=reason,
            left_label=left_label,
            right_label=right_label,
            left_pass_rate=0.0,
            right_pass_rate=0.0,
            left_passed=0,
            right_passed=0,
            total=0,
            left_tokens=left_tokens,
            right_tokens=right_tokens,
            left_cost_usd=left_cost,
            right_cost_usd=right_cost,
        )

    fixes: list[TaskFlip] = []
    regressions: list[TaskFlip] = []
    left_passed = right_passed = 0
    for task_id, variant in shared:
        before = left_outcomes[(task_id, variant)]
        after = right_outcomes[(task_id, variant)]
        left_passed += int(before)
        right_passed += int(after)
        if before != after:
            flip = TaskFlip(task_id=task_id, variant=variant, before=before, after=after)
            (fixes if flip.is_fix else regressions).append(flip)

    total = len(shared)
    return ScoreComparison(
        comparable=True,
        incomparable_reason="",
        left_label=left_label,
        right_label=right_label,
        left_pass_rate=left_passed / total,
        right_pass_rate=right_passed / total,
        left_passed=left_passed,
        right_passed=right_passed,
        total=total,
        fixes=fixes,
        regressions=regressions,
        left_tokens=left_tokens,
        right_tokens=right_tokens,
        left_cost_usd=left_cost,
        right_cost_usd=right_cost,
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _delta_tokens(before: int, after: int) -> str:
    if before == 0:
        return f"{after:,}"
    ratio = (after - before) / before * 100
    return f"{after:,} ({ratio:+.1f}%)"


def render_markdown(comparison: ScoreComparison) -> str:
    lines = ["# Benchmark Score Comparison", ""]
    lines.append(f"- Left (`{comparison.left_label}`) vs Right (`{comparison.right_label}`)")

    if not comparison.comparable:
        lines += ["", f"**无法对比**：{comparison.incomparable_reason}", ""]
        return "\n".join(lines)

    lines += [
        f"- Tasks compared: `{comparison.total}`",
        f"- Pass rate: `{_pct(comparison.left_pass_rate)}` → "
        f"`{_pct(comparison.right_pass_rate)}` "
        f"(**{comparison.pass_rate_delta * 100:+.1f} pts**)",
        f"- Passed: `{comparison.left_passed}` → `{comparison.right_passed}`",
        f"- Tokens: `{comparison.left_tokens:,}` → "
        f"`{_delta_tokens(comparison.left_tokens, comparison.right_tokens)}`",
    ]
    if comparison.left_cost_usd or comparison.right_cost_usd:
        lines.append(
            f"- Estimated cost: `${comparison.left_cost_usd:.4f}` → "
            f"`${comparison.right_cost_usd:.4f}`"
        )

    lines += ["", "## Verdict", ""]
    if comparison.flip_count == 0:
        lines.append("**No task changed outcome.** 这次改动没有影响任何一道题的判定。")
    elif comparison.within_noise:
        lines.append(
            f"**在噪声范围内**：只有 {comparison.flip_count} 道题翻转，"
            f"而本套件一题 = {comparison.per_task_points:.1f} 个百分点。"
            f"少于 {NOISE_FLIP_THRESHOLD} 题的差异**不构成策略有效的证据**——"
            "同一配置重跑也可能得到这个差。"
        )
    else:
        lines.append(
            f"{comparison.flip_count} 道题翻转（一题 = {comparison.per_task_points:.1f} 个百分点）。"
        )
    if comparison.regressions:
        lines.append("")
        lines.append(
            f"**注意：有 {len(comparison.regressions)} 道题从通过变为失败**，"
            "即使总分上升也要先看这些。"
        )

    if comparison.fixes:
        lines += ["", "## Fixed (fail → pass)", ""]
        lines += [f"- `{f.task_id}` / `{f.variant}`" for f in comparison.fixes]
    if comparison.regressions:
        lines += ["", "## Regressed (pass → fail)", ""]
        lines += [f"- `{f.task_id}` / `{f.variant}`" for f in comparison.regressions]

    lines.append("")
    return "\n".join(lines)


def load_report(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a benchmark report object.")
    return data


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two DM-Code-Agent benchmark reports (offline, no model calls)."
    )
    parser.add_argument("left", type=Path, help="Baseline report JSON.")
    parser.add_argument("right", type=Path, help="New report JSON.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    args = parser.parse_args(argv)

    try:
        left = load_report(args.left)
        right = load_report(args.right)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Failed to load reports: {exc}", file=sys.stderr)
        return 2

    comparison = compare_reports(
        left, right, left_label=args.left.name, right_label=args.right.name
    )
    if args.json:
        print(json.dumps(comparison.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(comparison))

    if not comparison.comparable:
        return 2
    # 有回归就非零退出，方便挂进 CI 或脚本。
    return 1 if comparison.regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
