"""SWE-bench Lite benchmark suite for DM-Code-Agent.

Adapts the public SWE-bench Lite dataset (princeton-nlp/SWE-bench_Lite, 300 GitHub
issues sampled from real Python repositories) to DM-Code-Agent's benchmark
runner. Each task instance gives the agent the natural-language `problem_statement`
plus the repository at `base_commit`. The agent must produce a patch; the
verifier scores the patch by running the instance's hidden `FAIL_TO_PASS` and
`PASS_TO_PASS` tests.

Public API:
    SWEBenchInstance        Single task description.
    SWEBenchResult          Single benchmark result.
    SWEBenchVerification    Hidden-test verification outcome.
    load_instances          Load a (subset of) SWE-bench Lite instances.
    fixed_subset_50         Deterministic 50-instance subset for v2 baselines.
    run_swebench_lite       End-to-end runner: agent + workspace + verifier.
    categorize_failure      Classify a failed result into a recovery-relevant bucket.
    summarize_failure_modes Aggregate failure-mode statistics across results.

The submodule never imports `datasets` at module load time. Loading the
dataset requires the optional `[swebench]` extra (`pip install
"dm-code-agent[swebench]"`) so that the default install stays small.
"""

from __future__ import annotations

from .models import (
    SWEBenchInstance,
    SWEBenchResult,
    SWEBenchVerification,
    SWEBenchRunConfig,
    FailureCategory,
)

__all__ = [
    "SWEBenchInstance",
    "SWEBenchResult",
    "SWEBenchVerification",
    "SWEBenchRunConfig",
    "FailureCategory",
    "load_instances",
    "fixed_subset_50",
    "run_swebench_lite",
    "categorize_failure",
    "summarize_failure_modes",
]


def __getattr__(name: str):
    """Lazy import to keep optional `datasets` dependency truly optional."""
    if name in {"load_instances", "fixed_subset_50"}:
        from .loader import load_instances, fixed_subset_50

        return {"load_instances": load_instances, "fixed_subset_50": fixed_subset_50}[name]
    if name == "run_swebench_lite":
        from .runner import run_swebench_lite

        return run_swebench_lite
    if name in {"categorize_failure", "summarize_failure_modes"}:
        from .analyzer import categorize_failure, summarize_failure_modes

        return {
            "categorize_failure": categorize_failure,
            "summarize_failure_modes": summarize_failure_modes,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
