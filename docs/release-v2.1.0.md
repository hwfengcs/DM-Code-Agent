# DM-Code-Agent v2.1.0 — inspect the run, share the evidence

DM-Code-Agent is a local coding agent whose changes, failures, and verification steps can be inspected. This release makes that workflow easier to try and easier to share.

[Interactive demo](https://hwfengcs.github.io/DM-Code-Agent/) · [English homepage](https://github.com/hwfengcs/DM-Code-Agent/blob/main/README.md) · [中文介绍](https://github.com/hwfengcs/DM-Code-Agent/blob/main/README_ZH.md)

## Try a complete run without an API key

```bash
pip install "dm-code-agent[web] @ https://github.com/hwfengcs/DM-Code-Agent/releases/download/v2.1.0/dm_code_agent-2.1.0-py3-none-any.whl"
dm-agent-demo --output demo-run
dm-agent-web --sessions-dir demo-run/sessions --read-only
```

The new `dm-agent-demo` uses a scripted client with the real agent, file tools, and Python unittest. It creates two isolated runs: one that fixes a retry bug and runs tests, and one that finishes the edit without verification. Inspect the difference in the CLI or browser console. It needs no model key, reads no user configuration or extensions, and refuses to overwrite a nonempty output directory.

This is a deterministic product demonstration, not a live-model evaluation.

## Export a report that works without a server

```bash
dm-agent-trace export demo-run/sessions/verified.jsonl --output report.html --include-content
```

The standalone HTML export shows outcomes, execution steps, verification evidence, and replacement excerpts when content is included. The default export is a structural summary. `--include-content` explicitly adds redacted content; review reports before sharing them. `--force` is required to replace an existing report, and export cannot overwrite its source log.

## A clearer entry point and reusable engineering stories

- English default README with a full Chinese version and a compatibility link at `README_EN.md`.
- Browser demo, real screenshots, and a walkthrough so the inspection workflow is visible before installation.
- Three bilingual articles with offline reproductions and original evidence: [step budgets](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/articles/01-more-steps.en.md), [failure classification](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/articles/02-error-is-not-failure.en.md), and [content-anchored editing](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/articles/03-content-anchored-edits.en.md).

## Boundaries

The agent runs with local file and command permissions; it is not a sandbox. Trace redaction remains the default, full model I/O remains opt-in, and replay that executes tools remains explicit. An observed test run is evidence to inspect, not proof of correctness.

The bundled coding and maintenance benchmark remains 30 hidden-test tasks. This release does not claim a new model score or a leaderboard improvement. Historical results and their limitations remain linked from the documentation.

## 中文摘要

v2.1.0 把“看清 Agent 做了什么”变成可以直接体验和分享的流程：

- `dm-agent-demo` 无需 API key，使用真实文件工具和 unittest，生成“有验证”和“跳过验证”两次运行。
- `dm-agent-trace export` 导出无需服务器的单文件 HTML，默认摘要，显式开启内容导出后提供脱敏片段。
- 英文默认首页、中文完整首页、在线演示和三篇双语技术文章，统一安装与上手入口。

演示不是模型评测，历史实验不代表本次发布取得新的分数提升。真实项目仍需检查变更与测试结果，分享报告前需审阅内容。
