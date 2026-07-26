# 26 — Run-level checkpoint/resume and progress-carrying replan

## TL;DR

- **`--checkpoint PATH`**: after every step the agent atomically snapshots
  conversation history, steps, metadata, plan, compressor memory, reflexion
  lessons, and an agent-config fingerprint into one JSON file
  (`RunCheckpoint`, schema v1, `dm_agent/core/checkpoint.py`).
- **`--resume PATH`**: restores that state into a fresh process and continues
  from `step_count + 1`; the task argument may be omitted (taken from the
  checkpoint). Max-steps-exhausted runs also write a terminal snapshot, so
  they can be resumed with a larger `--max-steps`.
- **Progress-carrying replan (default-on fix)**: `TaskPlanner.replan` now
  keeps completed steps (renumbering new ones after them) instead of
  resetting everything to `[todo]`, the agent marks plan progress only when
  the *next pending* step's action matches (no more first-name-match
  ambiguity), and the non-adaptive replan path gets a cost guard
  (`DEFAULT_REPLAN_BUDGET = 5`; `--max-replans` still overrides).
- **`--reflexion-memory-file PATH`** (opt-in): persists `EpisodicMemory`
  lessons across processes using its existing `to_dict/from_dict`.

## Design decisions

**Snapshot timing: start-of-next-iteration.** The loop body has several
`continue` exits (parse error, unknown tool, critic rejection); snapshotting
at the top of iteration N persists exactly the state after iteration N-1 for
all of them with one call site. A crash mid-step resumes by *repeating* the
interrupted step — safe because the step never wrote its observation into
the persisted history.

**Compressor memory is included.** Without it, a resumed long run loses all
atomic memories and the compression cadence drifts — the "resume behaves
like it was never interrupted" acceptance criterion fails.
`Mem0StyleMemory.to_dict/from_dict` passes item metadata through verbatim,
so hygiene markers (`superseded_at_turn`, entry 24) survive for free — which
is also why the P1 work had to land before this entry.

**The file ledger is deliberately NOT persisted.** After a resume, the
read-before-edit guard starts empty, so the first `edit_file` on any file is
blocked until re-read. That is the correct bias: files may have changed on
disk while the run was stopped.

**Resume refuses config drift silently changing semantics.** The checkpoint
stores model/temperature/guard settings; mismatches print warnings (not
fatal — resuming with a different model is a legitimate recovery move).
Unknown `schema_version` is a hard error.

**Reflexion multi-trial runs are excluded (v1).** Trials wrap `_run_once`
and would need per-trial checkpoint naming plus lesson-state coordination;
`--checkpoint/--resume` with `--enable-reflexion` is rejected at validation.
Benchmark/SWE-bench keep their existing instance-level resume — a run-level
checkpoint inside a benchmark would double-layer recovery for no measurement
benefit.

**Replan budget default = 5.** Before this entry, with planning on and
adaptive replanning off (the default configuration!), every failing
observation triggered a full planner LLM call with no ceiling — a genuine
token-blowup path. Five replans covers every legitimate recovery seen in the
deterministic evals and traces; `--max-replans` overrides it, and exhaustion
is audited via the existing `replan_decision` trace event
(`strategy=replan_budget_exhausted`). Progress-carrying itself ships without
a flag: it only fixes bookkeeping (completed work displayed as `[todo]`,
first-match marking on duplicate actions) — the old behavior has no
defensible semantics to preserve.

## Measurement

Keyless: `tests/test_checkpoint.py` (roundtrip + schema guard, max-steps
snapshot, resume-and-finish with counters preserved and no tool re-runs,
compressor memory roundtrip, reflexion+resume rejection),
`tests/test_planner_agent.py` (progress-carrying replan, default budget with
trace assertion; existing replan tests updated in the same commit),
`tests/test_reflexion.py` (memory-file roundtrip).

## Open questions / next bets

1. Checkpoint files contain conversation history — same privacy posture as
   `--trace-llm-io`, documented in tracing.md's privacy section.
2. Reflexion-trial checkpointing (per-trial files) if long reflexion runs
   become common.
3. A `dm-agent-trace` subcommand to render a checkpoint's plan/step state
   would make manual inspection nicer.
