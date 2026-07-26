# 28 — Evals: recovery rate, capability breakdown, stability, and CI gates

## TL;DR

The evals track closes the loop on P1/P2: new metrics measure the new
mechanisms, and CI now enforces quality instead of only compilation.

1. **Recovery success rate** — `recovered_runs / runs_with_failures` (a run
   "had failures" when any of parse/tool/unknown/argument/critic/edit-guard
   counters is non-zero). Replaces interpretation of the old
   `recovery_events` occurrence counter, which is kept for compatibility.
   Added to eval summaries, benchmark summaries (per variant), and trace
   directory aggregation.
2. **Per-tag capability breakdown** — `by_tag` in eval/benchmark summaries
   (opt-in via the new `tasks=` parameter, so old callers see no change).
3. **Hallucination proxies in the trace analyzer** — `hallucination_signals`
   per trace and aggregated per directory: edits without a prior read,
   edit-guard blocks, truncated observations (+rate), missing-path
   references. Deliberately NOT wired into the `_trace_health` score until
   calibrated against outcomes.
4. **Repeat stability** — with `--repeat`, benchmark summaries add per-task
   `pass@k` / `pass^k` / per-repeat pass lists and a task pass-rate stddev.
   Honestly named *repeat variance*: same config, API nondeterminism
   included, not a controlled-seed experiment.
5. **Per-test partial credit** — `dm-agent-bench --per-test-credit` runs
   hidden tests node-by-node (mirroring the SWE-bench verifier pattern,
   without importing the swebench package). Advisory only: strict scoring,
   Wilson CIs, manifests, and the freeze statement are untouched.
6. **CI quality gates** — CI now runs the *full* keyless eval suite and
   fails below 100% (`dm_agent/evals/gate.py`), and guards benchmark task
   definitions against silent drift: `dm-agent-bench --manifest-only`
   regenerates the manifest keylessly and `dm-agent-manifest-diff` compares
   it against the checked-in baselines
   (`bench_reports/manifest-baseline-{coding,maintenance}.json`, exit 1 on
   drift). Changing a benchmark task now requires regenerating the baseline
   in the same PR — attaching the diff output, per CONTRIBUTING.
7. **New keyless eval tasks** — `truncated_read_pagination` (hits the
   truncation cap via `agent_overrides={"max_observation_chars": 400}`, then
   pages with line ranges) and `edit_guard_reread` (blocked blind edit →
   read → edit). `EvalTask.agent_overrides` is the general mechanism for
   behavior-guard evals.

## Boundaries and deferrals

- **Budget-compression coverage** lives in a scripted agent unit test
  (`tests/test_agent_guards.py::test_token_budget_forces_early_compression`)
  rather than an eval task: the eval harness constructs the agent with the
  fixed compressor window (`keep_recent=8`), so triggering compression there
  would need a 17+ message script for no additional wiring coverage.
- **Retry / checkpoint / resume are unit-tested, not eval tasks** — they need
  fault-injecting clients or cross-process semantics the scripted eval
  framework intentionally does not model.
- **LLM-as-judge is deferred without a stub.** Keyless-first is this
  project's identity; a judge adds network, keys, and nondeterminism to the
  default suite. Sketch for when live evals unfreeze: a `JudgeClient`
  attached to `evals/real_runner.py` scoring `final_answer` against a
  per-task rubric, reported as advisory alongside (never instead of) the
  deterministic validators. The deterministic proxies above cover the current
  problem surface.
- **Hallucination proxies stay out of `_trace_health` weights** until we have
  enough traces to calibrate deduction sizes against real outcomes; the
  aggregation added here is exactly the data collection needed for that
  decision.

## Compatibility

- All new summary fields are additive; `recovery_events` kept.
- Aggregations read new metadata keys with `.get(key, 0)`; a test feeds a
  v2.0-era result (no new counters) through the summarizer.
- The eval task list grew (14 tasks); eval reports have no manifest/signature
  mechanism, so no guard is affected. Benchmark task definitions are
  untouched in this whole phase → `suite_signature` stable → the new CI
  manifest guard is green on introduction.

## Measurement

Keyless: `tests/test_evals.py` (rate math, None-denominator, by-tag, legacy
metadata, new tasks × 4 variants, gate pass/fail/unreadable),
`tests/test_coding_benchmarks.py` (benchmark rate/tags/stability math,
per-node credit on a synthetic workspace incl. collection-error fallback,
manifest-only CLI, bare-manifest diff drift), `tests/test_tracing.py`
(hallucination signals on synthetic traces, zero-defaults for legacy traces).

## Open questions / next bets

1. Calibrate hallucination-proxy weights into `_trace_health` once enough
   directory aggregates exist.
2. `pass^k` on the maintenance suite with `--repeat 3` is the cheapest next
   live experiment when the freeze lifts — it directly measures whether the
   P1/P2 guards reduce variance, not just means.
3. A gate over benchmark reports (pass-rate threshold vs a stored baseline
   JSON) once real runs resume; the eval gate pattern transfers directly.
