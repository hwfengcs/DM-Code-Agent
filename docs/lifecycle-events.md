# 生命周期事件总线

`dm_agent.core.events` 提供同步、可拦截的中间件事件总线。它不是广播通知：同一事件的
处理器严格按注册顺序执行，后一个处理器会看到前一个处理器留下的修改。

```python
from dm_agent.core import EventBus

bus = EventBus()
bus.on("before_tool_call", handler, name="my_extension.handler")
agent = ReactAgent(client, tools, event_bus=bus)
```

也可以先创建 Agent，再通过 `agent.event_bus.on(...)` 注册处理器。注册时建议显式传入
稳定的 `name`；未传时会使用处理器的 `module + qualname`。

## 核心事件

### `before_tool_call`

处理器收到 `BeforeToolCallEvent`，其中包含 `tool_name`、`arguments`、`step_number`、
`run_id` 和本次 run 的 `metadata`。

- 返回 `{"block": True, "reason": "..."}` 会停止后续前置处理器并跳过工具执行；
  `reason` 会成为该步骤的 observation。
- 可以直接修改 `event.arguments`。
- **修改参数后不会重新做参数校验。** 工具会直接收到处理器留下的参数。这是刻意采用的
  约定，便于扩展实现参数重写、沙箱路径映射等能力；处理器必须自行保证参数可用。

### `after_tool_result`

处理器收到 `AfterToolResultEvent`，可返回新的 observation。返回 `None` 表示不改写。
每次有效改写都会写回 `event.observation`，所以下一个处理器看到的是上一处理器的结果。
最终结果直接进入 step、历史、trace 和恢复判断。

Agent 的 observation 长度限制（`--max-observation-chars`）是内核护栏，**先于**本事件
执行：处理器拿到的已经是截断后的文本，也就是最终会写进对话历史的那一份。

事件还包含 `tool_succeeded`：它表示 runner 是否正常返回，不代表返回文本一定是业务成功。

### `before_llm_request`

处理器收到 `BeforeLLMRequestEvent`，可返回新的 `list[dict[str, str]]`；返回 `None` 表示
不改写。事件包含 `step_number`、`run_id` 和 `phase`。当前内置 phase 包括：

- `agent`
- `planner`
- `compression`

消息处理发生在一次逻辑 `respond()` 调用前，不会因 provider 内部重试重复触发。主循环的
`llm_call` trace 会记录实际发送的改写后消息统计；完整消息仍只在 `capture_llm_io` 开启时记录。

### `before_finish`

处理器收到 `BeforeFinishEvent`，其中包含 `task`、`action`（`finish` 或 `task_complete`）、
`completion_text`、已执行的 `steps`、`step_number`、`run_id` 和本次 run 的 `metadata`。

- 返回 `None` 表示放行。
- 返回 `{"block": True, "reason": "..."}` 会否决这次完成：`reason` 成为该步骤的
  observation，写回对话历史并参与失败判定，Agent 继续下一步。第一个否决生效，后续处理器不再执行。

注意异常处理：事件总线的异常隔离会跳过抛异常的处理器，那等价于**放行**。
对「审查失败即否决」语义的守卫来说这是反的，所以这类处理器必须自己捕获异常
并转成显式否决，不能依赖总线兜底。

被否决时内核记的失败标识是 `critic_rejected`——这是历史字段名（当年只有内置
Critic 用这条路），会话日志与 planner 的重规划策略都按它对齐，不随内置 Critic
的移除而改名。

### `on_run_start`

处理器收到 `RunStartEvent`，包含 `task`、`attempt`（第几次尝试，从 1 开始）、`run_id`、
`prompt_suffix` 和本次 run 的 `metadata`。触发时机是 `metadata` 骨架建好之后、trace
`start_run` 与技能激活之前，所以处理器可以：

- 就地改写 `metadata`（例如声明「本能力已启用」，让报告和 trace 如实反映）；
- 返回一段字符串作为追加到 system prompt 末尾的内容，返回 `None` 表示不追加。
  多个处理器串联，后一个看到前一个的结果。

### `on_run_end`

处理器收到 `RunEndEvent`，包含 `task`、`attempt`、`run_id`、完整的 `result` 和它的
`metadata`。可在这里做计时、成本统计，或改写 `result["metadata"]`。

返回 `{"retry": True}` 会让内核**丢弃本次尝试并重跑一轮**：对话历史恢复到 `run()`
调用前的快照，`attempt` 加一，下一轮的 `on_run_start` 可以借 `prompt_suffix` 把上一轮
的经验带进去。第一个要求重试的处理器生效。

> `--checkpoint` / `--resume` 与 `on_run_end` 重试互斥：断点续跑记录的是单轮的线性
> 状态，重跑会让它失去意义，因此同时使用会直接抛 `ValueError`。

## 异常隔离与 trace

单个处理器抛异常或返回非法类型时，事件总线会跳过该结果并继续执行后续处理器，Agent run
不会因此中断。若启用了 trace，会新增一条 `hook_error` 事件，至少包含：

- `hook`
- `handler`
- `handler_position`
- `step_number`
- `run_id`
- `error_type`
- `message`

工具事件还会记录 `tool_name`，LLM 事件会记录 `phase`。默认不记录完整 arguments、messages
或 traceback，以免扩大 trace 的敏感数据面。

## 内置能力也是事件处理器

内置 read-before-edit 守卫是事件处理器：它在 `before_tool_call` 拦截不安全的
`edit_file`，并在 `after_tool_result` 中维护成功读写的文件台账。`--disable-edit-guard`
只关闭拦截，保持既有 CLI 语义不变。

可选能力同样如此：实现 `dm_agent.core.capabilities.AgentCapability` 协议，
在 Agent 构造末尾通过 `install(context)` 把自己挂到事件总线上，经
`ReactAgent(capabilities=[...])` 传入。

> v2.1 移除了全部内置可选能力（Critic / 工具熔断 / Reflexion）与
> `dm_agent/extensions/capabilities/` 子包。协议本身保留——它是公开扩展点，
> 要复活任何一个能力，按 [扩展开发](extensions.md) 写成外部扩展即可。

`CapabilityContext` 只暴露 `event_bus`、`client_for`（按 phase 包装的 LLM 客户端工厂）
和 `trace_writer`，不会把 `ReactAgent` 交给能力实现。也可以在构造 Agent 时直接传入
`capabilities=[...]` 安装自定义能力：

```python
agent = ReactAgent(client, tools, capabilities=[MyCapability()])
```

注册顺序即执行顺序：外部扩展（事件总线创建时注册）→ 可选能力 → 内核内置守卫。
