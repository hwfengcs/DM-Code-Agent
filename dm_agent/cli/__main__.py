"""让 ``python -m dm_agent.cli`` 可用。

包内一直没有 ``__main__``，所以 ``python -m dm_agent.cli --help`` 会静默什么都不做
（CLAUDE.md 把它记成已知坑）。Web 控制台 spawn 子进程时需要一个不依赖 PATH 上是否
装了 console script 的稳定入口，顺手把这个坑补掉。
"""

from __future__ import annotations

import signal
import sys
from types import FrameType

from . import main


def _terminate(_signum: int, _frame: FrameType | None) -> None:
    # Let execution/MCP finally blocks release their own process groups on SIGTERM.
    raise KeyboardInterrupt


if __name__ == "__main__":
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _terminate)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
