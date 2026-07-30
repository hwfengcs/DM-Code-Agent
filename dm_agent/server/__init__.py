"""DM-Code-Agent Web 控制台（``dm-agent-web``）。

与 ``dm_agent.cli`` 同级的最外层装配者。核心包不依赖任何 web 框架——
本子包只有在装了 ``dm-code-agent[web]`` 之后才 import 得动，
所以 ``import dm_agent`` 与全部 CLI 功能不受影响。

设计要点见 ``docs/web.md``；一句话版本：**live run 与历史 trace 是同一份
append-only JSONL 条目流**，所以前端只需要一套渲染器，后端主体只是
``dm_agent.tracing`` 已有纯函数的 HTTP 包装。
"""

from __future__ import annotations

from .settings import ServerSettings

__all__ = ["ServerSettings", "create_app"]


def create_app(settings: ServerSettings) -> object:
    """延迟导入的 ``app.create_app``。

    直接在模块顶层 ``from .app import create_app`` 会让 ``import dm_agent.server``
    在没装 ``[web]`` extra 时就炸掉；``settings`` 是纯 dataclass，应该始终可导入
    （``dm-agent-web`` 的依赖缺失提示就依赖这一点）。
    """
    from .app import create_app as _create_app

    return _create_app(settings)
