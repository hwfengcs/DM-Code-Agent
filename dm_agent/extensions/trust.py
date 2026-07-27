"""项目本地 Python 扩展的持久化信任决策。"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from enum import Enum
from pathlib import Path
from typing import Any


class ProjectTrustDecision(str, Enum):
    """用户面对项目本地扩展时可作出的决定。"""

    LOAD_ONCE = "load_once"
    TRUST = "trust"
    SKIP_ONCE = "skip_once"
    DENY = "deny"


class ProjectTrustStore:
    """将项目路径的正向或负向信任记录保存在用户目录之外的仓库外文件。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, project_root: str | Path) -> bool | None:
        """返回持久化决定；缺失或配置损坏时按未决定处理。"""
        projects = self._load_projects()
        value = projects.get(canonical_project_key(project_root))
        return value if isinstance(value, bool) else None

    def set(self, project_root: str | Path, *, trusted: bool) -> None:
        """原子保存一个项目的信任决定。"""
        projects = self._load_projects()
        projects[canonical_project_key(project_root)] = trusted
        payload = {"version": 1, "projects": projects}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _restrict_permissions(self.path.parent, directory=True)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            _restrict_permissions(temporary_path, directory=False)
            os.replace(temporary_path, self.path)
            _restrict_permissions(self.path, directory=False)
        finally:
            if temporary_path is not None and temporary_path.exists():
                with suppress(OSError):
                    temporary_path.unlink()

    def _load_projects(self) -> dict[str, bool]:
        if not self.path.is_file():
            return {}
        try:
            payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict) or payload.get("version") != 1:
            return {}
        projects = payload.get("projects")
        if not isinstance(projects, dict):
            return {}
        return {str(key): value for key, value in projects.items() if isinstance(value, bool)}


def canonical_project_key(project_root: str | Path) -> str:
    """生成适合跨进程比较的规范化绝对项目路径。"""
    return os.path.normcase(str(Path(project_root).resolve()))


def default_trust_store_path(home_dir: str | Path | None = None) -> Path:
    """返回用户级信任文件路径。"""
    home = Path.home() if home_dir is None else Path(home_dir)
    return home / ".dm_agent" / "trusted-projects.json"


def _restrict_permissions(path: Path, *, directory: bool) -> None:
    if os.name == "nt":
        return
    with suppress(OSError):
        path.chmod(0o700 if directory else 0o600)
