# 架构

**这份文字版是架构的权威来源。** `docs/architecture.drawio` 与两张 png 保留作为附件，
但二进制图 AI 读不了、人也没法 diff，改了架构不一定会有人更新图。两者冲突时以本文为准。

## 一句话

内核只有 ReAct 主循环；每一步的具体环节住在同层模块里，可选能力挂在生命周期钩子上，
运行历史是一棵 append-only 的会话条目树。

## 分层

依赖必须**单向向下**。这条契约由 ruff 的 `TID251` 在 CI 里强制，配置和理由写在
`pyproject.toml` 的 `[tool.ruff.lint.flake8-tidy-imports.banned-api]`。

```
clients      不依赖任何其他 dm_agent 子包
   ↑
tools        只依赖 clients
   ↑
tracing      只依赖 tools / memory（记录汇，不回头依赖 core）
   ↑
core         依赖 clients / tools / memory / prompts / tracing，禁止依赖 cli
   ↑
extensions   依赖 core（把内置能力装到事件总线上）
   ↑
cli          最外层组装者，可以依赖任何层
```

`cli` 是**参考实现，不是被复用的库**。想自己造 agent 就直接用 `dm_agent.core.ReactAgent`，
不必接受这套 CLI 与 UI。

| 包 | 职责 |
| --- | --- |
| `dm_agent/clients/` | 四家 LLM 适配 + 注册制工厂 + 统一重试 |
| `dm_agent/tools/` | 文件、执行、测试、lint、AST、代码索引工具 |
| `dm_agent/prompts/` | system prompt 构造 |
| `dm_agent/memory/` | token 估算 + Mem0 风格原子记忆折叠 |
| `dm_agent/tracing/` | 会话日志写入、读取归一化、分析/diff/fork CLI |
| `dm_agent/core/` | ReAct 主循环 + 每步环节的同层模块 + 事件总线 |
| `dm_agent/extensions/` | 注册表、三来源发现、项目信任、内置能力 |
| `dm_agent/skills/` | 领域技能与选择器 |
| `dm_agent/mcp/` | MCP 配置、客户端、管理器 |
| `dm_agent/benchmarks/` | coding / maintenance / swebench-lite 套件与经济学核算 |
| `dm_agent/evals/` | 确定性与真实模型 eval |
| `dm_agent/cli/` | argparse、Config、UI、报告、运行装配 |

## `core/` 的模块分工

第 6 步把 `agent.py` 从 1616 行拆到 866 行。`ReactAgent` 现在只做三件事：装配协作者、
跑主循环、维护对话历史。

| 模块 | 负责的环节 |
| --- | --- |
| `agent.py` | 装配 + ReAct 主循环 |
| `run_state.py` | `Step`、`RunContext`（run 级共享的 `run_id`/`step_number`/`metadata`/`history_entry_ids`）、metadata 初值 |
| `prompting.py` | 任务提示词构造与技能激活 |
| `context_window.py` | 构造发给 LLM 的消息，按需折叠旧上下文 |
| `response_parser.py` | 容错 JSON 解析与动作名归一化 |
| `tool_invoker.py` | 工具调用链（见下节） |
| `observation.py` | 观察截断与失败判定 |
| `completion.py` | 完成门禁与结果格式化 |
| `replan.py` | 失败签名与重规划 |
| `persistence.py` | checkpoint 编解码、写前备份、`--resume` 加载 |
| `events.py` | 事件总线、事件对象、按 phase 包装的 LLM 客户端 |
| `capabilities.py` | `AgentCapability` 协议与 `CapabilityContext` |
| `guards.py` | read-before-edit 守卫（作为钩子处理器实现） |
| `critic.py` / `reflexion.py` / `circuit_breaker.py` / `planner.py` | 各自的算法实现 |

> `RunContext` **必须原地改、不能整体替换**——`LLMRequestClient` 在构造期就绑定了它的
> 取值回调，换新实例会让它继续读旧对象。

## 一次 run 的执行链

```mermaid
flowchart TD
    Start([dm-agent task]) --> Disc[扩展发现<br/>builtin -> entry_points -> 用户目录 -> 项目目录 -> --extension]
    Disc --> Assemble[cli.runner 装配<br/>client / tools / skills / event_bus / ReactAgent]
    Assemble --> RunStart{{on_run_start}}
    RunStart --> Skills[技能激活]
    Skills --> Plan[TaskPlanner 生成 3-8 步计划]
    Plan --> Loop[ReAct 循环]

    Loop --> CP[落 checkpoint 条目]
    CP --> Build[ContextWindow.build_messages<br/>按需折叠 + 落 compaction 条目]
    Build --> LLMHook{{before_llm_request}}
    LLMHook --> LLM[LLM respond<br/>统一重试]
    LLM --> Parse[response_parser<br/>容错解析 thought/action/action_input]
    Parse --> Branch{action?}

    Branch -->|finish / task_complete| Finish{{before_finish}}
    Finish -->|放行| Done([run_end])
    Finish -->|否决| Replan

    Branch -->|工具| Invoke[ToolInvoker]
    Branch -->|未知工具 / 解析失败| Replan[replan.try_replan]

    Invoke --> Fail{失败观察?}
    Fail -->|是| Replan
    Fail -->|否| Loop
    Replan --> Loop
    Loop -.->|步数耗尽| Done
    Done --> RunEnd{{on_run_end}}
    RunEnd -->|retry| RunStart
    RunEnd -->|结束| Out([结果 + 报告])
```

