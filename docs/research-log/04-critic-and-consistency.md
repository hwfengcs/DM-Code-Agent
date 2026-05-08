# 04 — Critic and self-consistency

## TL;DR

P4 lands two pieces of selection logic that sit on top of the ReAct loop:

- `CriticAgent`: a peer-review gate that inspects a candidate completion before the agent accepts
  it as finished.
- `SelfConsistencyRunner`: a wrapper that runs the same task multiple times and selects the best
  candidate with majority vote, critic score, or visible-test pass.

Both are default-off. Normal `ReactAgent` behavior stays unchanged unless a critic instance is
passed in. The new logic is covered by keyless tests and trace events, but the benchmark-level
ablation table is still pending a dedicated runner pass.

## Context

Reflexion helps when one run fails and can learn from the failure. Critic and self-consistency are
different: they change how we *accept* a candidate and how we pick between several independent
candidates. The motivation is simple: some completions look plausible but are still wrong, and some
tasks benefit from multiple noisy attempts rather than a single deterministic path.

## What Changed

- `dm_agent/core/critic.py`
  - `CriticAgent`
  - `CriticReview`
  - JSON-first review parsing with heuristic fallback
- `dm_agent/core/self_consistency.py`
  - `SelfConsistencyRunner`
  - `SelfConsistencyCandidate`
  - `SelfConsistencyResult`
- `dm_agent/core/agent.py`
  - Optional `critic` parameter
  - Completion gate before accepting `finish` / `task_complete`
  - `critic_review` trace events
  - metadata counters for review passes and failures
- `dm_agent/tracing/writer.py`
  - `record_critic_review`

## Design Notes

The critic is intentionally a gate, not a refiner. It returns a structured pass/fail verdict and a
few concrete reasons. If it rejects a completion, the agent gets an explicit failure observation and
can continue or replan.

Self-consistency is kept generic: it operates on a callable that runs one candidate and returns a
dict-shaped result. That keeps it usable for local agent runs, benchmark wrappers, or future tool
pipelines without hard-wiring it to one particular workspace manager.

## Keyless Checks

```bash
python -m pytest tests/test_critic.py tests/test_self_consistency.py
python -m pytest tests/test_planner_agent.py
```

## Open Questions / Next Bets

- Whether benchmark-level selection should live in the benchmark runner or stay as a separate
  wrapper.
- Whether the critic should see raw patches or only the agent's final answer.
- Whether majority vote should compare final answers, patch fingerprints, or hidden-test outcomes.
- Whether the critic should become a reusable scoring API for future P4/P5 experiments.
