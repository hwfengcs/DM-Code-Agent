"""分层契约：server 层的三条不变式，由 AST 静态断言。

ruff 的 TID251 拦不住这些——``dm_agent/server/**`` 为了能写 ``from .settings import ...``
必须整体豁免 TID251（同 ``dm_agent/cli/**``），豁免之后 server → cli 也就不再报错了。
所以这三条改由本文件显式钉住：

1. server **不得 import cli**（它 spawn CLI 子进程，不把 CLI 当库用）。
2. 没有任何下层反向 import server。
3. ``settings.py`` 不碰 fastapi——缺 ``[web]`` extra 时 ``dm-agent-web``
   要能正常打印依赖缺失提示，而不是抛 ImportError。

本文件**不 import fastapi**，因此在只装核心包的环境里也照样运行。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "dm_agent" / "server"

# 不允许 server 依赖的模块前缀。
FORBIDDEN_IN_SERVER = ("dm_agent.cli", "main")

# 只允许这几个下层被 server 依赖之外的层反向依赖 server 的白名单——空的，
# 也就是任何 dm_agent/ 下的非 server 代码都不许 import server。
LOWER_LAYERS = tuple(
    path
    for path in (REPO_ROOT / "dm_agent").rglob("*.py")
    if "server" not in path.relative_to(REPO_ROOT / "dm_agent").parts
)


def _imported_modules(path: Path) -> set[str]:
    """收集一个文件里全部被导入的模块名（相对导入按其绝对形式展开）。

    用 ``utf-8-sig`` 读：仓库里有文件带 UTF-8 BOM，``ast.parse`` 见到 U+FEFF 会
    直接抛 SyntaxError。
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    package_parts = path.relative_to(REPO_ROOT).with_suffix("").parts[:-1]
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # from .x import y → 用所在包补全成绝对模块名
                base = package_parts[: len(package_parts) - node.level + 1]
                modules.add(".".join((*base, node.module)) if node.module else ".".join(base))
            elif node.module:
                modules.add(node.module)
    return modules


def _is_under(module: str, prefix: str) -> bool:
    """按模块边界判断归属。

    不能用裸 ``startswith``：``dm_agent.clients`` 会被 ``dm_agent.cli`` 前缀命中，
    那是个假阳性（clients 层是 server 完全可以依赖的下层）。
    """
    return module == prefix or module.startswith(f"{prefix}.")


def _server_files() -> list[Path]:
    files = sorted(SERVER_DIR.rglob("*.py"))
    assert files, "dm_agent/server 下应该有 Python 文件"
    return files


def test_server_never_imports_cli() -> None:
    offenders: list[str] = []
    for path in _server_files():
        for module in _imported_modules(path):
            if any(_is_under(module, prefix) for prefix in FORBIDDEN_IN_SERVER):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()} -> {module}")
    assert (
        not offenders
    ), "server 层不得 import cli 或顶级 main；需要跑 agent 时请 spawn CLI 子进程。\n" + "\n".join(
        offenders
    )


def test_no_lower_layer_imports_server() -> None:
    offenders: list[str] = []
    for path in LOWER_LAYERS:
        for module in _imported_modules(path):
            if _is_under(module, "dm_agent.server"):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()} -> {module}")
    assert not offenders, "server 是最外层装配者，任何下层都不得反向依赖它。\n" + "\n".join(
        offenders
    )


def test_prefix_matching_is_module_aware() -> None:
    """守住上面两条断言自己的正确性：clients 不能被 cli 前缀误伤。"""
    assert _is_under("dm_agent.cli", "dm_agent.cli")
    assert _is_under("dm_agent.cli.runner", "dm_agent.cli")
    assert not _is_under("dm_agent.clients", "dm_agent.cli")
    assert not _is_under("dm_agent.clients.base_client", "dm_agent.cli")


def test_settings_module_is_importable_without_web_extra() -> None:
    """``settings.py`` 必须零 web 依赖，缺 extra 时才能给出友好提示。"""
    roots = {module.split(".")[0] for module in _imported_modules(SERVER_DIR / "settings.py")}
    assert not roots & {"fastapi", "starlette", "uvicorn", "pydantic"}


def test_server_cli_defers_web_imports() -> None:
    """``cli.py`` 顶层不许 import fastapi/uvicorn，否则缺依赖时拿不到提示。"""
    tree = ast.parse((SERVER_DIR / "cli.py").read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            top_level.add(node.module.split(".")[0])
    assert not top_level & {"fastapi", "starlette", "uvicorn"}
