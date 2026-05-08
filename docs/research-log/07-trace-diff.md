# 07 — Trace diff for offline behavioral comparison

## TL;DR

Post-v2 adds `dm-agent-trace diff`, a keyless offline comparator for two JSONL traces. It reports
status changes, step/tool/replan deltas, action-sequence divergence, tool-usage deltas, plan
changes, and final-answer changes without calling a model, executing tools, or requiring the
original workspace.

This turns trace from a single-run audit artifact into an ablation and regression-review artifact:
maintainers can compare a baseline run with an opt-in mechanism run before trusting a benchmark
headline.

## Context

P2-P5 added default-off mechanisms: Reflexion, RAG, critic review, self-consistency, and adaptive
replanning. The project can now produce multiple traces for the same task under different
configurations, but the previous trace tooling only supported:

- `view`: summarize one run.
- `replay`: dry replay or explicit tool replay for one run.

That left a gap for local research work. If a RAG-enabled run succeeds where the baseline fails, the
first question should not be "what is the score?" It should be "what behavior changed?"

## What Changed

- `dm_agent/tracing/cli.py`
  - Adds `dm-agent-trace diff BASE CANDIDATE`.
  - Adds a pure function `diff_events(base_events, candidate_events)`.
  - Keeps `view` and `replay` output unchanged.
- `dm_agent/tracing/__init__.py`
  - Exports `diff_events` and `summarize_events` for programmatic analysis.
- `tests/test_tracing.py`
  - Covers a deterministic two-trace comparison using a fake client.

## Diff Schema

The JSON output is intentionally compact and stable:

| Field | Meaning |
| --- | --- |
| `status_changed` | Whether final run status changed |
| `task_changed` | Whether the traces describe different task text |
| `final_answer_changed` | Whether the final answer text changed |
| `plan_changed` | Whether initial planner action sequence changed |
| `metrics.*.delta` | Candidate minus base for steps, tool calls, replans, and duration |
| `action_sequence.common_prefix` | Number of identical leading actions |
| `action_sequence.changes` | Per-step action divergence, including missing trailing steps |
| `tool_usage.delta` | Per-tool call-count deltas |

The command is deliberately non-destructive. It never replays tool calls, even for safe tools.

## Example

```bash
dm-agent-trace diff traces/baseline.jsonl traces/rag-enabled.jsonl
dm-agent-trace diff traces/baseline.jsonl traces/rag-enabled.jsonl --json
```

## Keyless Checks

```bash
python -m pytest tests/test_tracing.py
python -m ruff check dm_agent/tracing/cli.py tests/test_tracing.py
```

## Open Questions / Next Bets

- Extend `dm-agent-trace analyze` into directory-level aggregate reports for benchmark traces.
- Add a verification-gap detector: did the run finish without `run_tests`, `run_linter`, or
  `run_python`? Initial per-trace support landed in entry 08.
- Compare trace diffs across repeated benchmark samples and summarize common divergence points.
- Add benchmark report links to trace diffs when both baseline and candidate traces are available.
