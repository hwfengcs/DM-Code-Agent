# 扩展开发

> **可以把这份文档整份给 AI 看，然后描述你的需求，让它帮你写扩展。**
> 它包含了写一个扩展所需的全部接口、语义与安全约定，不需要读源码。

DM-Code-Agent 的内核是极小的：只有 ReAct 主循环。加工具、加守卫、加供应商、
在执行链上插手——全部通过扩展完成，**不需要改 `dm_agent/` 里的任何一行**。

一个扩展就是一个导出 `setup(api)` 的 Python 模块。它只能通过 `ExtensionAPI` 注册东西，
**拿不到 `ReactAgent` 实例**，所以扩展无法绕过内核护栏。

```python
from dm_agent.extensions import ExtensionAPI
from dm_agent.tools.base import Tool


def setup(api: ExtensionAPI) -> None:
    api.register_tool(
        Tool(name="hello", description="返回一条问候。", runner=lambda arguments: "hello")
    )
```

放到 `~/.dm_agent/extensions/hello.py` 就生效，或者 `dm-agent --extension ./hello.py "任务"`。

---

## 安全模型

**扩展是以当前用户权限运行的任意 Python 代码，不是沙箱。** 扩展可以读写当前用户能访问的
任何文件、启动进程、访问网络。只加载你审查过的来源。

三条具体的防线：

**1. 项目本地扩展需要显式信任。** 克隆一个恶意仓库后运行 `dm-agent`，仓库里的
`.dm_agent/extensions/*.py` 在获得明确授权之前**不会被 import**，模块顶层代码也不会执行。

只有当前项目确实存在这类文件时才会询问，四个选项：

| 选择 | 行为 |
| --- | --- |
| 仅本次加载 | 本进程加载，不写配置 |
| 始终信任 | 把规范化后的项目绝对路径记入用户级信任文件 |
| 本次跳过 | 本进程不加载，下次再问 |
| 始终拒绝 | 记录负向决定，后续不再询问也不加载 |

**2. 信任文件在仓库之外。** `~/.dm_agent/trusted-projects.json`。项目代码无法通过提交一个
配置文件来伪造信任。文件缺失、损坏或读取失败一律按「未信任」处理；**非交互环境（CI、
管道）默认跳过未信任的项目扩展**，不会挂住等输入。

信任按项目的规范化绝对路径记录，所以同一路径重新克隆仓库会继承旧决定。撤销方式：关闭正在
运行的 `dm-agent`，删掉 `trusted-projects.json` 里对应路径的条目（删整个文件清除全部决定）。

**3. 两个 CLI 开关。**

```bash
# 只留内置能力：不扫目录、不查 entry point、不触发项目信任提示
dm-agent --no-extensions "任务"

# 显式加载单个已审查文件，仅本次生效，可重复指定
dm-agent --extension ./my_extension.py "任务"
```

两者互斥。`--extension` 是对**那个文件**的一次性授权，不会把它所在的项目写进信任文件。

**加载失败不会中断启动**：目录扫描与 entry point 的失败被记进诊断信息后继续；
只有 `--extension` 显式指定的文件加载失败才会抛 `ExtensionDiscoveryError` 中止。

---

## 发现来源与优先级

优先级**从低到高**。同名工具、技能、供应商后注册的覆盖前者；事件处理器按同一顺序**串联**执行：

| # | 来源 | 默认 |
| --- | --- | --- |
| 1 | 内置能力 | 总是加载 |
| 2 | Python 包 entry point：`dm_agent.extensions` | 自动 |
| 3 | 用户目录 `~/.dm_agent/extensions/*.py` | 自动 |
| 4 | 项目目录 `.dm_agent/extensions/*.py` | **需要信任** |
| 5 | `--extension PATH`（可重复，按命令行顺序） | 显式 |

目录扫描只取该目录下的 `*.py`（不递归），按文件名不区分大小写排序，顺序稳定。

第三方包这样发布扩展：

```toml
[project.entry-points."dm_agent.extensions"]
my_extension = "my_package.extension:setup"
```

`setup` 的执行是**事务式**的：先注册到一个暂存 registry，成功才合并进主 registry。
一个 `setup` 中途抛异常不会留下半套注册结果。

---

## `ExtensionAPI` 接口参考

`api` 只有四个方法，没有别的。

### `register_tool(tool: Tool) -> None`

