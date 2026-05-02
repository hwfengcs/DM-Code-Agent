# 01 — SWE-bench Lite baseline: harness, sampling, and the road to numbers

> **TL;DR.** Phase 1 lands the SWE-bench Lite harness (`dm_agent/benchmarks/swebench_lite/`)
> — loader, deterministic 50-instance subset, per-instance git workspace, Tier-1
> Python-host verifier, runner, failure-mode analyzer, and a CLI integration via
> `dm-agent-bench --suite swebench_lite`. The first real-model run is queued,
> not yet reported. This entry documents the harness design and the open
> question of how much absolute pass rate we should expect on Tier-1.

## Context

[Entry 00](00-kickoff.md) committed to publishing a SWE-bench Lite baseline
because no other piece of evidence calibrates a code agent's quality as
quickly. SWE-bench is the de-facto industry yardstick: 300 real GitHub
issues from 12 popular Python projects in the Lite split, scored by hidden
unit tests on real codebases.

Phase 1 builds the harness around DM-Code-Agent. Phase 1's pass rate is
intentionally a *baseline* — no Reflexion, no RAG, no Critic, no
Self-Consistency — so that the relative deltas in P2-P4 show up cleanly.

## Design

### Module layout

```
dm_agent/benchmarks/swebench_lite/
├── __init__.py     # public surface; lazy import for datasets-free import path
├── models.py       # SWEBenchInstance, SWEBenchResult, SWEBenchVerification, FailureCategory
├── loader.py       # HuggingFace + JSONL snapshot, deterministic 50-subset
├── workspace.py    # per-instance git checkout at base_commit + test_patch
├── verifier.py     # Tier-1 pytest-driven scoring
├── runner.py       # ReactAgent + workspace + verifier glue
└── analyzer.py     # failure-mode categorization
```

The package never imports `datasets` at module load time. Tests, CI, and
users without the optional `[swebench]` extra still get a working import; the
real loader is wired in via `__getattr__` and only triggers on actual data
access.

### Sampling: `fixed_subset_50`

The full Lite test split is 300 instances; running all of them every time we
change something would burn API credits we don't have. We sample 50 with a
deterministic strategy (`seed=42`, `max_per_repo=5`) and freeze the
result by recording its 12-character SHA-256 signature into every benchmark
report.

The strategy is repo-balanced round-robin: groups instances by repo, shuffles
within each group, then sweeps repos in shuffled order picking one instance at
a time until we hit 50. This prevents Django (which dominates the dataset)
from consuming half the budget.

### Workspace: cache-then-clone

Per-instance setup uses one bare cache per repo plus a cheap full clone
into a per-instance workspace:

```
~/.cache/dm-agent/swebench_lite/repos/
    django__django/         # bare clone, --filter=blob:none
    sympy__sympy/
    ...
```

The first time we touch e.g. `django/django`, we run a partial bare clone
(~120 MB instead of ~2 GB). All subsequent Django instances reuse it.
Per-instance workspaces are full clones from the local bare cache, fast and
offline-friendly. We commit the test_patch on top of `base_commit` so that
the agent's later changes can be diffed against `HEAD` to extract its
prediction cleanly.

### Verifier: Tier-1 vs Tier-2

The verifier runs in two tiers:

- **Tier-1 (default)**: each `FAIL_TO_PASS` and `PASS_TO_PASS` test node
  runs as a separate `python -m pytest` call inside the workspace, using
  the *host* Python and *host*-installed dependencies.
- **Tier-2 (planned, `--use-docker`)**: delegate to the official
  `swebench` harness containers. Currently `NotImplementedError`. Tracked.

Tier-1 trades coverage for simplicity. Many Lite instances need a specific
historical Python (e.g. 3.6 for older Django) or repo-specific extras, and
those will not pass on a developer machine running Python 3.11 with a fresh
venv. We expect Tier-1 coverage to land in the 40-60% range; instances that
the verifier cannot exercise show up as `patch_apply_failed` /
`hidden_test_fail` rather than crash the run.

This is the single biggest known gap in P1 and the reason Tier-2 exists in
the design from day one.

### Per-instance failure classification

