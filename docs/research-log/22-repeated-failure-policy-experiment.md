# 22 - Repeated-failure policy experiment

## TL;DR

Adaptive replanning has a new default-off experiment:
`--enable-repeated-failure-policy-experiment`. When enabled, a repeated action/error signature can
select `break_repeated_failure_loop` instead of reusing the ordinary failure strategy.

This is not a benchmark score claim. It is a deterministic policy hook with keyless tests.

## Context

Entry 12 added repeated-failure signals but deliberately kept them metadata-only. That was the
right default: repeated failures are suspicious, but some tasks can legitimately retry the same
tool after changing context.

The next useful step is an opt-in experiment that makes the signal policy-bearing without changing
normal agent behavior.

## What Changed

- `AdaptiveReplanPolicy.decide(...)`
  - accepts `repeated_failure` and `use_repeated_failure_escape`.
  - returns `break_repeated_failure_loop` only when both are true.
- `ReactAgent`
  - adds `enable_repeated_failure_policy_experiment=False`.
  - records `repeated_failure_policy_experiment_enabled`.
  - records `repeated_failure_policy_applied_count`.
- Benchmark plumbing
  - exposes `--enable-repeated-failure-policy-experiment`.
  - requires `--enable-adaptive-replanning`.
  - carries the flag in generic and SWE-bench Lite configs without running live evaluations.

## Why It Is Default-Safe

The default is unchanged:

- adaptive replanning remains off unless explicitly enabled;
- the repeated-failure experiment remains off even when adaptive replanning is enabled;
- existing repeated-failure metadata is still recorded;
- no model calls, Docker runs, or SWE-bench runs are introduced by tests.

## Keyless Checks

```bash
python -m pytest tests/test_planner_agent.py tests/test_coding_benchmarks.py
python -m ruff check dm_agent/core/agent.py dm_agent/core/planner.py dm_agent/benchmarks tests
python -m black --check dm_agent/core/agent.py dm_agent/core/planner.py dm_agent/benchmarks tests
```

## Open Questions / Next Bets

- Add an offline ablation harness that compares trace metadata for default adaptive replanning vs
  the loop-breaking policy.
- Surface repeated-failure policy metadata in benchmark Markdown reports.
- Track non-consecutive repeated failures within a run.
