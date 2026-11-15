# 文档

按主题拆分，每份只讲一件事。[English homepage](../README.md) · [中文首页](../README_ZH.md) · [在线演示](https://hwfengcs.github.io/DM-Code-Agent/)。

## 上手

| 文档 | 内容 |
| --- | --- |
| [快速开始](getting-started.md) | 安装、离线演示、HTML 报告、配置模型与第一个真实任务 |
| [English getting started](getting-started.en.md) | Complete English installation, first task, reports, and troubleshooting |
| [本地模型](local-models.md) · [English](local-models.en.md) | Xinference/Qwen 的 Chat Completions 扩展与验证范围 |
| [真实维护案例](case-studies/failure-classification/README_ZH.md) · [English](case-studies/failure-classification/README.md) | 12 项检查通过后的集成失败；真实运行报告、补丁和零模型调用复现 |
| [CLI 参考](cli.md) | 九个命令行入口、配置优先级、全部开关及其默认值 |
| [Web 控制台](web.md) | `dm-agent-web`：会话审计、实时运行、安全模型、静态托管 |
| [在线演示与媒体](demo-site.md) | 静态展厅构建、公开证据来源、截图与录屏复现 |
| [能力清单](capabilities.md) | 能力总表、默认开/关的分类原则、上下文记忆 |

## 可独立阅读的技术文章

每篇包含最小复现、历史数据和结论边界。[文章索引](articles/README.md)同时提供中英文版本。

| 主题 | 中文 | English |
| --- | --- | --- |
| 更多步数为什么未必更成功 | [阅读](articles/01-more-steps.zh.md) | [Read](articles/01-more-steps.en.md) |
| 为什么源码中的 `error` 会误触发重规划 | [阅读](articles/02-error-is-not-failure.zh.md) | [Read](articles/02-error-is-not-failure.en.md) |
| 内容锚定编辑如何减少相邻代码误伤 | [阅读](articles/03-content-anchored-edits.zh.md) | [Read](articles/03-content-anchored-edits.en.md) |

## 深入

| 文档 | 内容 |
| --- | --- |
| [架构](architecture.md) | 分层、执行链、钩子位置、扩展加载流程、会话数据模型 |
| [扩展开发](extensions.md) | `ExtensionAPI` 参考、发现来源、安全模型、可运行示例 |
| [生命周期事件](lifecycle-events.md) | 六个事件的时机与返回值语义、异常隔离、内置能力 |
| [会话与 trace](tracing.md) | 条目结构、隐私、HTML 导出、fork、resume、非破坏式折叠 |

## 子系统

| 文档 | 内容 |
| --- | --- |
| [MCP 配置](mcp.md) | 接入 Playwright / Context7 / Filesystem / SQLite 等 MCP server |
| [Skill 系统](skills.md) | 内置技能、自定义技能（JSON 与 Python 两种方式）、激活机制 |
| [Benchmark](benchmarks.md) | benchmark suite、评分口径、报告字段、manifest 漂移检测 |

## 项目

| 文档 | 内容 |
| --- | --- |
| [项目现状与对标](project-status.md) | 同类项目对比、算法模块状态、评测口径说明、roadmap |
| [最近八轮进展](recent-progress.md) | devlog 36–43 的实验结论、SWE-bench Verified 20/50 归档与边界 |
| [改进 agent 系统](改进agent系统.md) | 基于 50 题实测的瓶颈诊断与 S0–S3 可执行方案、决策记录、不做清单、判读纪律 |
| [版本发布](releasing.md) | GitHub 安装包、校验和、PyPI Trusted Publishing 配置 |
| [传播准备](distribution/README.md) | 双语发布稿、渠道记录与本地 GitHub 流量快照 |
| [研究日志](research-log/) | 每个非平凡设计决策的动机、实验、ablation、踩坑 |
| [产品定位](product.md) | 目标用户与落地场景 |
| [v2.0.0 发布说明](release-v2.0.0.md) | 发布叙事与 smoke checklist |
| [v2.1.0 发布说明](release-v2.1.0.md) | 离线演示、可分享报告与新的上手入口 |
| [自主路线记录](autonomous-roadmap.md) | 按时间排列的自主迭代记录 |
| [项目审查记录（2026-11-13）](audit-2026-11-13.md) | 整仓审查记录：已修复项、待审查项与验证记录 |
| [项目审查记录（2026-11-14）](audit-2026-11-14.md) | 整仓审查记录：已修复项、待审查项与验证记录 |
| [项目审查记录（2026-11-15）](audit-2026-11-15.md) | 整仓审查记录：已修复项、待审查项与验证记录 |

## 架构图附件

`architecture.drawio` / `architecture.drawio.png` / `architecture-cn.png` 保留作为附件；
`project-overview-simple.drawio` / `project-overview-simple.png` 是面向非开发者的通俗总览图。
**文字版 [architecture.md](architecture.md) 是权威来源**——二进制图 AI 读不了、人也没法 diff，
架构改了图不一定会跟着更新。两者不一致时以文字版为准。
