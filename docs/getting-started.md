# 快速开始

[English homepage](../README.md) · [中文首页](../README_ZH.md) · [在线交互演示](https://hwfengcs.github.io/DM-Code-Agent/)

先用离线演示检查一次代码修改，再配置模型，在自己的仓库中运行任务。

## 安装

需要 Python 3.10+。从 v2.1.0 GitHub Release 安装，前端产物随 wheel 分发，不需要 Node.js：

```bash
pip install "dm-code-agent[web] @ https://github.com/hwfengcs/DM-Code-Agent/releases/download/v2.1.0/dm_code_agent-2.1.0-py3-none-any.whl"
```

只需要 CLI 时不装 Web extra：

```bash
pip install https://github.com/hwfengcs/DM-Code-Agent/releases/download/v2.1.0/dm_code_agent-2.1.0-py3-none-any.whl
```

想隔离到独立工具环境，可以把第一条命令的 `pip install` 换为 `uv tool install`。
Release 附件见 [v2.1.0](https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v2.1.0)。

开发者从源码安装，使用 CI 相同的锁文件：

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
uv sync --frozen --extra dev
```

源码安装后，在下文命令前加 `uv run --frozen`，或激活 `.venv`。
不用 uv 时可以创建虚拟环境后执行 `pip install -e ".[dev]"`。

## 第一次体验：不需要模型或 API key

```bash
dm-agent-demo --output demo-run
dm-agent-web --sessions-dir demo-run/sessions --read-only
```

点击服务器打印的带 token 本地地址，打开两份演示会话：

1. `verified.jsonl`：先运行失败测试，修复 `retry.py` 的重试次数边界，再运行通过的测试。
2. `unverified.jsonl`：完成同一修改后直接结束。检查诊断中的验证缺口。

演示使用脚本化客户端驱动真实 Agent、文件工具和 `python -m unittest discover -s .`，不会发起模型请求。
它不读取用户配置或扩展，不操作你的真实项目。输出目录必须不存在或为空；重复运行请换一个目录名。

输出包含：

| 路径 | 内容 |
| --- | --- |
| `demo-run/sessions/` | 两份可供 CLI 和 Web 读取的 JSONL 会话 |
| `demo-run/verified/`、`demo-run/unverified/` | 两个独立的示例工作区，包含代码与测试 |
| `demo-run/before/retry.py` | 修改前的示例代码 |
| `demo-run/verified.patch`、`demo-run/unverified.patch` | 演示修改的 patch |
| `demo-run/manifest.json` | 演示产物清单与说明 |

命令行也能检查全部过程：

```bash
dm-agent-trace view demo-run/sessions/verified.jsonl
dm-agent-trace analyze demo-run/sessions/unverified.jsonl
dm-agent-trace diff demo-run/sessions/unverified.jsonl demo-run/sessions/verified.jsonl
```

这组演示解释“宣布完成”和“留下验证证据”的区别，不用于评价模型的成功率。

## 导出可审阅的报告

```bash
dm-agent-trace export demo-run/sessions/verified.jsonl --output report.html --include-content
```

用浏览器打开 `report.html`，无需服务器。示例包含公开的演示代码，适合体验内容导出。

真实任务默认使用摘要导出：省略 `--include-content` 即不带任务正文、代码、工具参数与输出片段。
开启该参数会额外加入脱敏内容和基于 `old_string` / `new_string` 的替换片段；它不是完整 Git diff。
分享前审阅文件，因为脱敏不能保证识别所有敏感信息。已有报告需要 `--force` 才能覆盖，源日志始终不能被导出覆盖。
细节见[会话与 trace](tracing.md)。

## 配置模型

只有运行真实模型任务才需要 API key。推荐在目标工作区创建 `.env`，填入所用供应商的变量：

```dotenv
DEEPSEEK_API_KEY=your-key
```

| 变量 | `--provider` |
| --- | --- |
| `DEEPSEEK_API_KEY` | `deepseek`（默认） |
| `OPENAI_API_KEY` | `openai` |
| `CLAUDE_API_KEY` | `claude` |
| `GEMINI_API_KEY` | `gemini` |

`.env` 按当前目录 `./.env`、用户目录 `~/.dm_agent/.env` 的顺序加载，已经导出的环境变量优先。
全局安装后也可以把 key 放在用户目录，不必为每个项目复制。不要将含 key 的文件提交到 Git。
仓库开发者可以复制 `.env.example` 为 `.env`。带 UTF-8 BOM 的 `.env` 也受支持。

非敏感设置如 provider、model、max_steps 放在 `config.json`，优先级为：

```text
CLI 参数 > ./config.json > ~/.dm_agent/config.json > 默认值
```

配置文件先到先得，项目级存在就使用它。交互设置向导写回已读取的文件；都不存在时写入用户目录。
自建网关或本地推理服务使用 `--base-url`，自定义供应商见[扩展开发](extensions.md)。

## 在自己的仓库中运行

切换到目标项目的工作目录，先试一个可审查的小任务：

```bash
dm-agent "分析当前项目结构，列出最适合优先测试的模块" --provider deepseek --trace sessions/review.jsonl --show-steps
dm-agent-trace analyze sessions/review.jsonl
```

`--show-steps` 实时显示过程，`--trace` 留下默认脱敏的会话记录。
Agent 使用你的本地文件和命令权限，并非沙箱；在 Git 工作区中执行、检查变更与测试结果。
完整 LLM I/O 需要显式开启 `--trace-llm-io`；`--trace` 与 `--checkpoint` 不能指向同一文件。

喜欢浏览器交互时执行 `dm-agent-web`，可在对话里提交任务并检查每一步。
只审查历史记录则用 `dm-agent-web --sessions-dir sessions --read-only`。详见 [Web 控制台](web.md)。

## 开发者本地验证

从源码安装 dev 依赖后，不需要 API key 即可运行以下检查。使用 uv 时在每条命令前加 `uv run --frozen`：

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
python -m mypy dm_agent
```

依赖变更后需运行 `uv lock` 并提交 `uv.lock`。前端开发检查见 [Web 控制台](web.md)。
根目录 `main.py` 仅保留 `python main.py` 的兼容入口，安装后请使用 `dm-agent` 或 `python -m dm_agent.cli`。
