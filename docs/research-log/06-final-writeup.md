# 06 — Final write-up: v2 algorithm stack

## TL;DR

DM-Code-Agent v2 turns the original local ReAct agent into an inspectable code-agent research
baseline:

- SWE-bench Lite Tier-1 harness and frozen 50-instance baseline.
- Reflexion trial memory.
- Critic gate and self-consistency runner.
- Adaptive replanning and offline token economics.

The important constraint: the only real SWE-bench number currently published is still the P1
Tier-1 baseline (`0/50 resolved`, `36/50 patch applied`). We did not run Docker/Tier-2, new true
SWE-bench evaluations, or cross-model sweeps in the final pass.

## The Project Shape

The design goal is not to hide complexity behind a server. The agent is meant to be read:

- `dm_agent/core/agent.py` keeps the ReAct loop, planning, Reflexion injection,
  critic gate, and adaptive replan hook visible in one place.
- `dm_agent/tracing/` records enough JSONL structure to audit behavior without saving full prompts
  by default.
- `dm_agent/benchmarks/` keeps hidden-test coding and maintenance tasks in-tree, plus the
  SWE-bench Lite adapter.
- `docs/research-log/` records the design decisions and the current benchmark limits.

## What Worked

1. **Default-off algorithm modules.** Reflexion, critic, self-consistency, and adaptive
   replanning can be tested independently without changing baseline CLI behavior.
2. **Keyless tests.** The new modules use scripted clients and existing JSON
   reports. CI does not need API keys or network access.
3. **Trace-friendly design.** P2-P5 add explicit events (`trial_start`, `reflexion`,
   `critic_review`, `replan_decision`) instead of hiding behavior in prompts.
4. **Offline economics.** Cost-per-success reporting is generated from existing JSON. It never
   fetches prices or runs models.

## What Did Not Get Claimed

We deliberately do not claim a real score lift for any v2 mechanism yet.

The P1 Tier-1 baseline exposed host-verifier noise and dependency drift. Under the current freeze,
the correct move is to keep that number stable, document the limitation, and avoid inventing
ablation gains.

## Reproducible Local Checks

The final local checks are:

```bash
python -m pytest
python -m ruff check dm_agent tests
python -m black --check .
```

## Release Hardening Addendum

The v2 release pass also wires the default-off algorithm modules into the generic coding and
maintenance benchmark CLI. `--enable-critic` and `--self-consistency-runs` are
available for local smoke experiments, but they do not affect default runs.

SWE-bench Lite keeps the stricter freeze boundary: self-consistency is rejected before instance
loading so a missing snapshot or dataset cannot mask the policy decision. This prevents accidental
new SWE-bench claims during the frozen evaluation window.

The economics smoke report can be regenerated without model calls:

```bash
python -m dm_agent.benchmarks.economics \
  bench_reports/swebench_lite_baseline.json \
  --label swebench-tier1-baseline \
  --cost-per-1k-tokens 0.00027 \
  --output-json bench_reports/economics.json \
  --output-md bench_reports/economics.md
```

## Suggested Blog Outline

Title: `Building an auditable Python code agent: Reflexion, critic review, and the cost of SWE-bench`

1. Why local-first agent baselines still matter.
2. The v1 loop: ReAct, planner, tools, trace replay.
3. SWE-bench Lite Tier-1 harness and why official-equivalent numbers require Docker/Tier-2.
4. The v2 algorithm modules and why each is default-off.
5. Failure modes from the frozen baseline.
6. Token economics: why pass rate is not enough.
7. What remains: true Tier-2 verification, real ablations, and cross-model economics.

## Release Checklist

- README and README_EN show the v2 modules and frozen SWE-bench caveat.
- CHANGELOG has a 2.0.0 section.
- Devlogs 00-06 are linked from the research-log index.
- `bench_reports/economics.{json,md}` can be regenerated from existing reports.
- No test requires real LLM/API keys or external network.
