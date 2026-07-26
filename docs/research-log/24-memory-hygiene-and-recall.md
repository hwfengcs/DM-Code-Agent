# 24 — Memory hygiene and anchored recall (default-off)

## TL;DR

Two default-off upgrades to the Mem0-style local memory
(`--enable-memory-hygiene`, `--enable-llm-compression`):

1. **Hygiene** — when a later message reports success (`returncode: 0` or a
   success marker) touching the same files, matching "Observed failure"
   memories are *superseded*: importance ×0.3, search score ×0.25, and the
   rendered line gains a "(possibly stale: later success touched these
   files)" suffix. The recall query is also anchored to the original task
   text instead of only the last four messages.
2. **LLM summary compression** — when folding older messages, the compressor
   can additionally ask the (already-plumbed, previously unused) client for a
   ≤500-char summary stored as one semantic memory; any failure silently
   falls back to the pure rule-based path.

Both stay off by default. New metadata: `memory_invalidation_count`,
`llm_summary_count`, `llm_summary_error_count`; new trace event
`memory_invalidation`.

## Context

The rule-based memory had two stale-context hazards observed in code review:

- **Failure memories never expired.** A pytest failure in `retry.py` was
  extracted as a high-importance (0.8) "Observed failure" memory. After the
  fix landed and tests passed, the memory kept its importance and could be
  recalled many turns later — injecting a confidently wrong "this file is
  broken" hint, which is precisely the hallucination shape we want to avoid.
- **Recall was myopic.** The search query was built from the last four
  messages only (`compress` at `context_compressor.py`). Long detours (e.g.,
  exploring an unrelated module) skewed recall away from task-relevant
  memories.

## Design decisions

**Supersede, don't delete.** The memory `id` is a fingerprint of
`(type, text, scope)`; editing text would break deduplication, and deleting
would erase audit history. Superseded items keep their text, drop to 30%
importance, are down-ranked (not excluded) in search, and carry an explicit
staleness annotation when rendered — the model still sees the history but
with calibrated trust. `superseded_at_turn` lives in item metadata, which
round-trips through the (upcoming) checkpoint serialization for free.

**Inert when off.** The score penalty and render suffix key off
`superseded_at_turn`, which is only ever written when hygiene is enabled —
so the default path is behaviorally identical to the legacy pipeline. A
regression test compresses the same history with and without the flag and
asserts identical output for the off case.

**Why default-off (and the promotion bar).** Hygiene rewrites what
`<agent_memory>` injects — the same blast radius as an algorithm module, and
lexical recall quality cannot be fully validated keyless. Promotion to
default requires: the deterministic eval suite stays green (it does), plus a
live maintenance-benchmark run (`--repeat 3`) whose pass-rate CI is not worse
than baseline. Until that run happens, this entry claims implementation only.

**LLM summary as an additive memory, not a replacement.** The summary is one
more semantic item (importance 0.75, `source: llm_summary`) competing in the
same recall ranking — rule-extracted memories are untouched, and a summary
failure costs nothing (`llm_summary_error_count` + silent fallback). Keyless
tests script the client; live quality assessment is deferred with the same
freeze rationale as above.

## Measurement

- Keyless: supersede-after-success, disabled-path byte-equality, anchored
  query capture, summary success/failure fallback — all in
  `tests/test_memory_compressor.py`.
- Live ablation pending (see promotion bar above).

## Open questions / next bets

1. Hygiene currently keys on "Observed failure" items only; "Files mentioned"
   memories could also go stale after large refactors.
2. Success detection is marker-based; a `run_tests` exit-code signal from the
   agent loop would be more precise than string matching.
3. Embedding-based recall remains deliberately out of scope (no new runtime
   dependencies); anchoring + hygiene are the cheap 80%.
