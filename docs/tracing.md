# Trace And Replay

DM-Code-Agent writes JSONL traces so an agent run can be inspected after it finishes. The
trace format is append-only, which means partial traces still survive if a run fails midway.

## Enable Trace

```bash
dm-agent "Fix retry.py and run tests" --trace traces/retry-fix.jsonl
```

For a human-readable summary, write a Markdown report next to the machine-readable trace:

```bash
dm-agent "Fix retry.py and run tests" \
  --trace traces/retry-fix.jsonl \
  --report reports/retry-fix.md
```

The report includes runtime metadata, step summaries, the final answer, and git workspace
status before/after the run.

View the trace:

```bash
dm-agent-trace view traces/retry-fix.jsonl
dm-agent-trace view traces/retry-fix.jsonl --json
```

Dry replay:

```bash
dm-agent-trace replay traces/retry-fix.jsonl
```

Dry replay does not call a model and does not execute tools. It verifies that the recorded
timeline can be read and replayed as an audit artifact.

## Tool Replay

Tool replay is explicit because it can read files, modify files, or run commands:

```bash
dm-agent-trace replay traces/retry-fix.jsonl --execute-tools --workspace .
```

Execution tools are blocked unless you explicitly allow them:

```bash
dm-agent-trace replay traces/retry-fix.jsonl \
  --execute-tools \
  --allow-shell \
  --workspace /path/to/sandbox
```

Tool replay compares the new observation with the recorded observation and reports mismatches.

## Events

The current schema records these event types:

- `runtime`: CLI/provider/runtime metadata.
- `run_start`: task, working directory, platform, safe metadata, and tool list.
- `skills`: activated skill names.
- `plan`: initial planner steps.
- `plan_error`: planning failure.
- `llm_call`: message count, roles, temperature, prompt chars, and response chars.
- `parse_error`: invalid model response information.
- `tool_call`: action, action input, observation, and failure flag.
- `step`: ReAct step with thought, action, input, and observation.
- `replan`: regenerated plan after a failure.
- `run_end`: final answer, status, duration, and agent metadata.
- `run_error`: unhandled runtime error.

## Privacy Boundary

Default traces avoid complete model input/output. They still may include file paths, tool
arguments, command output, and observations. The writer redacts common environment secret
values and home-directory prefixes, but traces should still be treated as development
artifacts.

Use full LLM I/O only for private debugging:

```bash
dm-agent "Explain this module" --trace traces/debug.jsonl --trace-llm-io
```

## Design Notes

- JSONL is used so traces remain useful after interrupted runs.
- Replay starts with dry replay because it is safe and deterministic.
- Tool replay is a separate opt-in mode so dangerous actions are never hidden behind a default.
- The schema is intentionally small enough to inspect manually and evolve over time.
