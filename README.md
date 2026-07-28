# DM-Code-Agent

<div align="center">

**本地优先、可审计、有算法骨架的 Python Code Agent**

[![CI](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/Docs-docs%2F-purple.svg)](docs/)
[![Research Log](https://img.shields.io/badge/Research%20Log-active-orange.svg)](docs/research-log/)

**中文** | [English](README_EN.md)

</div>

在本地工作区跑 ReAct 循环，读写文件、跑测试、跑 lint、调 MCP 工具，
并把每一步计划、工具调用和观察结果写成 append-only 的 JSONL 会话日志。

它不是又一个聊天黑盒，而是一个开发者能看懂、能复现、能扩展、能拿来做对比研究的
Code Agent baseline：内核只有 ReAct 主循环，Reflexion / Critic / 熔断这些能力是挂在
生命周期钩子上的扩展；上下文折叠不删原文，所以 ablation 结论可以被验证。

## 安装

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
uv sync --frozen --extra dev        # 或 pip install -e ".[dev]"
cp .env.example .env                # 填入至少一个 API key
```

## 跑一个

```bash
dm-agent "分析当前项目结构，列出最适合优先测试的模块" --show-steps

dm-agent "修复 retry.py 的重试边界，并运行测试" --trace sessions/fix.jsonl
dm-agent-trace analyze sessions/fix.jsonl
```

测试、确定性 eval 和 benchmark manifest 检查都**不需要 API key**：

```bash
python -m pytest && python -m dm_agent.evals.cli --variant full --task direct_finish
```

## 文档

从 **[docs/](docs/)** 开始，那里有完整导航。最常用的四份：

- [快速开始](docs/getting-started.md) — 安装、配置、第一个任务、本地验证
- [CLI 参考](docs/cli.md) — 六个入口、全部开关及默认值
- [架构](docs/architecture.md) — 分层、执行链、钩子位置、会话数据模型
- [扩展开发](docs/extensions.md) — 不改内核加工具/守卫/供应商

评测口径与同类项目对比见 [项目现状](docs/project-status.md)。
**本项目不声明任何未实际运行过的评测分数。**

## 贡献

先读 [CONTRIBUTING.md](CONTRIBUTING.md)、[AGENTS.md](AGENTS.md)、[SECURITY.md](SECURITY.md)、
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。涉及算法决策或非平凡 ablation 的改动，
请在 [`docs/research-log/`](docs/research-log/) 留一篇 devlog。

## License

MIT License. See [LICENSE](LICENSE).