`{{双花括号}}` 的是钩子点。语义与返回值见 [生命周期事件](lifecycle-events.md)。

## 工具调用链的次序（有意为之）

`core/tool_invoker.py` 的存在理由就是钉住内核护栏与扩展钩子的相对次序：

```
入参校验            非法直接返回 observation，不进钩子、不执行
   ↓
before_tool_call    可就地改 arguments，可返回 {block, reason} 拦下
   ↓                （改完不再重新校验——这是写进文档的约定）
写前备份            只在放行后、真正执行前做；被拦下的调用不备份
   ↓
tool.execute        异常被捕获成 "Tool execution failed: ..."
   ↓
观察截断            先于后置钩子；处理器看到的就是最终写进历史的那份
   ↓
after_tool_result   中间件式串联，后一个看到前一个改过的 observation
```

处理器的执行顺序 = 注册顺序 = **外部扩展 → 可选能力 → 内核内置守卫**。

## 扩展的发现与加载

```mermaid
flowchart LR
    A[create_builtin_registry<br/>内置工具/技能/供应商] --> B{--no-extensions?}
    B -->|是| Z[只用内置]
    B -->|否| C[entry_points<br/>group=dm_agent.extensions]
    C --> D[用户目录<br/>~/.dm_agent/extensions/*.py]
    D --> E{项目有<br/>.dm_agent/extensions/*.py?}
    E -->|无| G
    E -->|有| F[查 ~/.dm_agent/trusted-projects.json]
    F -->|已信任| G[显式 --extension PATH]
    F -->|已拒绝 / 非交互| S[跳过并记 skipped]
    F -->|未决定| P[交互询问：本次 / 始终 / 跳过 / 始终拒绝]
    P --> G
    S --> G
    G --> R[ExtensionRegistry]
    R --> T[get_tools / get_skills<br/>get_provider_factory<br/>create_event_bus]
```

优先级**从低到高**，同名工具/技能/供应商后者覆盖前者；事件处理器则按同一顺序串联。
每个扩展的 `setup(api)` 是**事务式**执行的：`apply_setup` 先注册到一个暂存 registry，
成功才合并，失败不留下半套注册结果。

加载失败不会中断启动——记进 `ExtensionDiscoveryResult.failures` 并继续；只有
`--extension` 显式指定的文件加载失败才抛 `ExtensionDiscoveryError`。

细节与安全模型见 [扩展开发](extensions.md)。

## 会话数据模型

运行历史是一份 append-only 的 JSONL，每条一个条目：

```json
{"id": "a1b2c3d4-0007", "parent_id": "a1b2c3d4-0006",
 "timestamp": "2026-07-28T09:15:22.481923+00:00", "run_id": "a1b2c3d4...",
 "event": "tool_call", "payload": {"step_number": 3, "action": "read_file"}}
```

- `id` = `<run_id 前 8 位>-<四位序号>`，同一个 writer 内单调递增。
- `parent_id` = 同一 writer 写出的上一条；文件首条为 `""`，**fork 出来的会话首条指回
  源会话的分叉点**——这就是把多份 JSONL 串成一棵树的那根指针。
- `event` / `payload` 沿用 1.x 的拼写（没有改成 `type` / `data`），schema 版本 `2.0`。

```mermaid
flowchart LR
    subgraph src["run.jsonl（源会话）"]
        E1[0001 run_start] --> E2[0002 message]
        E2 --> E3[0003 checkpoint]
        E3 --> E4[0004 compaction]
        E4 --> E5[0005 tool_call]
        E5 --> E6[0006 run_end]
    end
    subgraph fork["run.fork-0003.jsonl（分叉）"]
        F1[0001 run_start] --> F2[0002 message]
        F2 --> F3[0003 checkpoint]
        F3 --> F4[fork 条目]
    end
    E3 -. parent_id .-> F4
```

条目类型、两个保真档（`--trace` 脱敏 vs `--checkpoint` 完整）、非破坏式折叠与
`rebuild_context` 的 ablation 用法，见 [会话与 trace](tracing.md)。

## 三条约定

1. **新增能力先问：这个必须住在内核里吗？** 只需要在固定几个点插手的，就该是扩展。
2. **不用「重构」当借口降低验证强度。** 每个重构都要证明 `pytest` + `evals.cli` +
   benchmark manifest 全绿，且 eval 结果与重构前逐字段一致。
3. **原始数据永不删除。** 折叠、截断、摘要只能是「追加一条派生记录 + 构造上下文时跳过原文」。
