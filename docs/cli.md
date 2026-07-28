# CLI 参考

## 六个入口

`pyproject.toml` 的 `[project.scripts]` 定义了六个命令：

| 命令 | 实现 | 用途 |
| --- | --- | --- |
| `dm-agent` | `dm_agent.cli:main` | 主 CLI：跑任务、交互模式 |
| `dm-agent-trace` | `dm_agent.tracing.cli:main` | `view` / `analyze` / `analyze-dir` / `replay` / `diff` / `fork` |
| `dm-agent-bench` | `dm_agent.benchmarks.cli:main` | coding / maintenance / swebench-lite benchmark |
| `dm-agent-eval` | `dm_agent.evals.cli:main` | 确定性 eval（无需 API key） |
| `dm-agent-economics` | `dm_agent.benchmarks.economics:main` | 离线 token 成本核算 |
| `dm-agent-manifest-diff` | `dm_agent.benchmarks.manifest_diff:main` | benchmark 任务集漂移检测 |

根目录 `main.py` 是 `python main.py` 的兼容转发，不会作为顶级 `main` 模块安装。

## 配置优先级

```
CLI 参数  >  config.json  >  硬编码默认
```

API key 是例外：**只从环境变量读**（`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` /
`CLAUDE_API_KEY` / `GEMINI_API_KEY`），不参与上面的链条。MCP 配置独立于当前工作目录的
`mcp_config.json`，见 [MCP 配置](mcp.md)。

## 基础参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--provider` | `deepseek` | 已注册的供应商；扩展可注册新的 |
| `--model` | `deepseek-chat` | 模型标识 |
| `--base-url` | 供应商默认 | 自建网关 / 代理 |
| `--max-steps` | `100` | ReAct 步数上限（`ReactAgent` 作为库使用时默认 200） |
| `--temperature` | `0.7` | 采样温度（`ReactAgent` 库默认 0.0） |
| `--show-steps` | 关 | 实时打印中间步骤 |
| `--interactive` | — | 进入交互式菜单（不给 task 时也会进） |
| `--report PATH` | — | 输出人类可读的 Markdown 运行报告 |

## 基础设施护栏（默认**开**）

这些是「防止 agent 把自己搞死」的护栏，默认启用，只能显式放宽：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--max-observation-chars` | `8000` | 单条工具观察的字符上限，超出截断并附分页提示；`0` 关闭 |
| `--context-token-budget` | `24000` | 估算 token 超预算时提前触发上下文折叠；`0` 只按消息节奏折叠 |
| `--disable-edit-guard` | 守卫开启 | 关闭 read-before-edit 守卫（`edit_file` 前必须读过目标） |
| `--llm-max-retries` | `2` | 四家 provider 统一的瞬时故障重试次数 |

原子文件写入与修改前备份始终开启，没有开关。

## 行为/算法模块（默认**关**）

| 参数 | 附带参数 | 说明 |
| --- | --- | --- |
| `--enable-critic` | — | 完成前加一道 peer-review 门禁 |
| `--enable-reflexion` | `--max-trials 3`、`--reflexion-memory-file` | 失败 trial 反思成 lesson 注入下一轮 |
| `--enable-adaptive-replanning` | `--max-replans -1` | 错误信号映射到重规划策略 |
| `--enable-circuit-breaker` | `--circuit-breaker-threshold 3`、`--circuit-breaker-cooldown 5` | 连续失败的工具临时禁用 |
| `--enable-memory-hygiene` | — | 后续成功让相关失败记忆降权 |
| `--enable-llm-compression` | — | 折叠旧消息时额外生成一条 LLM 摘要记忆 |
| `--enable-repeated-failure-policy-experiment` | 需要 adaptive-replanning 或 evolution | 重复失败策略实验 |
| `--enable-evolution` | — | 隐式打开 adaptive-replan + 重复失败策略 |

Planning 与上下文折叠**默认开启**，但没有暴露成 `dm-agent` 开关；它们只在 bench/eval
里作为 ablation 变体存在（`no_planning` / `no_compression`）。

**Self-consistency 只在 benchmark 侧**（`dm-agent-bench --self-consistency-runs N`），
没有接进 `dm-agent`。

这些开关是过渡写法：它们内部等价于「加载对应的内置扩展」，实现见
[生命周期事件](lifecycle-events.md#内置能力也是事件处理器)。

## 会话、断点与分叉

| 参数 | 说明 |
| --- | --- |
| `--trace PATH` | 写可分享的脱敏会话日志 |
| `--trace-llm-io` | 在 trace 中包含完整 LLM 输入/输出，仅私有调试用 |
| `--checkpoint PATH` | `*.jsonl` 写 append-only 会话日志（可配合 `--resume-at` 与 `fork`）；其他后缀写单文件 JSON 快照 |
| `--resume PATH` | 从上面两种形态中的任意一种恢复；任务参数可省略 |
| `--resume-at ENTRY_ID` | 仅对 JSONL 会话日志有效，定位到某条 entry（支持唯一前缀） |

`--trace` 与 `--checkpoint` 不能指向同一个文件（前者默认脱敏，后者含完整对话）。
`--checkpoint`/`--resume` 与 `--enable-reflexion` 互斥。细节见 [会话与 trace](tracing.md)。

## 扩展开关

| 参数 | 说明 |
| --- | --- |
| `--no-extensions` | 只留内置能力：不扫目录、不查 entry point、不触发项目信任提示 |
| `--extension PATH` | 显式加载单个已审查的 `.py`，仅本次生效，可重复 |

两者互斥。安全模型见 [扩展开发](extensions.md#安全模型)。
