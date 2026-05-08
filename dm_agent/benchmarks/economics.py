"""Token economics helpers for benchmark reports.

The module is intentionally offline-only: it reads existing JSON benchmark reports
and never calls providers, price APIs, or SWE-bench infrastructure.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class EconomicsEntry:
    """One report-level cost/performance row."""

    label: str
    suite: str
    provider: str
    model: str
    total_runs: int
    successes: int
    pass_rate: float
    pass_rate_ci_95: Dict[str, float]
    total_estimated_tokens: int
    cost_per_1k_tokens: Optional[float]
    estimated_cost_usd: Optional[float]
    cost_per_success_usd: Optional[float]
    avg_tokens_per_run: float
    tokens_per_success: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "suite": self.suite,
            "provider": self.provider,
            "model": self.model,
            "total_runs": self.total_runs,
            "successes": self.successes,
            "pass_rate": self.pass_rate,
            "pass_rate_ci_95": self.pass_rate_ci_95,
            "total_estimated_tokens": self.total_estimated_tokens,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "cost_per_success_usd": self.cost_per_success_usd,
            "avg_tokens_per_run": self.avg_tokens_per_run,
            "tokens_per_success": self.tokens_per_success,
        }


def summarize_report(
    report: Dict[str, Any],
    *,
    label: str = "",
    cost_per_1k_tokens: Optional[float] = None,
) -> EconomicsEntry:
    """Summarize one benchmark report into a cost/performance row."""

    suite = str(report.get("suite") or report.get("mode") or "unknown")
    summary = report.get("summary") or {}
    results = list(report.get("results") or [])
    total_runs = int(summary.get("total_runs") or summary.get("total") or len(results))
    successes = _success_count(report, summary, total_runs)
    pass_rate = _safe_rate(successes, total_runs)
    pass_rate_ci = _pass_rate_ci(summary, successes, total_runs)
    total_tokens = _total_tokens(results, summary)
    configured_cost = _resolve_cost_per_1k(report, cost_per_1k_tokens)
    total_cost = _total_cost(results, total_tokens, configured_cost)
    cost_per_success = (total_cost / successes) if total_cost is not None and successes else None
    tokens_per_success = (total_tokens / successes) if successes else None

    return EconomicsEntry(
        label=label or _default_label(report),
        suite=suite,
        provider=str(report.get("provider") or ""),
        model=str(report.get("model") or ""),
        total_runs=total_runs,
        successes=successes,
        pass_rate=pass_rate,
        pass_rate_ci_95=pass_rate_ci,
        total_estimated_tokens=total_tokens,
        cost_per_1k_tokens=configured_cost,
        estimated_cost_usd=total_cost,
        cost_per_success_usd=cost_per_success,
        avg_tokens_per_run=(total_tokens / total_runs) if total_runs else 0.0,
        tokens_per_success=tokens_per_success,
    )


def build_economics_report(
    reports: Sequence[Dict[str, Any]],
    *,
    labels: Optional[Sequence[str]] = None,
    cost_per_1k_tokens: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a deterministic economics report from existing benchmark JSON payloads."""

    labels = labels or []
    entries = [
        summarize_report(
            report,
            label=labels[index] if index < len(labels) else "",
            cost_per_1k_tokens=cost_per_1k_tokens,
        )
        for index, report in enumerate(reports)
    ]
    ranked = sorted(
        entries,
        key=lambda item: (
            item.cost_per_success_usd is None,
            item.cost_per_success_usd if item.cost_per_success_usd is not None else float("inf"),
            -item.pass_rate,
            item.label,
        ),
    )
    return {
        "mode": "benchmark_economics",
        "summary": {
            "reports": len(entries),
            "best_cost_per_success": (
                ranked[0].label if ranked and ranked[0].cost_per_success_usd is not None else ""
            ),
            "best_pass_rate": max((entry.pass_rate for entry in entries), default=0.0),
        },
        "entries": [entry.to_dict() for entry in entries],
        "ranking": [entry.label for entry in ranked],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    """Render :func:`build_economics_report` output as Markdown."""

    lines = [
        "# Benchmark Token Economics",
        "",
        "This report is generated from existing benchmark JSON files. It does not run "
        "live models, SWE-bench, or external price lookups.",
        "",
        "| Label | Suite | Provider | Model | Pass rate (95% CI) | Runs | Avg tokens | Tokens/success | Estimated cost | Cost/success |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in report.get("entries", []):
        lines.append(
            "| {label} | {suite} | {provider} | {model} | {pass_rate} | {total_runs} | "
            "{avg_tokens_per_run:.0f} | {tokens_per_success} | {estimated_cost} | "
            "{cost_per_success} |".format(
                label=entry.get("label", ""),
                suite=entry.get("suite", ""),
                provider=entry.get("provider", ""),
                model=entry.get("model", ""),
                pass_rate=_format_rate_with_ci(
                    entry.get("pass_rate"),
                    entry.get("pass_rate_ci_95"),
                ),
                total_runs=int(entry.get("total_runs", 0)),
                avg_tokens_per_run=float(entry.get("avg_tokens_per_run", 0.0)),
                tokens_per_success=_format_number(entry.get("tokens_per_success"), decimals=0),
                estimated_cost=_format_usd(entry.get("estimated_cost_usd")),
                cost_per_success=_format_usd(entry.get("cost_per_success_usd")),
            )
        )

    ranking = report.get("ranking") or []
    if ranking:
        lines.extend(["", "## Cost-per-success ranking", ""])
        for index, label in enumerate(ranking, start=1):
            lines.append(f"{index}. `{label}`")
    return "\n".join(lines) + "\n"


def load_json_reports(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    reports = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            reports.append(json.load(handle))
    return reports


def write_economics_report(report: Dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize token economics from reports.")
    parser.add_argument("reports", nargs="+", type=Path, help="Benchmark JSON report paths.")
    parser.add_argument("--label", action="append", help="Optional label for each report.")
    parser.add_argument("--output-json", type=Path, default=Path("bench_reports/economics.json"))
    parser.add_argument("--output-md", type=Path, default=Path("bench_reports/economics.md"))
    parser.add_argument(
        "--cost-per-1k-tokens",
        type=float,
        help="Override report prices with one explicit USD cost per 1K tokens.",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    report = build_economics_report(
        load_json_reports(args.reports),
        labels=args.label,
        cost_per_1k_tokens=args.cost_per_1k_tokens,
    )
    write_economics_report(report, json_path=args.output_json, markdown_path=args.output_md)
    print(render_markdown(report))
    return 0


def _success_count(report: Dict[str, Any], summary: Dict[str, Any], total_runs: int) -> int:
    if "resolved" in summary:
        return int(summary.get("resolved") or 0)
    if "overall_pass_rate" in summary:
        return int(round(float(summary.get("overall_pass_rate") or 0.0) * total_runs))
    return sum(1 for result in report.get("results", []) if result.get("success"))


def _total_tokens(results: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> int:
    if "total_estimated_tokens" in summary:
        return int(summary.get("total_estimated_tokens") or 0)
    return sum(int(result.get("estimated_tokens") or 0) for result in results)


def _resolve_cost_per_1k(report: Dict[str, Any], override: Optional[float]) -> Optional[float]:
    if override is not None:
        return override
    economics = report.get("token_economics") or {}
    value = economics.get("cost_per_1k_tokens")
    if value is None:
        return None
    value = float(value)
    return value if value > 0 else None


def _pass_rate_ci(
    summary: Dict[str, Any],
    successes: int,
    total_runs: int,
) -> Dict[str, float]:
    interval = summary.get("overall_pass_rate_ci_95")
    if isinstance(interval, dict) and {"low", "high"} <= set(interval):
        return {
            "low": float(interval.get("low", 0.0)),
            "high": float(interval.get("high", 0.0)),
        }
    return _wilson_interval(successes, total_runs)


def _total_cost(
    results: Sequence[Dict[str, Any]],
    total_tokens: int,
    cost_per_1k_tokens: Optional[float],
) -> Optional[float]:
    explicit = sum(float(result.get("estimated_cost_usd") or 0.0) for result in results)
    if explicit > 0:
        return explicit
    if cost_per_1k_tokens is None:
        return None
    return (total_tokens / 1000.0) * cost_per_1k_tokens


def _default_label(report: Dict[str, Any]) -> str:
    provider = str(report.get("provider") or "unknown")
    model = str(report.get("model") or "unknown")
    suite = str(report.get("suite") or report.get("mode") or "benchmark")
    return f"{suite}:{provider}:{model}"


def _safe_rate(successes: int, total: int) -> float:
    return (successes / total) if total else 0.0


def _wilson_interval(successes: int, total: int, *, z: float = 1.96) -> Dict[str, float]:
    if total <= 0:
        return {"low": 0.0, "high": 0.0}
    phat = successes / total
    denominator = 1 + (z * z / total)
    centre = phat + (z * z / (2 * total))
    margin = z * ((phat * (1 - phat) + (z * z / (4 * total))) / total) ** 0.5
    return {
        "low": max(0.0, (centre - margin) / denominator),
        "high": min(1.0, (centre + margin) / denominator),
    }


def _format_rate_with_ci(rate: Any, interval: Any) -> str:
    value = 0.0 if rate is None else float(rate)
    if not isinstance(interval, dict):
        return f"{value:.1%}"
    low = float(interval.get("low", 0.0))
    high = float(interval.get("high", 0.0))
    return f"{value:.1%} [{low:.1%}-{high:.1%}]"


def _format_usd(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"${float(value):.4f}"


def _format_number(value: Any, *, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{decimals}f}"


if __name__ == "__main__":
    raise SystemExit(main())
