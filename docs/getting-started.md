# 快速开始

## 安装

推荐用 [uv](https://docs.astral.sh/uv/)，按 `uv.lock` 可复现安装（CI 用的就是这条）：

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
uv sync --frozen --extra dev
```

传统方式：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

安装后有六个命令行入口，见 [CLI 参考](cli.md)。

## 配置 API key

API key **只从环境变量读取**，不会从 `config.json` 读，也不会被写进 trace：

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

在 `.env` 里填至少一个：

| 变量 | 供应商 |
| --- | --- |
| `DEEPSEEK_API_KEY` | deepseek（默认） |
| `OPENAI_API_KEY` | openai |
| `CLAUDE_API_KEY` | claude |
| `GEMINI_API_KEY` | gemini |

自建网关或本地推理服务用 `--base-url`，或用扩展注册自定义 provider（见
[扩展开发](extensions.md#自定义-llm-供应商)）。

## 跑第一个任务

```bash
dm-agent "分析当前项目结构，列出最适合优先测试的模块" --show-steps
```

`--show-steps` 会实时打印每一步的 thought / action / observation。

留一份可审计的记录：

```bash
dm-agent "修复 retry.py 的重试边界，并运行测试" \
  --trace sessions/retry-fix.jsonl \
  --report reports/retry-fix.md

dm-agent-trace view sessions/retry-fix.jsonl
dm-agent-trace analyze sessions/retry-fix.jsonl
```

trace 默认不含完整 prompt 与模型原始输出，细节见 [会话与 trace](tracing.md)。

## 本地验证

不需要 API key 就能跑完整套（与 CI 完全一致）：

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
python -m mypy dm_agent
```

改了 `pyproject.toml` 的依赖后要重新 `uv lock` 并提交 `uv.lock`，否则 CI 的
`uv lock --check` 会失败。

## 已知坑

- `python -m dm_agent.cli --help` **不可用**（包内没有 `__main__`）。用
  `dm-agent --help` 或 `python main.py --help`。
- 根目录 `main.py` 只是 `python main.py` 的兼容转发，不会作为顶级 `main` 模块安装。
