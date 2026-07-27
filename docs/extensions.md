# 扩展系统

DM-Code-Agent 扩展是一个导出 `setup(api)` 的 Python 模块。扩展只能通过
`ExtensionAPI` 注册工具、技能、LLM 供应商和生命周期事件处理器，不会拿到
`ReactAgent` 实例。

```python
from dm_agent.extensions import ExtensionAPI
from dm_agent.tools import Tool


def setup(api: ExtensionAPI) -> None:
    api.register_tool(
        Tool(
            name="hello",
            description="返回一条问候。",
            runner=lambda arguments: "hello from extension",
        )
    )
```

## 安全警告

**扩展是以当前用户权限运行的任意 Python 代码，不是沙箱。** 扩展可以读取或修改
当前用户能访问的文件、启动进程并访问网络。只安装、加载和信任你已经审查过的来源。

尤其不要因为仓库里出现了 `.dm_agent/extensions/` 就直接加载。克隆恶意仓库后运行
`dm-agent` 时，项目扩展在获得明确授权之前不会被导入，模块顶层代码也不会执行。

## 发现来源与优先级

加载顺序从低到高如下，后注册的同名工具、技能或供应商覆盖前者；事件处理器则按该
顺序串联执行：

1. DM-Code-Agent 内置能力。
2. Python 包 entry point：`dm_agent.extensions`。
3. 用户目录：`~/.dm_agent/extensions/*.py`，默认加载。
4. 当前项目：`.dm_agent/extensions/*.py`，必须先通过信任检查。
5. 重复指定的 `--extension PATH`，按命令行出现顺序加载，优先级最高。

第三方包可在 `pyproject.toml` 中声明：

```toml
[project.entry-points."dm_agent.extensions"]
my_extension = "my_package.extension:setup"
```

## 项目信任模型

只有当前项目确实包含 `.dm_agent/extensions/*.py` 时才会询问。可选择：

- 仅本次加载：本进程加载，不写配置。
- 始终信任：把规范化后的项目绝对路径记入用户级信任文件。
- 本次跳过：本进程不加载，下次再次询问。
- 始终拒绝：记录负向决定，后续不再询问也不加载。

信任文件位于 `~/.dm_agent/trusted-projects.json`，不放在仓库内，项目代码无法通过提交
一个配置文件来伪造信任。文件缺失、损坏或读取失败时一律按“未信任”处理；非交互环境
也默认跳过未信任的项目扩展，不会等待输入。

信任按项目规范化绝对路径记录。同一路径重新克隆仓库仍会继承旧决定。要撤销信任或拒绝，
关闭正在运行的 `dm-agent`，删除 `trusted-projects.json` 中对应路径的条目；删除整个文件会
清除全部项目决定。

## CLI 开关

```bash
# 关闭所有非内置扩展；不会扫描目录、查询 entry point 或触发项目信任提示
dm-agent --no-extensions "任务"

# 显式加载单个已审查文件，仅本次生效；可重复指定
dm-agent --extension ./my_extension.py "任务"
```

`--no-extensions` 与 `--extension` 互斥。显式文件视为用户对该文件的一次性授权，不会把
它所在的项目写入信任文件。

## 生命周期处理器

`api.on()` 复用内核事件总线，支持 `before_tool_call`、`after_tool_result` 和
`before_llm_request`。例如阻止危险命令：

```python
from dm_agent.extensions import ExtensionAPI


def setup(api: ExtensionAPI) -> None:
    def confirm(event):
        command = str(event.arguments.get("command", ""))
        if event.tool_name == "run_shell" and "rm -rf" in command:
            return {"block": True, "reason": "扩展拒绝危险命令"}
        return None

    api.on("before_tool_call", confirm)
```

处理器严格按加载顺序执行。单个处理器抛异常时事件总线会记录失败并继续运行，因此涉及
人工确认的守卫应自行捕获 `EOFError` 等输入异常，并默认拒绝，而不是依赖异常中断工具。
