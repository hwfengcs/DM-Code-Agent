# 05 — Adaptive replanning and token economics

## TL;DR

P5 adds two default-off pieces:

- `AdaptiveReplanPolicy`: a deterministic error-signal classifier that can steer replanning by
  failure type (`tool_error`, `parse_error`, `test_failure`, `critic_rejected`, `max_steps`).
- `dm_agent.benchmarks.economics`: an offline report generator that reads existing benchmark JSON
  and computes pass rate, estimated tokens, estimated cost, and cost per success.

No live model, Docker verifier, Tier-2 SWE-bench, or new SWE-bench scoring run was executed for this
phase. The P1 Tier-1 baseline remains unchanged.

## Context

The P1 failure-mode analysis showed two practical problems:

1. The agent can spend too many steps repeating the same recovery pattern.
2. Pass rate alone hides the cost shape of a mechanism. A feature that improves one task but doubles
   token use needs to be measured explicitly.

The goal for this phase is therefore not a new leaderboard number. It is a local, reproducible
control surface for recovery behavior and a report format that lets future real runs compare
cost-per-success.

## What Changed

- `dm_agent/core/planner.py`
  - `ReplanSignal`
  - `ReplanDecision`
  - `AdaptiveReplanPolicy`
  - `TaskPlanner.replan(..., error_signal=...)` strategy guidance
- `dm_agent/core/agent.py`
  - `enable_adaptive_replanning=False`
  - `max_replans=-1`
  - `replan_decision` trace events
  - metadata fields: `replan_signals`, `replan_strategy_counts`, `replan_skipped_count`,
    `replan_maxed_count`
- `dm_agent/benchmarks/economics.py`
  - offline JSON report reader
  - Markdown/JSON economics report rendering
  - CLI entry point: `dm-agent-economics`
- Benchmark config
  - `--enable-adaptive-replanning`
  - `--max-replans`
  - `--cost-per-1k-tokens`

All new behavior is opt-in. With the default flags, existing planner/replan behavior stays the same.

## Strategy Map

| Signal | Strategy | Intent |
| --- | --- | --- |
| `tool_error` | `simplify_plan_skip_failed_tool` | Avoid blindly repeating a failing tool call |
| `unknown_tool` | `select_available_tool` | Force the plan back onto the supported tool set |
| `parse_error` | `repair_response_format` | Add a strict JSON-format recovery step |
| `invalid_arguments` | `repair_tool_arguments` | Fix tool input shape before retrying |
| `test_failure` | `inject_test_failure_context` | Put failing test output at the center of the next plan |
| `critic_rejected` | `address_critic_feedback` | Treat critic feedback as a blocker, not a summary |
| `max_steps` | `coarsen_plan_after_budget` | Merge low-value steps and move toward a smaller fix |

## Economics Report

The checked-in smoke report is generated from the existing P1 Tier-1 baseline only:

```bash
python -m dm_agent.benchmarks.economics \
  bench_reports/swebench_lite_baseline.json \
  --label swebench-tier1-baseline \
  --cost-per-1k-tokens 0.00027 \
  --output-json bench_reports/economics.json \
  --output-md bench_reports/economics.md
```

The price value above is a configured example input for local accounting, not a live provider quote.
Because the frozen baseline resolved `0/50`, cost-per-success is intentionally `n/a`.

Raw report: `bench_reports/economics.json`
Markdown report: `bench_reports/economics.md`

## Frozen Real-Eval Items

These remain intentionally undone under the current constraints:

- No Docker / Tier-2 SWE-bench verification.
- No new true SWE-bench run.
- No cross-model SWE-bench run.
- No claim that Reflexion, RAG, Critic, Self-Consistency, or Adaptive Replanning improved the real
  P1 score.

The code path is ready for future runs, but the numbers should only be filled after an allowed live
evaluation.

## Keyless Checks

```bash
python -m pytest tests/test_planner_agent.py tests/test_coding_benchmarks.py
python -m ruff check dm_agent tests
python -m black --check .
```

## Open Questions / Next Bets

- Whether adaptive replanning should become the default after enough deterministic eval evidence.
- Whether the policy should track consecutive repeated tool failures, not just total replans.
- Whether future economics reports should split input/output tokens once provider clients expose
  reliable per-direction accounting.
- Whether cross-model cost comparisons should be separate from SWE-bench until Tier-2 is available.
