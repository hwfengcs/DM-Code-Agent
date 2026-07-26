# 23 — Observation truncation, token budget, and the read-before-edit guard

## TL;DR

Long-context hallucination in this agent had a concrete mechanical cause: tool
outputs entered the conversation verbatim with no cap (`read_file` returned
whole files; `run_tests` returned full stdout+stderr), compression fired on
message count only, and `edit_file` operated on raw line numbers with no
requirement that the file was ever read. This entry lands three default-on
infrastructure guards:

1. **Bounded observations** — every tool observation is capped
   (`--max-observation-chars`, default 8000) with an explicit
   `[truncated: ...]` marker and concrete paging guidance.
2. **Token-budget compression trigger** — the compressor now also fires when
   the estimated history size exceeds `--context-token-budget` (default
   24000 tokens, chars/4 heuristic), not only every N turns.
3. **Read-before-edit guard** — `edit_file` is intercepted unless the target
   file was read this run and re-read after any write
   (`--disable-edit-guard` to opt out).

All three are auditable: new trace events `observation_truncated`,
`context_budget`, and `edit_guard` (trace schema 1.0 → 1.1, additive).

## Context

The v2 review of long-context behavior found:

- `file_tools.read_file` returned entire files and `execution_tools.run_*`
  returned full command output; a single verbose traceback or large file
  persisted verbatim for at least `keep_recent*2 = 16` messages.
- `ContextCompressor.should_compress` triggered purely on turn cadence
  (`compress_every=20`), so twenty turns of large observations could overflow
  the window before compression ever fired. Between compressions the full
  history was sent as-is.
- Nothing enforced the prompt rule "understand before modifying":
  `edit_file` happily replaced line ranges in files the model had never read
  in this run, which is exactly the hallucinated-edit failure mode.

## Design decisions

**Truncation lives in the agent, not the tools.** The two `tool.execute`
call sites in `ReactAgent._run_once` are the single choke point through which
built-in, skill, and MCP tools all flow. Bounding there guarantees that
`Step.observation`, `conversation_history`, and the `tool_call` trace event
carry the same text — the trace never shows more (or less) than the model saw.
A `default_tools()` closure would have missed skill and MCP tools.

**Head + tail, with a head floor.** Caps keep
`head = max(min(cap, 500), 60% of cap)` and give the rest to the tail:
file heads carry imports/signatures, tracebacks live at the end. The 500-char
head floor (bounded by the cap itself for small caps) keeps the
repeated-failure signature input — `observation[:160]` in
`_record_failure_signature` — byte-identical for truncated failures, so
devlog 12/22 semantics are unaffected. Tests assert this invariant.

**Marker wording is constrained.** `_is_failure_observation` and the
compressor's `_ERROR_MARKERS` match substrings like `error`, `failed`,
`失败`, `错误`, `不存在`. The truncation marker and guard messages
deliberately avoid all of them ("truncated", "blocked", "changed") so a
healthy-but-bounded observation cannot trigger replan or be memorized as a
failure. A test feeds the marker to `_is_failure_observation` and asserts
`False`.

**Budget is a floor guard, not a hard limit.** When the estimated history
exceeds the budget, compression is forced early (`last_trigger =
"token_budget"`, counted in `budget_compression_count`). If the *compressed*
view is still over budget, we record a `context_budget` event with
`phase="post_compress_still_over"` and do nothing else — with observations
bounded at the source, recent-window bloat is no longer reachable in normal
operation, and silently dropping recent messages would be worse than a large
prompt.

**The edit guard derives state from the action history only.** A
`FileLedger` records the step of the last successful read
(`read_file`/`search_in_file`) and write (`edit_file`/`create_file`) per
normalized path. `edit_file` is blocked when the path was never read
(`never_read`) or written after the last read (`stale_read`). No mtime/hash
checks — the filesystem is never consulted, so behavior is identical on
Windows and in replay. Blocked edits do not execute the tool, do not mark
plan steps completed, and return a synthetic observation telling the model
exactly how to proceed (re-read the target range). `create_file` is exempt
(its semantics are overwrite).

**Why default-on.** Unlike Reflexion/Critic (which change *what the agent
tries*), these guards only bound resource use and intervene when the model is
already on a hallucination path (editing unread files). The keyless
deterministic evals pass unchanged with defaults; none of the 13 tasks uses
`edit_file` without reading. Escape hatches: `--max-observation-chars 0`,
`--context-token-budget 0`, `--disable-edit-guard`.

## Measurement

- Keyless: `tests/test_context_budget.py` (truncation invariants, estimator
  boundaries, ledger), `tests/test_agent_guards.py` (end-to-end scripted runs:
  block → re-read → edit; stale-read; truncation in history + trace), plus
  budget-trigger cases in `tests/test_memory_compressor.py`.
- New metadata counters: `truncation_count`, `truncated_chars_saved`,
  `budget_compression_count`, `edit_guard_block_count` — these feed the
  hallucination-signal aggregation planned for the evals track (entry 28).
- Live ablation (does the guard reduce failed edits / step waste on the
  maintenance suite?) is pending; per the freeze policy this entry claims
  implementation and keyless verification only.

## Open questions / next bets

1. Tail truncation currently cuts mid-line; snapping to line boundaries would
   cost a few chars of budget for cleaner rendering.
2. The budget estimator ignores the system prompt (roughly constant per run).
   If skills inflate it significantly, the estimate should include it.
3. `edit_guard` treats any successful `search_in_file` as a read; a stricter
   variant could require the edited line range to have been displayed.
