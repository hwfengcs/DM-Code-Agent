# Trace And Replay

DM-Code-Agent writes JSONL sessions so an agent run can be inspected after it finishes. The
format is append-only, which means partial sessions still survive if a run fails midway.

Every entry carries an `id` (`<run-id-prefix>-<seq>`) and a `parent_id` pointing at the previous
entry, so a session is a navigable tree rather than a flat log. That is what makes
`--resume-at` and `dm-agent-trace fork` possible. See
[`docs/research-log/29-session-tree.md`](research-log/29-session-tree.md) for the design record.

```json
{"id": "a1b2c3d4-0007", "parent_id": "a1b2c3d4-0006", "timestamp": "...",
 "run_id": "a1b2c3d4...", "event": "tool_call", "payload": {"...": "..."}}
```

Sessions written before schema `2.0` have no `id`/`parent_id`. They are still readable: the
loader synthesizes `legacy-0000`, `legacy-0001`, … on read, so `view`, `analyze`, `analyze-dir`,
`replay`, `diff`, and `fork` all keep working on old files unchanged.

## Two Fidelity Tiers, One Format

| | `--trace path.jsonl` | `--checkpoint path.jsonl` |
| --- | --- | --- |
| Purpose | shareable audit view | local resumable session |
| Model responses | `content_chars` + `content_sha256` only (full text needs `--trace-llm-io`) | full text |
| Redaction | yes | `checkpoint` entries are not redacted (redaction rewrites `$HOME` to `~`, which would corrupt resumed context) |
| Tooling | `view` / `analyze` / `replay` / `diff` / `fork` | same, plus `--resume` |

When both flags are supplied, session events fan out to two independent writers. The writers
do not copy one serialized payload: the shareable trace applies its redaction policy while the
local checkpoint keeps complete `message` content. Each writer has its own entry-id sequence, so
`compaction.first_kept_entry_id` is translated to the id that exists in that particular file.
Checkpoint state is written only to the local file. Full LLM request/response capture remains
opt-in via `--trace-llm-io`; a checkpoint file having complete messages does not enable it.

Supplying only `--checkpoint sessions/run.jsonl` still creates a complete session log. It contains
the ordinary `run_start`, `message`, `step`, and `compaction` entries as well as the resumable
`checkpoint` entries, so `dm-agent-trace view` reports the run's steps instead of an empty session.

Pointing both flags at the same file is rejected: the redacted, shareable tier would silently
gain the full conversation.

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

Analyze one trace for failure stage, recovery, and verification gaps:

```bash
dm-agent-trace analyze traces/retry-fix.jsonl
dm-agent-trace analyze traces/retry-fix.jsonl --json
dm-agent-trace analyze-dir bench_reports/traces
dm-agent-trace analyze-dir bench_reports/traces --markdown bench_reports/trace-analysis.md
```

Trace analysis is advisory and read-only. It reports the primary failure stage, final failure
stage, whether a replan happened after the first failure, whether the run finished without a local
verification action, and a small trace-health grade. `analyze-dir` aggregates those signals across
trace directories.

Compare two traces without replaying tools:

```bash
dm-agent-trace diff traces/baseline.jsonl traces/critic-enabled.jsonl
dm-agent-trace diff traces/baseline.jsonl traces/critic-enabled.jsonl --json
```

Trace diff reports status changes, step/tool/replan deltas, action-sequence divergence, tool-usage
deltas, plan changes, and final-answer changes. It is a pure JSONL analysis pass: it does not call a
model, execute tools, or require the original workspace.

Dry replay:

```bash
dm-agent-trace replay traces/retry-fix.jsonl
```

Dry replay does not call a model and does not execute tools. It verifies that the recorded
timeline can be read and replayed as an audit artifact.

## Fork A Session

`fork` branches a new session file from any entry of an existing one:

```bash
dm-agent-trace fork sessions/run.jsonl --at a1b2c3d4-0042
dm-agent-trace fork sessions/run.jsonl --at a1b2c3d4-0042 --output sessions/branch.jsonl
```

Entries `[0..--at]` are copied verbatim (so the original ids survive) and one `fork` entry is
appended, recording the source file and the fork point. That entry's `parent_id` points back at
the fork point, which is what links the two JSONL files into a tree. `--at` accepts an exact id
or a unique prefix; an existing output file is never overwritten.

Whether the branch can actually keep running depends on there being a `checkpoint` entry at or
before the fork point. If there is, `fork` prints the ready-to-paste command:

```bash
dm-agent --resume sessions/branch.jsonl
```

If there is not (for example a plain `--trace` file, or a pre-2.0 trace), `fork` says so
explicitly instead of failing later.

## Resume From A Session Entry

```bash
# append-only session: every step's snapshot is kept
dm-agent "Fix retry.py" --checkpoint sessions/run.jsonl
dm-agent --resume sessions/run.jsonl                      # last checkpoint entry
dm-agent --resume sessions/run.jsonl --resume-at a1b2c3d4-0031   # or an earlier one

# single-file JSON snapshot: unchanged behaviour
dm-agent "Fix retry.py" --checkpoint sessions/run.json
dm-agent --resume sessions/run.json
```

