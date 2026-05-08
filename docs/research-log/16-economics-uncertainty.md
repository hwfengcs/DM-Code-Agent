# 16 — Confidence-aware token economics reports

## TL;DR

`dm-agent-economics` now carries pass-rate 95% confidence intervals from benchmark reports into the
offline economics table. If an older report lacks the interval, the economics helper computes a
Wilson interval from successes and total runs.

No prices are fetched, no models are run, and no benchmark is re-executed.

## Context

Entry 10 added confidence intervals to benchmark summaries. The economics report compares pass rate,
tokens, cost, and cost per success across existing JSON files. Without intervals, it could still
make a tiny sample look as decisive as a larger run.

The fix is to preserve uncertainty all the way into the cost table.

## What Changed

- `EconomicsEntry` includes `pass_rate_ci_95`.
- `summarize_report(...)` uses `summary.overall_pass_rate_ci_95` when available.
- Older reports get a Wilson fallback interval.
- Markdown renders pass rate as `point [low-high]`.

## Interpretation

The interval is not a leaderboard claim. It is a local accounting aid:

- pass-rate uncertainty and cost-per-success should be read together;
- a cheap run with a wide interval may not be better than a more expensive stable run;
- reports remain only as trustworthy as their manifest, hidden tests, and trace review.

## Keyless Checks

```bash
python -m pytest tests/test_coding_benchmarks.py
python -m ruff check dm_agent/benchmarks/economics.py tests/test_coding_benchmarks.py
python -m black --check dm_agent/benchmarks/economics.py tests/test_coding_benchmarks.py
```

## Open Questions / Next Bets

- Add uncertainty-aware cost-per-success intervals when repeated report samples exist.
- Add a report-comparison CLI that refuses to rank reports with different suite signatures unless
  explicitly allowed.