注册或覆盖同名工具。`Tool` 是 `dm_agent.tools.base` 里的 dataclass：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `str` | 工具名，必须非空；模型用它作为 `action` |
| `description` | `str` | 会进 system prompt。**把参数格式写清楚**，模型只看这一段 |
| `runner` | `Callable[[dict], Any]` | 接收 `action_input` 字典，返回值会被 `str()` 后作为 observation |

名字为空会抛 `ValueError`。覆盖内置工具时，工具在提示词里的**位置不变**（只换实现），
所以不会打乱默认工具顺序。

runner 抛异常不会炸掉 run：内核捕获成 `Tool execution failed: <异常>` 作为观察，
并计入 `metadata["tool_error_count"]`。

### `register_skill(skill: BaseSkill) -> None`

注册或覆盖同名技能。技能要实现 `get_metadata()` / `get_system_prompt_section()` /
`get_tools()`，见 [Skill 系统](skills.md)。`get_metadata().name` 为空会抛 `ValueError`。

### `register_provider(name: str, factory: Callable) -> None`

注册或覆盖 LLM 供应商，**名字不区分大小写**。工厂由内核用**关键字参数**调用：

```python
factory(api_key=..., model=..., base_url=..., timeout=..., **kwargs)
```

返回的对象只需要一个方法：`respond(messages: list[dict[str, str]], **kwargs) -> str`。

`register_provider()` 目前**不携带**默认模型、默认 URL 或密钥环境变量元数据。所以自定义
供应商要么在工厂里处理空值，要么要求用户显式传 `--model` / `--base-url` / `--api-key`。
四家内置供应商继续用各自的默认值和环境变量；自定义供应商是否需要 API key 由工厂自己决定
（这就是接本地 llama.cpp 的路子）。

### `on(event: str, handler: Callable) -> None`

注册生命周期事件处理器。支持的六个事件：

| 事件 | 时机 | 返回值语义 |
| --- | --- | --- |
| `before_tool_call` | 工具执行前 | `{"block": True, "reason": "..."}` 拦下；也可就地改 `event.arguments` |
| `after_tool_result` | 观察截断之后 | 返回新的 observation 字符串；`None` 表示不改 |
| `before_llm_request` | 发请求前 | 返回新的 `list[dict[str, str]]`；`None` 表示不改 |
| `before_finish` | 判定完成前 | `{"block": True, "reason": "..."}` 否决完成 |
| `on_run_start` | metadata 建好、技能激活前 | 返回字符串追加到 system prompt 末尾；可就地改 `metadata` |
| `on_run_end` | 一轮结束后 | `{"retry": True}` 让内核丢弃本轮并重跑 |

事件名不在这六个之内会抛 `ValueError`；handler 不可调用会抛 `TypeError`。

**每个事件的完整字段、次序细节与异常隔离行为见 [生命周期事件](lifecycle-events.md)。**
写守卫前必读那一篇的三条：

1. `before_tool_call` **改完参数不会重新做校验**，处理器要自己保证参数可用。
2. `after_tool_result` 是**中间件语义**，后一个处理器看到前一个改过的结果。
3. **处理器抛异常等价于「放行」**——事件总线会跳过它并继续。所以涉及人工确认的守卫
   必须自己捕获 `EOFError` 等异常并默认拒绝，不能依赖异常去中断工具。

异常会在会话日志里留一条 `hook_error` 条目，能定位到是哪个扩展的哪个处理器。

---

## 三个完整示例

下面三份代码都是**实际跑通过**的（验证方式：`discover_extensions` 加载 → 装进
`ReactAgent` → 用脚本化模型响应跑一轮，无需 API key）。

### 示例 1：自定义工具

```python
"""统计文件词数的自定义工具。"""

from pathlib import Path

from dm_agent.extensions import ExtensionAPI
from dm_agent.tools.base import Tool


def count_words(arguments: dict) -> str:
    path = Path(str(arguments.get("path", "")))
    if not path.is_file():
        return f"文件 {path} 不存在。"
    words = len(path.read_text(encoding="utf-8").split())
    return f"{path}: {words} words"


def setup(api: ExtensionAPI) -> None:
    api.register_tool(
        Tool(
            name="count_words",
            description="统计一个文本文件的词数。参数：{\"path\": \"<文件路径>\"}",
            runner=count_words,
        )
    )
```

```bash
dm-agent --extension ./word_count_tool.py "统计 README.md 的词数" --show-steps
```

实跑结果：工具进了工具表（内置 17 个 → 18 个），模型调用后得到
`sample.txt: 4 words`，run status `success`。

