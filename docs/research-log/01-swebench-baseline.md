# 01 — SWE-bench Lite baseline: harness, sampling, and the road to numbers

> **TL;DR.** Phase 1 lands the SWE-bench Lite harness (`dm_agent/benchmarks/swebench_lite/`)
> — loader, deterministic 50-instance subset, per-instance git workspace, Tier-1
> Python-host verifier, runner, failure-mode analyzer, and a CLI integration via
> `dm-agent-bench --suite swebench_lite`. The first 50-instance DeepSeek
> Tier-1 baseline is now published: **0/50 resolved (0.0%)**,
> **36/50 patches applied (72.0%)**. A follow-up gold-patch smoke audit
> confirmed that the Tier-1 host verifier is noisy, so this run is useful as a
> harness/trace baseline but should **not** be treated as an official
> SWE-bench-equivalent score.

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

## Reproducing

```bash
pip install -e ".[dev,swebench]"

# List the deterministic subset
dm-agent-bench --suite swebench_lite --list \
  > bench_reports/swebench_lite_subset.json

# Run the baseline (DeepSeek)
dm-agent-bench --suite swebench_lite \
  --provider deepseek \
  --max-instances 50 \
  --resume \
  --output bench_reports/swebench_lite_baseline.json \
  --markdown bench_reports/swebench_lite_baseline.md \
  --trace-dir bench_reports/swebench_lite_traces
```

The run in this entry was resumed from earlier partial work. The final report
records `resume.reused_results=8`, so 42 instances were newly executed during
the final baseline window and 8 completed results were reused by `--resume`.

## Baseline results

Artifacts:

- JSON: `bench_reports/swebench_lite_baseline.json`
- Markdown: `bench_reports/swebench_lite_baseline.md`
- Traces: `bench_reports/swebench_lite_traces/*.jsonl`

Subset:

| Field | Value |
| --- | --- |
| Split | SWE-bench Lite test split |
| Selection | `fixed_subset_50(seed=42, max_per_repo=5)` |
| Selected instances | 50 / 300 |
| Subset signature | `30e25d14e380` |
| Provider / model | `deepseek` / `deepseek-chat` |
| Docker verifier | `False` (Tier-1 host Python verifier) |
| Resume reused results | 8 |

Summary:

| Metric | Value |
| --- | ---: |
| Total | 50 |
| Resolved | 0 |
| Resolved rate | 0.0% |
| Patch-applied rate | 72.0% |
| Avg steps | 47.14 |
| Avg tool calls | 43.36 |
| Avg estimated tokens | 483,885 |
| Total LLM requests | 3,419 |
| Avg duration | 349.2 s |

Failure-mode distribution, computed with
`dm_agent.benchmarks.swebench_lite.analyzer.summarize_failure_modes`:

| Category | Count | % of failures | % of total |
| --- | ---: | ---: | ---: |
| `patch_not_produced` | 13 | 26.0% | 26.0% |
| `patch_apply_failed` | 1 | 2.0% | 2.0% |
| `regression` | 36 | 72.0% | 72.0% |

Representative failures:

| Instance | Analyzer category | Runner reason | Signal | Next bet |
| --- | --- | --- | --- | --- |
| `psf__requests-2674` | `patch_not_produced` | `no_patch_produced` | Hit 60 steps / 60 tool calls and spent 1.22M estimated tokens without emitting a diff. | P2/P5 should force earlier reflection and a smaller finish criterion. |
| `django__django-15814` | `patch_apply_failed` | `patch_apply_failed` | `git apply` rejected the generated diff because a header lacked filename information. | P3 can improve hunk context; verifier should also canonicalize malformed diffs where possible. |
| `pytest-dev__pytest-8906` | `regression` | `pass_to_pass_regression` | FAIL_TO_PASS passed 1/1, but PASS_TO_PASS only passed 66/84; verifier tail includes a pytest node-id lookup failure. | P4 can catch behavioural regressions, but this sample also points at Tier-1 test-node drift. |
| `sphinx-doc__sphinx-8474` | `regression` | `fail_to_pass_unresolved` | PASS_TO_PASS was 0/436 and the verifier failed importing `docutils` in the host environment. | Tier-2 Docker is needed to separate agent quality from missing historical dependencies. |
| `pydata__xarray-4493` | `regression` | `fail_to_pass_unresolved` | Patch applied and many PASS_TO_PASS tests passed (1375/1689), but FAIL_TO_PASS stayed 0/1. | Better retrieval and a critic pass should target the actual failing behaviour instead of broad edits. |