`--resume` sniffs the file: a file that parses as one JSON object is the legacy snapshot, anything
else is read as a session log. `--resume-at` only applies to session logs and resolves to that
entry *or the closest `checkpoint` entry before it*.

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
- `message`: one message appended to the conversation history, with `role` and `kind`
  (`task` / `model_response` / `tool_result` / `observation` / `completion` / `replan_note` /
  `carried` / `resumed`). `assistant` content is reduced to `content_chars` + `content_sha256`
  unless `--trace-llm-io` is set.
- `compaction`: context was folded for one request. Records `first_kept_entry_id`,
  `folded_entry_ids`, the `<agent_memory>` `summary`, and the token estimate before/after.
  **The folded `message` entries are never removed** — folding only affects the message list sent
  to the model for that one request.
- `checkpoint`: resumable run state appended to a `--checkpoint *.jsonl` session.
- `fork`: this file was branched from another session (`source`, `forked_from_entry_id`).
- `skills`: activated skill names.
- `plan`: initial planner steps.
- `plan_error`: planning failure.
- `llm_call`: message count, roles, temperature, prompt chars, estimated prompt tokens, and response chars.
- `parse_error`: invalid model response information.
- `tool_call`: action, action input, observation, and failure flag.
- `observation_truncated`: a tool observation exceeded the cap; original/kept chars and line count.
- `context_budget`: the estimated-token budget forced an early compression
  (`phase=forced_compress`) or the compressed view is still over budget
  (`phase=post_compress_still_over`).
- `edit_guard`: an `edit_file` call was blocked (`reason=never_read` or `stale_read`) until the
  target range is re-read.
- `memory_invalidation`: memory hygiene superseded failure memories after a later success
  (only with `--enable-memory-hygiene`).
- `file_backup`: the original file was copied to the per-run backup directory before a
  write-class tool ran.
- `checkpoint_saved`: run state was snapshotted to the `--checkpoint` file after a step.
- `run_resumed`: a run continued from a `--resume` checkpoint (records the resume step).
- `circuit_breaker`: a repeatedly failing tool was disabled (`phase=opened`) or a call to it
  was intercepted during cooldown (`phase=blocked`); only with `--enable-circuit-breaker`.
- `step`: ReAct step with thought, action, input, and observation.
- `replan`: regenerated plan after a failure.
- `run_end`: final answer, status, duration, and agent metadata.
- `run_error`: unhandled runtime error.

## Trace Analysis

`dm-agent-trace analyze` converts one trace into a small review checklist:

- `primary_failure_stage`: first observed failure source such as `parse`, `tool_execution`,
  `verification`, `critic`, or `max_steps`.
- `final_failure_stage`: the stage that still blocked the run, or `none` if the run recovered.
- `recovery`: failure count, first failure step, replan count, and whether a replan occurred after
  the first failure.
- `verification`: `run_tests`, `run_linter`, and `run_python` actions before finish, plus a
  `gap` flag for successful runs that finished without local verification.
- `trace_health`: a compact `good` / `warning` / `risky` grade with issue labels.

`dm-agent-trace analyze-dir` applies the same analyzer to every matching trace in a directory and
summarizes health grades, verification gaps, and failure-stage counts. It accepts `--pattern` for
non-default file names, `--json` for machine-readable output, and `--markdown PATH` for a shareable
summary that omits raw prompts, observations, tool outputs, and final answers.

## Trace Diff

`dm-agent-trace diff` is intended for regression review and benchmark ablations. A maintainer can
compare a baseline run against an opt-in mechanism run and inspect whether the new run changed the
plan shape, skipped or added tools, reduced replans, or changed the final answer before looking at
the full JSONL.

Example JSON fields:

- `metrics.step_count.delta`
- `metrics.tool_call_count.delta`
- `action_sequence.common_prefix`
- `action_sequence.changes`
- `tool_usage.delta`
- `plan_changed`
- `final_answer_changed`

## Non-Destructive Compaction

Context compaction never deletes history. It appends one `compaction` entry describing the fold,
and the message list for that request is assembled by *skipping* the folded range. Because the
originals stay in the log, the same session can be replayed both ways:

```python
from dm_agent.tracing import load_session_entries, rebuild_context

entries = load_session_entries("sessions/run.jsonl")
sent = rebuild_context(entries, apply_compaction=True)    # what the model actually saw
full = rebuild_context(entries, apply_compaction=False)   # as if compaction never happened
```

The difference between the two is exactly what compaction folded away, which is what makes the
`no_compression` ablation attributable rather than just a pair of end-to-end scores.

`rebuild_context` also takes `until_entry_id=` to reconstruct the window as of an earlier entry.

Note that `estimated_tokens_after` can exceed `estimated_tokens_before` when only a message or two
is folded but an `<agent_memory>` block is injected. That was always true; it is now visible in
the log.

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
