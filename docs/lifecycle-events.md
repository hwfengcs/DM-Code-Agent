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

## 三个核心事件

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
最终结果仍会经过 Agent 的 observation 长度限制，然后进入 step、历史、trace 和恢复判断。

事件还包含 `tool_succeeded`：它表示 runner 是否正常返回，不代表返回文本一定是业务成功。

### `before_llm_request`

处理器收到 `BeforeLLMRequestEvent`，可返回新的 `list[dict[str, str]]`；返回 `None` 表示
不改写。事件包含 `step_number`、`run_id` 和 `phase`。当前内置 phase 包括：

- `agent`
- `planner`
- `critic`
- `reflexion`
- `compression`

消息处理发生在一次逻辑 `respond()` 调用前，不会因 provider 内部重试重复触发。主循环的
`llm_call` trace 会记录实际发送的改写后消息统计；完整消息仍只在 `capture_llm_io` 开启时记录。

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

内置 read-before-edit 守卫也是事件处理器：它在 `before_tool_call` 拦截不安全的
`edit_file`，并在 `after_tool_result` 中维护成功读写的文件台账。`--disable-edit-guard`
只关闭拦截，保持既有 CLI 语义不变。
