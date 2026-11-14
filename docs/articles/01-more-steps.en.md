# More steps did not establish a better coding agent

[中文](01-more-steps.zh.md) · [All articles](README.md) · [Interactive demo](https://hwfengcs.github.io/DM-Code-Agent/)

An agent runs out of steps. The obvious intervention is to raise the limit. In a historical DM-Code-Agent experiment, that increased the pass count from 22/30 to 24/30. It also introduced four regressions and increased estimated token use by 30.6%.

The useful result was not the higher score. It was finding out what the agent was spending its steps on.

## The experiment

On August 4, 2026, we compared two single runs of the same 30 coding and maintenance tasks. Both used `deepseek-chat`, temperature 0, declared allowed files, and the same scoring rules. The intervention changed each task's step limit from its supplied 14–20 steps to 30. At that revision, the budget itself was not included in the model prompt.

| Measure | Task-specific limits | Limit of 30 |
| --- | ---: | ---: |
| Passed tasks | 22/30 | 24/30 |
| Average steps | 11.7 | 14.2 |
| Estimated tokens | 1,458,155 | 1,903,954 |
| Runs exhausting the budget | 4 | 1 |
| Trace-identified editing self-damage events | 13 | 25 |
| Tasks with those events | 6/30 | 9/30 |

Ten tasks changed outcome: six fixes and four regressions. The total improved by two; the behavior was much less stable than that net number suggests.

“Editing self-damage” was the historical trace review's category for steps where the agent recognized that its own edit had broken or unintentionally removed code. It is a reviewed process metric, not an independently scored benchmark result. Token totals are estimates from the reports, not an invoice.

## Two different reasons for exhaustion

One baseline trace had working code and was about to finish. In `cross_file_user_contract`, the agent spent its last steps checking files after tests had passed. A larger budget could plausibly help that kind of run reach completion.

Other traces showed repeated repairs of damage introduced by previous edits. In `semver_compare`, a replacement removed `core = parts[0]`; a subsequent insertion put it in the wrong place. Those extra steps were paying for the editing interface's mistakes.

The follow-up trace inspection mattered more than the count of exhausted runs. Of the four previously exhausted tasks, only `packaging_ci_contract` actually used more than its old limit: 21 steps against a limit of 20. It still failed. The other three completed in 9, 13, and 16 steps—below their former limits. Those successes cannot be explained by access to the newly available steps.

There is also a correction to the original explanation. The first write-up blamed stale line numbers. [The next investigation](../research-log/38-edit-file-precision.md) found that the read-before-edit guard already rejected stale reads. The concrete failure was selecting the wrong range even from a fresh read, combined with a receipt that did not show the resulting code.

## Reproduce the report comparison offline

Clone and install the [project](../../README.md), then run from its root:

```bash
python -m dm_agent.benchmarks.score_diff bench_reports/ablation-scope-20260804.json bench_reports/steps30-20260804.json
```

This reads two saved reports and makes no model calls. Exit code **1 is expected** because the comparison contains regressions. It reproduces the aggregate and per-task comparison, not the historical trace review.

To verify the pass counts and token calculation directly:

```python
import json
from pathlib import Path

names = ["ablation-scope-20260804.json", "steps30-20260804.json"]
reports = [json.loads((Path("bench_reports") / name).read_text(encoding="utf-8"))
           for name in names]
for report in reports:
    summary = report["summary"]
    print(summary["variants"]["full"]["successes"],
          summary["total_estimated_tokens"])
before, after = [r["summary"]["total_estimated_tokens"] for r in reports]
print(f"Estimated token increase: {(after / before - 1) * 100:.1f}%")
```

Expected values: `22 1458155`, `24 1903954`, and `30.6%`.

## What this does—and does not—show

This comparison did not establish that increasing the budget improved the agent. It also does not establish that more steps are always harmful. There was one run per configuration, model output varied despite temperature 0, and the overall score hid both fixes and regressions. Later repeat runs showed further task-level variability; a historical noise heuristic is not a statistical significance test.

For the next engineering change, the actionable evidence was narrower: an exhausted run may have a budget problem, or it may be repeatedly repairing its own work. Inspect the last actions, check whether the new budget actually bound the outcome, and track regressions alongside the total score. In this project, that led to [changing the editing interface](03-content-anchored-edits.en.md).

## Evidence

- [Original experiment and trace excerpts, devlog 37](../research-log/37-step-budget-and-edit-self-damage.md)
- [Baseline report](../../bench_reports/ablation-scope-20260804.json) and [30-step report](../../bench_reports/steps30-20260804.json)
- [Corrected editing mechanism, devlog 38](../research-log/38-edit-file-precision.md)
- [Follow-up repeated-run discussion, devlog 39](../research-log/39-observation-failure-classification.md)

[DM-Code-Agent](../../README.md) records the steps needed for this kind of investigation. [Try the no-key demo](../getting-started.en.md) to compare a run with test evidence against one that finishes without it.
