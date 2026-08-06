# 能力清单

DM-Code-Agent 面向真实的代码维护任务：在本地工作区里读写文件、搜索、跑测试、跑 lint、
做代码分析和调 MCP 工具，并把每一步都写进可审计的会话日志。

## 适合做什么

- 修复小到中等规模的 bug，并运行测试验证。
- 补充回归测试，避免只修 visible case。
- 分析项目结构、函数签名、依赖和代码指标。
- 执行小型重构或文档一致性修复。
- 生成会话日志与 benchmark 报告，用于审计 agent 的行为质量。

## 能力总表

| 能力 | 默认 | 说明 |
| --- | --- | --- |
| ReAct 循环 | 开 | 模型输出 `thought/action/action_input`，Agent 执行工具并把 observation 写回上下文 |
| Task Planner | 开 | 执行前生成 3–8 步计划，失败后可触发 replan；重规划保留已完成进度并有预算护栏 |
| 上下文折叠 | 开 | Mem0 风格本地原子记忆，**非破坏式**——原始条目一条不删，见 [会话与 trace](tracing.md#non-destructive-compaction) |
| 观察截断 + 分页提示 | 开 | 单条观察超 `--max-observation-chars` 时截断 |
| token 预算触发折叠 | 开 | 估算超 `--context-token-budget` 时提前折叠 |
| 解析失败上下文隔离 | 开 | malformed 原文保留在审计日志，后续模型上下文只携带显式记录的短占位 |
| read-before-edit 守卫 | 开 | 首次 `edit_file` 前必须读过目标；内容锚定编辑可连续执行，行号编辑写后需重读；identity no-op 不写盘、不推进计划 |
| 统一 LLM 重试 | 开 | 四家 provider 共用一套瞬时故障重试 |
| 原子写 + 修改前备份 | 开 | 无开关；备份落在系统临时目录的 per-run 目录，不污染工作区 |
| checkpoint / resume / fork | 按需 | run 级断点续跑，可从任意 entry 分叉 |
| 工具系统 | 开 | 文件读写、搜索、Python/Shell 执行、测试、lint、AST、代码指标 |
| 代码索引 | 开 | 扫描 Python 仓库生成符号索引、符号搜索和本地依赖图 |
| 会话日志 / replay / diff / fork | 按需 | JSONL append-only 条目树，见 [会话与 trace](tracing.md) |
| 多 LLM | 开 | DeepSeek / OpenAI / Claude / Gemini + 自定义 `base_url`；供应商可由扩展注册 |
| MCP 集成 | 按需 | Playwright、Context7、Filesystem、SQLite 等，见 [MCP 配置](mcp.md) |
| Skill 系统 | 开 | 按任务关键词激活领域 prompt 与专用工具，见 [Skill 系统](skills.md) |
| 扩展系统 | 开 | 工具/技能/供应商/钩子都可由外部扩展注册，见 [扩展开发](extensions.md) |
| 生命周期钩子 | 开 | 六个可拦截的事件点，见 [生命周期事件](lifecycle-events.md) |
| Adaptive Replanning | **关** | `--enable-adaptive-replanning`；扩展的重规划决策策略与预算限制 |
| 确定性 eval | — | 无 API key 的行为回归，覆盖 JSON 修复、工具恢复、replan 等 |
| Maintenance benchmark | — | hidden-test benchmark，记录改动文件约束与 agent 指标 |

开关的完整口径见 [CLI 参考](cli.md)。

## 开关分两类

这是本项目一条明确的设计约定：

- **基础设施护栏默认开**。观察截断、token 预算、解析失败上下文隔离、read-before-edit
  守卫、LLM 重试、原子写+备份——它们防止 agent 因为上下文爆掉、瞬时网络故障或盲改
  文件而失败，开着不会改变任务语义。
- **行为/算法类默认关**。目前只剩 Adaptive Replanning——它会改变 agent 的决策路径，
  属于需要实验验证的假设，所以必须显式打开。

> 曾经还有 Reflexion / Critic / Self-Consistency / 工具熔断 / 记忆卫生 / LLM 摘要，
> 它们在 v2.1 被移除：毕业标准依赖真实评测数据，而真实评测冻结后这些假设
> 永远无法被证伪。理由与取回方式见 [devlog 33](research-log/33-scope-reduction.md)。

## 上下文记忆

长对话会用本地确定性策略折叠（**不调用 LLM**）：旧消息被提取成 episodic / semantic /
procedural 原子记忆，按当前任务检索成一段 `<agent_memory>`，同时保留最近轮次原文。

折叠是非破坏式的：会话日志里追加一条 `compaction` 条目记下折叠范围与摘要，
**原始消息条目一条不删**。所以事后可以在同一份日志上开关折叠重算上下文，
精确量化折叠掉了什么——这是 `no_compression` ablation 可信的前提。

实现在 `dm_agent/memory/context_compressor.py`，编排在 `dm_agent/core/context_window.py`。

解析失败上下文隔离不是 compaction，也不删除消息：原始 assistant `message` 仍按 trace /
checkpoint 的保真级别保存，`parse_error.context_replacement` 只记录派生上下文。所有已经穷尽
容错解析的失败响应，无论长短，后续请求都使用占位；旧日志没有该字段时保持历史行为。