### Tier-1 verifier audit

This number is intentionally honest, but it is not yet an official
SWE-bench leaderboard-style score. The P1 verifier runs hidden tests on the
host conda Python environment instead of the official per-instance Docker
images. That makes the run cheap and debuggable, but it also injects noise:

- older Django / sklearn / pytest / Sphinx instances expect historical Python
  and dependency versions;
- some PASS_TO_PASS failures are import or pytest-node lookup errors rather
  than clear behavioural regressions from the agent patch;
- the analyzer prioritizes PASS_TO_PASS breakage as `regression`, so
  host-environment failures can dominate the distribution even when the agent
  terminal state was `max_steps_exceeded` or `fail_to_pass_unresolved`.

After seeing `0/50`, we ran a gold-patch smoke audit on the same Tier-1
verifier:

| Instance | Gold-patch smoke result | What it proves |
| --- | --- | --- |
| `sphinx-doc__sphinx-8474` | The official patch still failed both sampled FAIL_TO_PASS and PASS_TO_PASS nodes because `tests/conftest.py` could not import `docutils`. | Missing historical dependencies can make a correct patch look unresolved. |
| `pytest-dev__pytest-8906` | The official patch passed normal sampled nodes, but dataset PASS_TO_PASS IDs like `testing/test_skipping.py::TestXFail::test_xfail_raises[TypeError-TypeError-*1` returned `ERROR: not found`. | Some parameterized pytest node IDs drift under the local pytest/runtime combination. |

The practical reading is: **P1 established a reproducible harness, trace set,
resume path, and failure taxonomy; the 0.0% Tier-1 number should not be used
as a public leaderboard comparison. Tier-2 Docker is now the gating item before
publishing a strong external SWE-bench claim.**

## Status

- [x] Harness implemented: loader, workspace, verifier, runner, analyzer.
- [x] CLI integration: `dm-agent-bench --suite swebench_lite`.
- [x] Unit tests (16) passing without the `[swebench]` extra.
- [x] First baseline run: DeepSeek 50-instance Tier-1 baseline complete.
- [x] Failure-mode distribution: `regression=36`, `patch_not_produced=13`,
      `patch_apply_failed=1`.
- [x] README badge update: 0.0% Tier-1 baseline, explicitly marked as
      non-official.
- [ ] Tier-2 docker verifier: deferred to post-P1 (or P5 if needed for
      reproducing instances Tier-1 can't exercise).

## Open questions / next bets

1. **Tier-1 coverage.** The baseline confirms that Tier-1 host verification is
   noisy below the threshold where we should make strong external claims.
   Docker-based Tier-2 should move up if we want a leaderboard-comparable
   number, even if P2/P3 ablations continue on Tier-1 for cost reasons.
2. **Subset signature drift.** The baseline subset signature is
   `30e25d14e380`. If HuggingFace republishes the dataset and a fresh cache
   changes the selected IDs, this signature will make the drift visible.
3. **Patch extraction drift.** `django__django-15814` produced a malformed
   diff header, confirming that canonicalization / repair around generated
   patches deserves a small verifier hardening pass.

## Status flag

This entry is now **frozen** as the P1 harness and Tier-1 baseline record.
Entry 02 can use the trace taxonomy for Reflexion design and measure relative
gains against this 0.0% line, but a leaderboard-comparable score should wait
for Tier-2 Docker verification.
