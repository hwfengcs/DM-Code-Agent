# 27 — Tool circuit breaker experiment (default-off)

## TL;DR

`--enable-circuit-breaker` adds a per-(action, error-kind) circuit breaker
(`dm_agent/core/circuit_breaker.py`): after `--circuit-breaker-threshold`
(default 3) consecutive identical-kind failures the tool is temporarily
disabled; calls during the cooldown (`--circuit-breaker-cooldown`, default 5
steps) are intercepted with a guidance observation that steers the model to a
different tool; after cooldown one probe attempt is allowed (half-open) —
success fully resets the counters, failure re-opens immediately. Default off,
audited via `circuit_breaker` trace events (`phase=blocked/opened`) and
`circuit_breaker_block_count` / `circuit_breaker_trip_count` metadata.

## Context

Entry 12 introduced repeated-failure *signatures* (metadata-only by design)
and entry 22 a replan-strategy experiment keyed on them. Neither prevents the
concrete waste pattern seen in traces: the model calls the same broken tool
with the same arguments many times, each round-tripping a full LLM call. The
breaker is the enforcement arm the signature work deliberately deferred.

## Design decisions

- **Key granularity: `action|error_kind`, no observation prefix.** The
  repeated-failure signature uses `action|error_kind|observation[:160]`; the
  breaker intentionally drops the observation component so P1's truncation or
  any wording change cannot affect trip decisions, and so failures with
  drifting error text (timestamps, temp paths) still accumulate.
- **Success fully resets.** After a successful probe, all failure counters
  for that action clear — otherwise a single later failure would insta-trip
  from the stale count, which reads as flapping rather than protection.
- **Interception text avoids failure markers** ("temporarily disabled", no
  error/failed/失败/错误), so a breaker block does not trigger replan or get
  memorized as a failure; blocked calls also do not mark plan steps
  completed.
- **Relation to entry 22.** The repeated-failure policy experiment changes
  *replan strategy*; the breaker changes *tool availability*. They compose
  but are independent flags with independent counters — the breaker does not
  read `_failure_signature` state.
- **Why default-off.** Unlike truncation/retry, the breaker changes what the
  agent is allowed to do; a miscalibrated threshold could block a tool that
  would have succeeded on attempt 4. Promotion bar mirrors entry 24: keyless
  suite green (it is) plus a live maintenance run showing fewer wasted steps
  on repeated-failure traces without pass-rate regression.

## Measurement

Keyless: `tests/test_circuit_breaker.py` — state-machine unit tests
(open-after-threshold, probe recovery, probe-failure re-open, success reset,
config validation) and scripted agent runs proving the fourth identical
failure is intercepted without executing the runner, plus default-off
behavioral identity.

## Open questions / next bets

1. Argument-aware keys (hash of action_input) would distinguish "same tool,
   different file" — deferred; error-kind granularity first.
2. Surfacing breaker state into the planner prompt (not just the observation)
   might help the model plan around a disabled tool earlier.
3. Candidate for `--enable-evolution` bundling once live data supports it.
