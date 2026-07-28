"""用 before_tool_call 拦截危险 shell 命令的最小扩展示例。"""

from dm_agent.core import BeforeToolCallEvent
from dm_agent.extensions import ExtensionAPI

DANGEROUS_MARKERS = (
    "rm -rf",
    "del /f /s /q",
    "rd /s /q",
    "remove-item -recurse -force",
    "format ",
)


def block_dangerous_shell(event: BeforeToolCallEvent) -> dict[str, object] | None:
    if event.tool_name != "run_shell":
        return None
    command = str(event.arguments.get("command", "")).lower()
    if any(marker in command for marker in DANGEROUS_MARKERS):
        return {"block": True, "reason": "安全策略拒绝执行危险 shell 命令"}
    return None


def setup(api: ExtensionAPI) -> None:
    api.on("before_tool_call", block_dangerous_shell)
