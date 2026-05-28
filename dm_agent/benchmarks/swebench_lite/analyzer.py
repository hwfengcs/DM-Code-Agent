"""Failure-mode analysis for SWE-bench Lite results.

Given a list of :class:`SWEBenchResult`, the analyzer assigns each failed run
to one :class:`FailureCategory` bucket. The buckets are designed so that the
distribution gives us actionable guidance for the next phases:

- ``patch_not_produced`` and ``parse_error`` are addressed by stricter
  output-format prompting, by Reflexion (P2), and by Adaptive Replanning (P5).
- ``patch_apply_failed`` often means the agent chose stale hunk context or
  edited without re-reading the concrete target file.
- ``hidden_test_fail`` and ``regression`` benefit from Critic + Self-Consistency
  (P4): an independent reviewer can catch behavioural mistakes.
- ``max_steps`` and ``timeout`` are budget signals.

Use :func:`summarize_failure_modes` to aggregate counts and
:func:`render_markdown_failure_modes` to produce a report addendum.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence

from .models import FailureCategory, SWEBenchResult


def categorize_failure(result: SWEBenchResult) -> FailureCategory:
    """Assign a single :class:`FailureCategory` to a failed result.

    Successful results return :attr:`FailureCategory.UNKNOWN`; callers should
    typically gate on ``result.success`` first.
    """
    if result.success:
        return FailureCategory.UNKNOWN

    verification = result.verification
    metadata = result.metadata or {}

    # 1. Did the agent emit a patch at all?
    if not result.prediction or not result.prediction.strip():
        return FailureCategory.PATCH_NOT_PRODUCED
    if verification.error == "empty_prediction":
        return FailureCategory.PATCH_NOT_PRODUCED

    # 2. Did the patch apply?
    if not verification.patch_applied:
        if verification.error == "patch_apply_failed":
            return FailureCategory.PATCH_APPLY_FAILED
        # Fall through: workspace setup or another upstream issue.

    # 3. Agent-side terminal states (signaled by metadata.status / failure_reason).
    status = metadata.get("status")
    if status == "max_steps":
        return FailureCategory.MAX_STEPS
    if status in {"parse_error", "agent_status_parse_error"}:
        return FailureCategory.PARSE_ERROR
    if metadata.get("tool_error_count", 0) and not verification.patch_applied:
        return FailureCategory.TOOL_ERROR

    if result.failure_reason and result.failure_reason.startswith("workspace_setup_failed"):
        return FailureCategory.UNKNOWN
    if result.failure_reason == "no_patch_produced":
        return FailureCategory.PATCH_NOT_PRODUCED

    # 4. Patch applied but tests did not satisfy the SWE-bench contract.
    if verification.patch_applied:
        if verification.pass_to_pass_pass < verification.pass_to_pass_total:
            return FailureCategory.REGRESSION
        if verification.fail_to_pass_pass < verification.fail_to_pass_total:
            return FailureCategory.HIDDEN_TEST_FAIL

    # 5. Timeouts surface in the verifier's error string when pytest hits them.
    if verification.error and "TIMEOUT" in (verification.stderr_tail or "").upper():
        return FailureCategory.TIMEOUT

    return FailureCategory.UNKNOWN


def summarize_failure_modes(results: Iterable[SWEBenchResult]) -> Dict[str, Any]:
    """Return counts and rates for each :class:`FailureCategory`.

    The ``per_category`` map preserves :class:`FailureCategory` declaration
    order so the report sorts deterministically.
    """
    results = list(results)
    failures = [r for r in results if not r.success]
    counts: Counter[FailureCategory] = Counter(categorize_failure(r) for r in failures)

    per_category: List[Dict[str, Any]] = []
    for category in FailureCategory:
        count = counts.get(category, 0)
        per_category.append(
            {
                "category": category.value,
                "count": count,
                "rate_of_failures": (count / len(failures)) if failures else 0.0,
                "rate_of_total": (count / len(results)) if results else 0.0,
            }
        )

    return {
        "total": len(results),
        "successes": len(results) - len(failures),
        "failures": len(failures),
        "per_category": per_category,
    }


def render_markdown_failure_modes(summary: Dict[str, Any]) -> str:
    """Render :func:`summarize_failure_modes` output as a Markdown table."""
    total = summary.get("total", 0)
    failures = summary.get("failures", 0)

    lines: List[str] = [
        "## Failure modes",
        "",
        f"- Total runs: `{total}`",
        f"- Successes: `{summary.get('successes', 0)}`",
        f"- Failures: `{failures}`",
        "",
        "| Category | Count | % of failures | % of total |",
        "| --- | ---: | ---: | ---: |",
    ]
    for entry in summary.get("per_category", []):
        if entry["count"] == 0:
            continue
        lines.append(
            f"| `{entry['category']}` | {entry['count']} | "
            f"{entry['rate_of_failures'] * 100:.1f}% | {entry['rate_of_total'] * 100:.1f}% |"
        )
    if total and not failures:
        lines.append("| — | 0 | — | — |")
    return "\n".join(lines) + "\n"


def render_full_analysis(results: Sequence[SWEBenchResult]) -> str:
    """Convenience: build a full failure-mode addendum from raw results."""
    summary = summarize_failure_modes(results)
    return render_markdown_failure_modes(summary)