Every failed run gets one `FailureCategory`. The bucket order is the
priority order — if a run "would" satisfy multiple buckets, we report the
most actionable:

```
PATCH_NOT_PRODUCED   →  P2 Reflexion / P5 Adaptive Replanning
PATCH_APPLY_FAILED   →  P3 RAG (better hunk context)
HIDDEN_TEST_FAIL     →  P4 Critic + Self-Consistency
REGRESSION           →  P4 Critic + Self-Consistency
MAX_STEPS            →  P5 budget tuning
PARSE_ERROR          →  P2 / P5
TOOL_ERROR           →  fix-forward today
TIMEOUT              →  budget tuning
UNKNOWN              →  manual triage
```

The mapping back to phases is the whole point: the failure-mode
distribution we measure here decides which P2-P4 features get prioritized.

## Hyperparameters chosen for the baseline

| Parameter | Value | Why |
| --- | --- | --- |
| Provider | DeepSeek (deepseek-chat / V3) | cheapest plausible model, $0.27/M input |
| Subset | `fixed_subset_50(seed=42)` | reproducible, repo-balanced |
| `max_steps` | 60 | enough for inspect → edit → run-test cycle on most tasks |
| Temperature | 0.0 | greedy, eliminates run-to-run variance for the baseline |
| Skills | enabled | matches default user experience |
| Planning + Compression | enabled | matches default user experience |
| `instance_test_timeout` | 300 s | per pytest node |

## Cost estimate (pre-run)

Empirically, each instance ships ~5-10k tokens of problem statement + tools
prompt. With ~30-50 ReAct steps and average 4-8 tool calls per step, we
expect ~200k input tokens / instance + ~30k output tokens / instance.
Across 50 instances at DeepSeek v3 prices:

```
50 × (200_000 × 0.27 + 30_000 × 1.10) / 1_000_000 ≈ $4.4
```

A second run (e.g. for the no-skills ablation later) is ≈$4.4 again.
Total Phase 1-5 budget envelope stays well under $50 if we stay on
DeepSeek for the heavy lifting and reserve Claude / GPT for the
20-instance cross-model entry in P5.

## Reproducing (will be filled in once the baseline run lands)

```bash
pip install -e ".[dev,swebench]"

# List the deterministic subset
dm-agent-bench --suite swebench_lite --list \
  > bench_reports/swebench_lite_subset.json

# Run the baseline (DeepSeek)
dm-agent-bench --suite swebench_lite \
  --provider deepseek \
  --max-instances 50 \
  --output bench_reports/swebench_lite_baseline.json \
  --markdown bench_reports/swebench_lite_baseline.md \
  --trace-dir bench_reports/swebench_lite_traces
```

## Status

- [x] Harness implemented: loader, workspace, verifier, runner, analyzer.
- [x] CLI integration: `dm-agent-bench --suite swebench_lite`.
- [x] Unit tests (14) passing without the `[swebench]` extra.
- [ ] First baseline run: pending real DeepSeek API key + machine time.
- [ ] Failure-mode distribution: pending baseline run.
- [ ] README badge update: pending baseline run.
- [ ] Tier-2 docker verifier: deferred to post-P1 (or P5 if needed for
      reproducing instances Tier-1 can't exercise).

## Open questions / next bets

1. **Tier-1 coverage.** What fraction of the 50 instances survive
   `pytest <node_id>` on a vanilla Python 3.11? Below ~60% we should
   prioritize the docker harness; above that we can keep the Tier-1 line
   as the primary number and treat Tier-2 as cross-check.
2. **Subset signature drift.** If HuggingFace re-publishes the dataset (it
   has happened in the past), `fixed_subset_50` could yield different
   instances on a fresh cache. The signature in every report makes this
   visible; we will commit a frozen subset JSONL once the first baseline
   run completes.
3. **Patch extraction drift.** `git diff HEAD` is sensitive to whitespace
   and line endings. We may need to canonicalize the agent's diff before
   re-applying it during verification on Windows machines. Track in
   the workspace test suite once we hit a real failure.

## Status flag

This entry is **active** until the first baseline run lands. After that, it
freezes and entry 02 picks up with Reflexion's relative gains.
