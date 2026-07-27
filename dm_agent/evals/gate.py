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
import sys
from pathlib import Path
from typing import Any


def evaluate_gate(
    report: dict[str, Any],
    *,
    min_success_rate: float,
    min_variant_rate: float,
) -> list[str]:
    """Return a list of human-readable violations (empty when the gate passes)."""
    violations: list[str] = []
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return ["report has no summary object"]

    overall = summary.get("overall_success_rate")
    if not isinstance(overall, (int, float)):
        violations.append("summary.overall_success_rate is missing")
    elif overall < min_success_rate:
        violations.append(
            f"overall_success_rate {overall:.3f} is below the required {min_success_rate:.3f}"
        )

    variants = summary.get("variants") or {}
    for name, data in sorted(variants.items()):
        rate = data.get("success_rate")
        if not isinstance(rate, (int, float)) or rate < min_variant_rate:
            violations.append(
                f"variant '{name}' success_rate "
                f"{rate if isinstance(rate, (int, float)) else 'missing'} "
                f"is below the required {min_variant_rate:.3f}"
            )

    if violations:
        for result in report.get("results", []):
            if isinstance(result, dict) and not result.get("success"):
                violations.append(
                    f"failed: {result.get('variant', '?')}/{result.get('task_id', '?')}: "
                    f"{result.get('failure_reason', '')}"
                )
    return violations


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
    except (OSError, json.JSONDecodeError) as exc:
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
