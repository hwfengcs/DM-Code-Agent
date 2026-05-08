# 08 — Trace analyzer for failure attribution and verification gaps

## TL;DR

`dm-agent-trace analyze` adds a keyless, read-only review layer on top of one JSONL trace. It
attributes the first observed failure stage, separates recovered failures from final failures,
checks whether a successful run finished without local verification, and emits an advisory trace
health grade.

The analyzer does not replay tools, execute commands, call a model, or change agent behavior. It is
designed as a triage aid for benchmarks and local regression review.

## Context

Entry 07 made two traces comparable. The next missing piece was single-run failure attribution.
Human reviewers often need to answer:

- Did the run fail because the model emitted invalid JSON, picked the wrong tool, hit a tool error,
  failed tests, got rejected by the critic, or simply ran out of steps?
- Did replanning happen after the first failure?
- Did the run claim success without executing any local verification tool?

Those questions can be answered from existing trace events without touching the workspace.

## What Changed

- `dm_agent/tracing/cli.py`
  - Adds `dm-agent-trace analyze TRACE`.
  - Adds `analyze_events(events)` for programmatic use.
- `dm_agent/tracing/__init__.py`
  - Exports `analyze_events`.
- `tests/test_tracing.py`
  - Covers verification-gap detection for a direct finish.
  - Covers parse-error recovery with a replan and pre-finish verification.

## Rule Set

The analyzer scans events in trace order:

| Signal | Stage |
| --- | --- |
| `parse_error` event | `parse` |
| `llm_error` event | `llm` |
| failed `critic_review` | `critic` |
| failed `tool_call` for `run_tests` / `run_linter`, or pytest/assertion output | `verification` |
| unknown-tool text | `tool_selection` |
| malformed argument text | `tool_arguments` |
| tool exception text | `tool_execution` |
| `max_steps_exceeded` with no earlier failure | `max_steps` |

The output distinguishes:

- `primary_failure_stage`: first observed failure, even if later recovered.
- `final_failure_stage`: the stage that still blocks the run, or `none` for recovered/successful
  runs.
- `verification.gap`: successful finish without `run_tests`, `run_linter`, or `run_python` before
  finish.
- `trace_health`: a small `good` / `warning` / `risky` grade with issue labels.

## Why Advisory

Trace analysis is intentionally conservative. Some tasks can be validly completed without tests;
some `run_python` calls are exploratory rather than real verification; some tool observations may
contain provider- or platform-specific wording. Therefore the analyzer is a review signal, not a
scoring gate.

Future benchmark plumbing can include analyzer fields in reports, but strict pass/fail should still
come from hidden tests and changed-file constraints.

## Keyless Checks

```bash
python -m pytest tests/test_tracing.py
python -m ruff check dm_agent/tracing/cli.py dm_agent/tracing/__init__.py tests/test_tracing.py
python -m black --check dm_agent/tracing/cli.py dm_agent/tracing/__init__.py tests/test_tracing.py
```

## Open Questions / Next Bets

- Add trace completeness checks to benchmark JSON reports when `--trace-dir` is used.
- Detect repeated failure loops across adjacent tool calls and replans.
- Track verification strength separately from the binary gap flag.
- Build aggregate analyzer summaries over a directory of traces.
