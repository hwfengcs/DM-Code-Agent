# 12 — Adaptive replanning repeated-failure signals

## TL;DR

Adaptive replanning now records consecutive repeated failures with the same
`action + error kind + observation` signature. The signal is stored in run metadata and
`replan_decision` trace events.

This is intentionally metadata-only. It does not change whether replanning happens, which strategy
is selected, or any default-off behavior.

## Context

P5 classified individual failures into strategies such as `tool_error`, `parse_error`, and
`critic_rejected`. That helped explain one failure at a time, but it did not identify loops where
the agent replans and then returns to the same failing action.

Repeated failures are a useful recovery signal:

- they expose tool loops;
- they can explain token waste;
- they provide a future hook for escalation policies;
- they are fully deterministic from existing observations.

## What Changed

- `ReactAgent` metadata now includes:
  - `last_failure_signature`
  - `repeated_failure_count`
  - `repeated_failures`
- `replan_decision` trace events now include:
  - `repeated_failure`
  - `repeated_failure_details` when a repeat is detected
- Tests cover two consecutive failing tool calls followed by successful recovery.

## Signature

The signature is:

```text
action | error_kind | compact_observation
```

The observation is whitespace-normalized and truncated, so the metadata stays compact while still
being specific enough to identify repeated behavior.

## Why No Decision Change Yet

It would be tempting to immediately route repeated failures to a new strategy such as
`avoid_repeated_failed_action`. That is risky without ablation data: some tools fail once because
the input was wrong, and a second attempt with a slightly different context may be valid.

For now, the signal is observable. Future work can make it policy-bearing after deterministic
benchmarks show whether escalation helps.

## Keyless Checks

```bash
python -m pytest tests/test_planner_agent.py
python -m ruff check dm_agent/core/agent.py tests/test_planner_agent.py
python -m black --check dm_agent/core/agent.py tests/test_planner_agent.py
```

## Open Questions / Next Bets

- Build an ablation harness around the default-off loop-breaking experiment.
- Track non-consecutive repeated failures within a run.
- Aggregate repeated-failure counts in benchmark reports.
