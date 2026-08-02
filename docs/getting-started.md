# 快速开始

## 安装

装一个能直接用的版本（不需要克隆仓库，也不需要 Node——前端产物随 wheel 分发）：

```bash
pip install "dm-code-agent[web]"     # 带 Web 控制台
pip install dm-code-agent            # 只要命令行
```

想隔离环境或者干脆不装，用 [uv](https://docs.astral.sh/uv/)：

```bash
uv tool install "dm-code-agent[web]"                  # 装成独立工具
uvx --from "dm-code-agent[web]" dm-agent-web          # 不装，跑一次
```

**开发**这个项目才需要克隆（按 `uv.lock` 可复现安装，CI 用的就是这条）：

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

安装后有七个命令行入口，见 [CLI 参考](cli.md)。

## 配置 API key

API key **只从环境变量读取**，不会从 `config.json` 读，也不会被写进 trace。
`.env` 按下面的顺序查找，**已经导出的环境变量始终压过文件**：

| 顺序 | 位置 | 适合 |
| --- | --- | --- |
| 1 | 已导出的环境变量 | CI、临时覆盖 |
| 2 | `./.env`（当前工作目录） | 按项目区分 key |
| 3 | `~/.dm_agent/.env` | 全局装一次，在任何目录下都能用 |

全局安装后推荐第 3 种：

```bash
mkdir -p ~/.dm_agent && echo "DEEPSEEK_API_KEY=sk-xxx" >> ~/.dm_agent/.env
```

> **Windows 用户注意**：PowerShell 的 `>`、`Set-Content -Encoding utf8` 和记事本的
> 「UTF-8」另存都会写 BOM。本项目按 `utf-8-sig` 读 `.env`，所以带 BOM 也能正常工作；
> 但别的工具读同一个文件时未必——`Set-Content -Encoding ascii` 最省心。

克隆仓库开发时用第 2 种：

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

可填的变量：

| 变量 | 供应商 |
| --- | --- |
| `DEEPSEEK_API_KEY` | deepseek（默认） |
| `OPENAI_API_KEY` | openai |
| `CLAUDE_API_KEY` | claude |
| `GEMINI_API_KEY` | gemini |

自建网关或本地推理服务用 `--base-url`，或用扩展注册自定义 provider（见
[扩展开发](extensions.md#自定义-llm-供应商)）。

## 其余设置（config.json）

provider、model、max_steps 等非敏感设置存在 `config.json`，查找顺序与 `.env` 同理：

| 顺序 | 位置 |
| --- | --- |
| 1 | `./config.json`（当前工作目录） |
| 2 | `~/.dm_agent/config.json` |

交互式设置向导（`dm-agent` 不带任务参数进入）**写回它读到的那个文件**；两个都不存在时
落用户级。CLI 参数永远优先于文件，完整优先级见 [CLI 参考](cli.md)。

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

- 根目录 `main.py` 只是 `python main.py` 的兼容转发，不会作为顶级 `main` 模块安装。
  包内入口用 `dm-agent` 或 `python -m dm_agent.cli`。
