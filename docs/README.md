# 文档

按主题拆分，每份只讲一件事。

## 上手

| 文档 | 内容 |
| --- | --- |
| [快速开始](getting-started.md) | 安装、配置 API key、跑第一个任务、本地验证 |
| [CLI 参考](cli.md) | 六个命令行入口、配置优先级、全部开关及其默认值 |
| [能力清单](capabilities.md) | 能力总表、默认开/关的分类原则、上下文记忆 |

## 深入

| 文档 | 内容 |
| --- | --- |
| [架构](architecture.md) | 分层、执行链、钩子位置、扩展加载流程、会话数据模型 |
| [扩展开发](extensions.md) | `ExtensionAPI` 参考、发现来源、安全模型、可运行示例 |
| [生命周期事件](lifecycle-events.md) | 六个事件的时机与返回值语义、异常隔离、内置能力 |
| [会话与 trace](tracing.md) | 条目结构、两个保真档、fork、resume、非破坏式折叠 |

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
| [研究日志](research-log/) | 每个非平凡设计决策的动机、实验、ablation、踩坑 |
| [产品定位](product.md) | 目标用户与落地场景 |
| [v2.0.0 发布说明](release-v2.0.0.md) | 发布叙事与 smoke checklist |
| [自主路线记录](autonomous-roadmap.md) | 按时间排列的自主迭代记录 |

## 架构图附件

`architecture.drawio` / `architecture.drawio.png` / `architecture-cn.png` 保留作为附件。
**文字版 [architecture.md](architecture.md) 是权威来源**——二进制图 AI 读不了、人也没法 diff，
架构改了图不一定会跟着更新。两者不一致时以文字版为准。
