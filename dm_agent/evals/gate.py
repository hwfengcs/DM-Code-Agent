"""CI quality gate for deterministic eval reports.

Reads a JSON report produced by ``dm-agent-eval --output`` and exits non-zero
when the success rates fall below the thresholds. Keyless and offline: it
never runs the agent, it only checks an existing report.

Usage:
    python -m dm_agent.evals.gate eval_reports/ci-report.json --min-success-rate 1.0
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, TypeGuard

from .validation import report_results


def evaluate_gate(
    report: dict[str, Any],
    *,
    min_success_rate: float,
    min_variant_rate: float,
) -> list[str]:
    """Return a list of human-readable violations (empty when the gate passes)."""
    violations = [
        f"{name} must be a finite number between 0 and 1"
        for name, value in (
            ("min_success_rate", min_success_rate),
            ("min_variant_rate", min_variant_rate),
        )
        if not _valid_rate(value)
    ]
    if violations:
        return violations
    try:
        results = report_results(report)
    except ValueError as exc:
        return [str(exc)]
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return ["report has no summary object"]

    overall = summary.get("overall_success_rate")
    if not _valid_rate(overall):
        violations.append("summary.overall_success_rate must be a finite number between 0 and 1")
    elif overall < min_success_rate:
        violations.append(
            f"overall_success_rate {overall:.3f} is below the required {min_success_rate:.3f}"
        )

    variants = summary.get("variants")
    if not isinstance(variants, dict) or not variants:
        violations.append("summary.variants must be a non-empty object")
        variants = {}
    for name, data in sorted(variants.items()):
        rate = data.get("success_rate") if isinstance(data, dict) else None
        if not _valid_rate(rate):
            violations.append(
                f"variant '{name}' success_rate must be a finite number between 0 and 1"
            )
        elif rate < min_variant_rate:
            violations.append(
                f"variant '{name}' success_rate {rate:.3f} "
                f"is below the required {min_variant_rate:.3f}"
            )

    actual_overall = sum(result["success"] for result in results) / len(results)
    if _valid_rate(overall) and not math.isclose(overall, actual_overall, abs_tol=1e-9):
        violations.append("summary.overall_success_rate disagrees with results")
    result_variants = {result["variant"] for result in results}
    if set(variants) != result_variants:
        violations.append("summary variants disagree with results")
    for name in result_variants:
        group = [result for result in results if result["variant"] == name]
        actual = sum(result["success"] for result in group) / len(group)
        data = variants.get(name)
        rate = data.get("success_rate") if isinstance(data, dict) else None
        if _valid_rate(rate) and not math.isclose(rate, actual, abs_tol=1e-9):
            violations.append(f"variant '{name}' success_rate disagrees with results")
    if violations:
        for result in results:
            if isinstance(result, dict) and not result.get("success"):
                violations.append(
                    f"failed: {result.get('variant', '?')}/{result.get('task_id', '?')}: "
                    f"{result.get('failure_reason', '')}"
                )
    return violations


def _valid_rate(value: Any) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Quality gate for eval JSON reports.")
    parser.add_argument("report", type=Path, help="Path to the eval JSON report.")
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=1.0,
        help="Minimum overall success rate (default: 1.0 — deterministic suite must be green).",
    )
    parser.add_argument(
        "--min-variant-rate",
        type=float,
        default=1.0,
        help="Minimum per-variant success rate (default: 1.0).",
    )
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"gate: cannot read report: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print("gate: report is not a JSON object", file=sys.stderr)
        return 2

    violations = evaluate_gate(
        report,
        min_success_rate=args.min_success_rate,
        min_variant_rate=args.min_variant_rate,
    )
    if violations:
        print("gate: FAILED", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print(
        "gate: OK "
        f"(overall={report['summary']['overall_success_rate']:.3f}, "
        f"variants={len(report['summary'].get('variants') or {})})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
