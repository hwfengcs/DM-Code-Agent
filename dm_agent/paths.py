"""用户级数据目录、配置文件与 ``.env`` 的落点解析。

**这个模块的存在理由是「包被装到 site-packages 之后」。** 开发时用的是 editable
安装，包目录就在仓库里，「相对包位置算路径」和「相对工作目录算路径」恰好重合，
所以下面这两类 bug 在开发环境永远不会暴露：

* 配置写在 ``Path(__file__).parents[2]``——全局安装后那是 ``site-packages/``。
  轻则污染别人的 site-packages，重则系统 Python 下直接权限失败，
  而且所有项目共享同一份配置、用户根本找不到文件在哪。
* 无参数 ``load_dotenv()``——它内部的 ``find_dotenv(usecwd=False)`` 是从**调用方
  模块所在目录**向上找的，全局安装后从 ``site-packages/dm_agent/cli/`` 往上翻，
  永远够不到用户的工作目录，用户放在自己项目里的 ``.env`` 会静默失效。

**为什么住在 ``dm_agent/`` 顶层而不是 ``cli/``**：``server`` 层也要用它加载 ``.env``，
而 server **不得 import cli**（``tests/test_server_layering.py`` 用 AST 断言这一条）。
本模块只依赖标准库与 ``dotenv``，不 import 任何 ``dm_agent`` 子包，因此任何层都能用它，
也不会触发 ``TID251`` 的分层检查。

查找顺序（读）：

    ./config.json              项目级，优先
    ~/.dm_agent/config.json    用户级

写回**读到的那一个**；两者都不存在时落用户级。这样「改了设置就生效」，同时让老用户
在仓库根跑时读写都还是仓库根的 ``config.json``——行为与拆分前逐字节一致，不需要迁移。

``.env`` 同样是项目级优先、用户级兜底，且都用 dotenv 的默认 ``override=False``，
所以**显式导出的环境变量始终压过文件**（``DEEPSEEK_API_KEY=xxx dm-agent ...`` 仍然管用）。
``tests/conftest.py`` 的 ``block_real_api_keys`` 靠的正是这条语义。
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

__all__ = [
    "CONFIG_FILE_NAME",
    "DM_AGENT_DIR_NAME",
    "ENV_FILE_NAME",
    "atomic_write_json",
    "load_env_files",
    "project_config_path",
    "resolve_config_read_path",
    "resolve_config_write_path",
    "restrict_permissions",
    "user_config_path",
    "user_data_dir",
    "user_env_path",
]

# 与扩展目录、信任文件同一个家：~/.dm_agent/{extensions/,trusted-projects.json,config.json,.env}
DM_AGENT_DIR_NAME = ".dm_agent"
CONFIG_FILE_NAME = "config.json"
ENV_FILE_NAME = ".env"


def user_data_dir(home_dir: str | Path | None = None) -> Path:
    """用户级数据目录 ``~/.dm_agent``。

    ``home_dir`` 只为测试注入；生产路径一律走 ``Path.home()``。
    """
    home = Path.home() if home_dir is None else Path(home_dir)
    return home / DM_AGENT_DIR_NAME


def user_config_path(home_dir: str | Path | None = None) -> Path:
    """用户级配置文件 ``~/.dm_agent/config.json``。"""
    return user_data_dir(home_dir) / CONFIG_FILE_NAME


def user_env_path(home_dir: str | Path | None = None) -> Path:
    """用户级 ``.env``：装一次 key，在任何目录下都能用。"""
    return user_data_dir(home_dir) / ENV_FILE_NAME


def project_config_path(cwd: str | Path | None = None) -> Path:
    """项目级配置文件 ``./config.json``（相对**当前工作目录**，不是包位置）。"""
    base = Path.cwd() if cwd is None else Path(cwd)
    return base / CONFIG_FILE_NAME


def resolve_config_read_path(
    *,
    cwd: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> Path | None:
    """返回实际要读的配置文件；都不存在时返回 ``None``（调用方用默认值）。"""
    project = project_config_path(cwd)
    if project.is_file():
        return project
    user = user_config_path(home_dir)
    return user if user.is_file() else None


def resolve_config_write_path(
    *,
    cwd: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> Path:
    """返回要写入的配置文件：读到哪个就写哪个，都没有则写用户级。

    「写回来源」是为了让交互式设置向导改完立刻生效——如果读的是项目级却写到用户级，
    用户会看到「我明明改了却没变」。
    """
    existing = resolve_config_read_path(cwd=cwd, home_dir=home_dir)
    return existing if existing is not None else user_config_path(home_dir)


def load_env_files(
    *,
    cwd: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> list[Path]:
    """按项目级 → 用户级的顺序加载 ``.env``，返回实际加载了哪些文件。

    两个都用 dotenv 默认的 ``override=False``，于是优先级为
    **已有环境变量 > ./.env > ~/.dm_agent/.env**。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv 是核心依赖，装不上才会走到
        return []

    base = Path.cwd() if cwd is None else Path(cwd)
    loaded: list[Path] = []
    for candidate in (base / ENV_FILE_NAME, user_env_path(home_dir)):
        if candidate.is_file():
            # 显式传路径，绕开 find_dotenv 那套「从调用方模块目录向上找」的逻辑。
            #
            # encoding 用 utf-8-sig 而不是 dotenv 默认的 utf-8：Windows 上生成 .env 的
            # 常见方式全都会写 UTF-8 BOM——PowerShell 的 `Set-Content -Encoding utf8`、
            # `>` 重定向、记事本的「UTF-8」另存。dotenv 不剥 BOM，会把它并进第一个键名
            # （变成 `﻿DEEPSEEK_API_KEY`），于是 key 明明配了却读不到，报错还是
            # 「缺少 API key」，几乎无法自己诊断。utf-8-sig 在没有 BOM 时与 utf-8 等价。
            load_dotenv(dotenv_path=candidate, encoding="utf-8-sig")
            loaded.append(candidate)
    return loaded


def restrict_permissions(path: Path, *, directory: bool) -> None:
    """POSIX 上把配置收敛到仅属主可读写；Windows 上是空操作。"""
    if os.name == "nt":
        return
    with suppress(OSError):
        path.chmod(0o700 if directory else 0o600)


def atomic_write_json(path: Path, payload: Any) -> None:
    """原子写入 JSON：同目录临时文件 → fsync → ``os.replace``。

    与 ``extensions/trust.py`` 里的私有实现是同一套逻辑，暂未合并——那属于重构，
    不该夹带进这次的修复（见 ``docs/research-log/32-user-level-config-and-env.md``）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    restrict_permissions(path.parent, directory=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        restrict_permissions(temporary_path, directory=False)
        os.replace(temporary_path, path)
        restrict_permissions(path, directory=False)
    finally:
        if temporary_path is not None and temporary_path.exists():
            with suppress(OSError):
                temporary_path.unlink()
