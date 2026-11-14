# Twelve targeted checks passed. The repair still wasn't ready.

[简体中文](README_ZH.md) · [Open the run report](https://hwfengcs.github.io/DM-Code-Agent/cases/failure-classification.html) · [Download HTML](report.html) · [Evidence manifest](evidence.json)

On 2026-11-14, DM-Code-Agent attempted a real repair in a detached checkout of its own
history. It fixed all 12 supplied regression checks. A broader test run then failed two
existing checks, and the agent used its remaining steps investigating before hitting its limit.
The patch is an **incomplete repair**, preserved for inspection; it was not merged into the
current agent.

## The actual defect

At commit [`bd35d253`](https://github.com/hwfengcs/DM-Code-Agent/tree/bd35d253abb18cabdaedf1caa1d5dd91cd985f59),
the failure classifier searched entire tool observations for markers such as `error`.
A successful read of `from errors import NotFound` could be classified as a failure.
Other real failures, such as a process exiting with code 2, could be missed.

This is a historical repository defect, subsequently fixed in
[`8025044`](https://github.com/hwfengcs/DM-Code-Agent/commit/8025044dd0b75f819e81ecb6d23e42a6b35d9a5b).
The new run started from its parent and received the [task](task.txt) and
[12 regression checks](regression_test.py.txt), not the historical solution. The agent running
the task was the current v2.1.0 implementation at `c07646a`.

## What the evidence says

| Check | Before the patch | After the patch |
| --- | --- | --- |
| Supplied regression checks | 5 passed, 7 failed | 12 passed |
| Historical suite plus supplied checks | 459 passed, 7 failed | 464 passed, 2 failed |
| Agent lifecycle | Started with a 14-step limit | `max_steps_exceeded` |

The model ran the targeted checks at steps 1 and 11, then the broader suite at step 12.
Both remaining failures are in `tests/test_evals.py`. The patch changes failure classification
in ways that the old eval fixtures do not accommodate; simply showing the 12 passing checks
would hide this integration problem. The original historical fix also changed eval fixture
content. This case's task allowed edits only to the classifier and its Agent call sites.

An independent offline replay applied the saved patch to a fresh checkout and reproduced the
same before/after results. See [before](before.txt), [after](after.txt),
[broader suite before](before-full-suite.txt), and [broader suite after](after-full-suite.txt).
Those are test results for an old checkout, not failures in today's main branch.

## Model, cost evidence, and intervention

- Configured provider/model: DeepSeek / `deepseek-chat`; responses reported `deepseek-flash`.
- One live attempt, 14 action steps, 17 completed client calls including planning/replanning.
  Transport retry attempts were not separately counted. This was a bounded case configuration:
  planning enabled, compression disabled, at most two replans, five file/test tools, and up to
  2,400 output tokens per request. Exact options are recorded in [evidence.json](evidence.json).
- The provider reported 164,476 prompt tokens and 4,670 completion tokens: 169,146 total,
  including 145,024 prompt cache-hit tokens. These are per-request usage totals, not unique
  context size or an invoiced cost. Billing was not queried. [Per-request usage](requests.json).
- The maintainer supplied the task and regression tests. No human edited the workspace during
  the run. The model changed only `dm_agent/core/observation.py` and `dm_agent/core/agent.py`;
  the supplied tests remained byte-for-byte unchanged.
- No new SWE-bench run or aggregate benchmark score was produced. One selected historical
  task cannot establish general coding ability, improvement, or a success rate.

## Reproduce without a model key

From a full clone with Git, Python 3.10+, and the development dependencies installed:

```bash
uv sync --frozen --extra dev
uv run --frozen python scripts/reproduce_maintenance_case.py --output build/case-reproduction --full-suite
```

For a shallow clone, first fetch the missing history with `git fetch --unshallow`.
The script creates a new detached worktree, installs the supplied checks, runs them, applies
the archived [agent patch](agent.patch), and repeats the checks. `--full-suite` also runs the
historical suite before and after. It makes **zero model calls** and does not change your
current checkout. The worktree and original outputs remain available for inspection; use a
new output directory for another run.

The script's exit code reports whether the targeted before/after behavior was reproduced.
The JSON records the broader suite's independent exit codes; reproduction success does not
mean the patch is ready to merge. Tests require a working development environment, and this
particular full-suite result was observed on Windows/Python 3.13.

## Inspect and share

The [HTML report](report.html) is a reviewed derivative of the real trace. It includes tool
receipts, replacement excerpts, the failing broader suite, and the run's incomplete status.
Local paths are replaced with placeholders. The original trace and worktrees are retained
locally; full model I/O was not captured. Artifact hashes are in [evidence.json](evidence.json).

For the simpler successful/untested comparison, use the [scripted browser demo](https://hwfengcs.github.io/DM-Code-Agent/).
For a real task in your own repository, follow the [English setup guide](../../getting-started.en.md).