### 示例 2：危险命令守卫

```python
"""拦截危险 shell 命令的守卫扩展。"""

from dm_agent.extensions import ExtensionAPI

DANGEROUS_MARKERS = ("rm -rf", "del /f /s /q", "rd /s /q", "mkfs", "dd if=")


def setup(api: ExtensionAPI) -> None:
    def guard(event):
        if event.tool_name != "run_shell":
            return None
        command = str(event.arguments.get("command", "")).casefold()
        if any(marker in command for marker in DANGEROUS_MARKERS):
            return {"block": True, "reason": f"安全策略拒绝执行：{command[:80]}"}
        return None

    api.on("before_tool_call", guard)
```

实跑结果：`rm -rf /` 的那一步 observation 变成 `安全策略拒绝执行：rm -rf /`，
**runner 完全没有被调用**；紧接着的 `echo hello` 正常放行执行。

要做交互式确认就在 `guard` 里 `input()`——但记住上面第 3 条，一定要兜底：

```python
def guard(event):
    if event.tool_name != "run_shell":
        return None
    try:
        answer = input(f"执行 {event.arguments.get('command')!r}？[y/N] ")
    except (EOFError, KeyboardInterrupt):
        return {"block": True, "reason": "无法确认，默认拒绝"}
    if not answer.strip().lower().startswith("y"):
        return {"block": True, "reason": "用户拒绝"}
    return None
```

### 示例 3：自定义 provider

```python
"""注册一个自定义 LLM 供应商（这里用一个不联网的假客户端演示接线）。"""

from dm_agent.extensions import ExtensionAPI


class EchoClient:
    """最小可用客户端：只需要一个 respond(messages, **kwargs) -> str。"""

    def __init__(self, *, model: str, base_url: str | None = None) -> None:
        self.model = model or "echo-1"
        self.base_url = base_url

    def respond(self, messages, **kwargs) -> str:
        last = messages[-1]["content"] if messages else ""
        return (
            '{"thought": "echo", "action": "finish", '
            f'"action_input": {{"answer": "{len(last)} chars"}}}}'
        )


def setup(api: ExtensionAPI) -> None:
    def create_client(*, api_key=None, model="", base_url=None, timeout=None, **kwargs):
        return EchoClient(model=model, base_url=base_url)

    api.register_provider("echo", create_client)
```

```bash
dm-agent --extension ./echo_provider.py --provider echo "随便说点什么"
```

实跑结果：可用 provider 从 `['deepseek', 'openai', 'claude', 'gemini']` 变成多一个 `echo`，
`create_llm_client(provider="echo")` 返回 `EchoClient`，run status `success`。

把 `EchoClient` 换成真的 HTTP 客户端（公司内网网关、本地 llama.cpp、自建代理）就是
生产用法。

---

## 内置能力也是扩展

`--enable-critic` / `--enable-circuit-breaker` / `--enable-reflexion` 以及内置的
read-before-edit 守卫，实现方式和你的扩展**完全一样**——都是挂在事件总线上的处理器：

| 能力 | 开关 | 挂载事件 | 实现 |
| --- | --- | --- | --- |
| read-before-edit 守卫 | 默认开，`--disable-edit-guard` 关 | `before_tool_call` + `after_tool_result` | `dm_agent/core/guards.py` |
| Critic 完成门禁 | `--enable-critic` | `before_finish` | `dm_agent/extensions/capabilities/critic_gate.py` |
| 工具熔断 | `--enable-circuit-breaker` | `before_tool_call` + `after_tool_result` | `dm_agent/extensions/capabilities/circuit_breaker_gate.py` |
| Reflexion 多 trial | `--enable-reflexion` | `on_run_start` + `on_run_end` | `dm_agent/extensions/capabilities/reflexion_loop.py` |

想看真实用法就读这几个文件——它们是最好的参考实现。

需要比 `setup(api)` 更多控制（例如要一个按 phase 包装的 LLM 客户端）时，可以实现
`dm_agent.core.capabilities.AgentCapability` 协议，直接传给 Agent：

```python
agent = ReactAgent(client, tools, capabilities=[MyCapability()])
```

`CapabilityContext` 只暴露 `event_bus`、`client_for`（按 phase 取 LLM 客户端）和
`trace_writer`，同样不会把 `ReactAgent` 交出去。

执行顺序：**外部扩展 → 可选能力 → 内核内置守卫**。
