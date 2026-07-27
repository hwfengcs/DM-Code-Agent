"""兼容入口：真正的 CLI 实现在 dm_agent/cli/，本文件只做转发。"""

from dm_agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
