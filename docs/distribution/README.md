# Distribution work queue

Updated 2026-11-14. This is a preparation and measurement record, not a record of posts sent to
external communities. The current release is v2.1.0. PyPI is not yet an installation channel.

## Audience and message

Start with developers building or debugging coding agents. Lead with one inspectable failure:
two runs claim completion, but only one leaves test evidence; or a successful file read is
mistaken for failure because its source contains `error`.

Project description:

> An inspectable coding agent. Trace code changes, diagnose failed runs, and check the test
> evidence. Try it without a model key and export a standalone HTML report.

中文介绍：

> 一个能检查运行过程的编程 Agent：看清代码改动、失败原因和测试证据。
> 无需模型 key 即可体验，也能导出独立 HTML 报告。

## Prepared assets

| Asset | Use |
| --- | --- |
| [Interactive demo](https://hwfengcs.github.io/DM-Code-Agent/) | Immediate browser experience |
| [38-second walkthrough](../media/demo-walkthrough.mp4) | Show tested and untested completion |
| [English first run](../getting-started.en.md) · [中文](../getting-started.md) | Complete installation-to-report path |
| [Engineering articles](../articles/README.md) | Three existing stories with evidence and offline reproductions |
| [English post draft](launch.en.md) · [中文稿](launch.zh.md) | One concrete failure story, adapted to the channel |
| [Local-model recipe](../local-models.en.md) · [中文](../local-models.md) | Response to a concrete Xinference/Qwen use case |
| [Real maintenance case](../case-studies/failure-classification/README.md) · [中文](../case-studies/failure-classification/README_ZH.md) | Supplied checks pass while broader checks fail; reviewed report and exact replay |

## First two weeks

1. Select two relevant communities where the maintainer can answer technical questions.
   Check their current self-promotion rules and disclose authorship. Publish one adapted post
   per selected channel, with the demo and source evidence; avoid duplicate drive-by posts.
2. Record the actual post URL and date below. Answer reproducible installation and protocol
   problems. Improve the relevant recipe before expanding the feature surface.
3. After several days, publish the real maintenance case as a follow-up, including failures,
   supplied tests, human involvement, and the exact verification boundary.
4. Invite a few interested users to try one small task. Record whether they reached a report
   and what prevented completion; do not equate a star with actual usage.
5. Evaluate external trace import only after users supply a specific format and a task it
   would help them accomplish. Support one format first; missing records must remain unknown.

## Measurement

Capture a baseline and fresh snapshots after each post. GitHub traffic access requires repository
permission and an authenticated `gh` CLI. This script only reads the API and creates a new local
file; it does not publish, change repository settings, or store a token:

```bash
uv run --frozen python scripts/snapshot_github_traffic.py --output build/growth/before-post.json
```

Use a new filename every time. GitHub traffic covers a rolling window; do not add overlapping
windows together. Compare stars, visitors, referring sites, and concrete trial feedback over
matching intervals. `new stars / unique visitors` is at most a rough trend, not an attributed
conversion rate. Preserve raw snapshots locally and do not publish private traffic by default.

| Published at | Channel / actual URL | Topic | Snapshot paths | Trial feedback / next change |
| --- | --- | --- | --- | --- |
| Not published | — | Drafts prepared | Local snapshots under `build/growth/` | No attributable growth result yet |

## Release and claim checks

- Use the tested GitHub wheel URL until a real PyPI version is available and installable.
- Keep the demo's scripted decisions explicit. Its files, edits and unittest checks are real.
- Separate a maintenance case from a benchmark result. One repair does not establish an overall success rate.
- The local-model extension has offline protocol tests; do not claim a live Qwen result without running it.
- Refer to [the release guide](../releasing.md) for Trusted Publisher binding. Do not enable
  the PyPI job just to make a status badge appear.
- The [older v2 launch plan](../research-log/DISTRIBUTION_CHECKLIST.md) is retained as history;
  its removed modules and SWE-bench Lite wording are not current product claims.
