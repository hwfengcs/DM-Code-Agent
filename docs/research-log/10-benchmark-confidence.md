# 10 — Benchmark confidence intervals for repeated samples

## TL;DR

Coding and maintenance benchmark summaries now include Wilson 95% confidence intervals for strict
pass rate, hidden-test pass rate, and agent completion rate. Markdown reports display the strict
pass interval next to the point estimate.

This is a reporting change only. It does not increase default repeat counts, run models, or change
scoring.

## Context

The benchmark runner already supports `--repeat`, but reports previously exposed only point
estimates. That is risky for small suites: a 3/4 result and a 30/40 result both display as 75%, but
they should not be read with the same confidence.

The goal is to make local ablation reports harder to over-interpret while keeping them simple and
deterministic.

## What Changed

- `summarize_benchmark_results` now emits:
  - `overall_pass_rate_ci_95`
  - `overall_hidden_test_pass_rate_ci_95`
  - `overall_agent_completion_rate_ci_95`
  - per-variant `pass_rate_ci_95`
  - per-variant `hidden_test_pass_rate_ci_95`
  - per-variant `agent_completion_rate_ci_95`
- Markdown reports label the strict pass column as `Strict pass (95% CI)`.
- Tests verify that the interval brackets the observed rate and remains available in Markdown.

## Why Wilson

Wilson intervals behave better than the normal approximation on small samples and near 0% / 100%.
That matters for local agent suites where a smoke run may only include a few tasks or repeats.

The interval is still binomial and does not solve all benchmark problems:

- tasks are not independent in the same way coin flips are;
- repeated agent runs may share prompts, tools, and model behavior;
- intervals do not replace hidden tests, changed-file constraints, or trace review.

They are a compact warning label, not a statistical proof.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/runner.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/runner.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add variance and confidence summaries to `dm-agent-economics` when comparing multiple reports.
- Add per-task repeat distributions, not only aggregate intervals.
- Add manifest hashes so confidence intervals can be tied to an exact task suite revision.
