"""运行期状态保全：文件备份与 run 级 checkpoint。

本模块集中存放"崩溃/误操作后还能救回来"的机制：

- ``backup_file``：在 agent 修改文件前把原文件拷到系统临时目录的
  per-run 备份区（刻意不放工作区内，避免污染 benchmark 的 changed-files
  判定和 git diff）。恢复目前是手工操作：从备份目录把文件拷回即可。
- ``RunCheckpoint``：每步之后把对话历史、步骤、metadata、计划与本地记忆
  原子落盘（--checkpoint），崩溃后可用 --resume 从最后一步继续。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BACKUP_ROOT_NAME = "dm_agent_backups"

CHECKPOINT_SCHEMA_VERSION = 1


def backup_root() -> Path:
    return Path(tempfile.gettempdir()) / BACKUP_ROOT_NAME


def backup_file(path: str | Path, *, run_id: str, step: int) -> Path | None:
    """把即将被修改的文件拷贝到 per-run 备份目录，失败时静默返回 None。

    备份是尽力而为的安全网，绝不能因为备份失败而中断任务执行。
    """
    source = Path(path)
    try:
        if not source.is_file():
            return None
        target_dir = backup_root() / run_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{step:03d}-{source.name}"
        # 跨卷场景（临时目录与工作区不同盘）用 copy 而非 rename。
        shutil.copy2(source, target)
        return target
    except OSError:
        return None


@dataclass
class RunCheckpoint:
    """一次 run 的可恢复快照。

    ``step_count`` 是已消耗的循环步数；resume 从 ``step_count + 1`` 继续。
    memory/plan 状态随行，恢复后的行为尽量接近"从未中断"。
    """

    task: str
    step_count: int
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    plan: list[dict[str, Any]] = field(default_factory=list)
    compressor_state: dict[str, Any] | None = None
    reflexion_memory: dict[str, Any] | None = None
    agent_config: dict[str, Any] = field(default_factory=dict)
    cwd: str = ""
    schema_version: int = CHECKPOINT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunCheckpoint:
        version = int(data.get("schema_version", -1))
        if version != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported checkpoint schema version: {version} "
                f"(expected {CHECKPOINT_SCHEMA_VERSION})."
            )
        task = str(data.get("task", ""))
        if not task:
            raise ValueError("Checkpoint is missing the original task text.")
        return cls(
            task=task,
            step_count=int(data.get("step_count", 0)),
            conversation_history=list(data.get("conversation_history") or []),
            steps=list(data.get("steps") or []),
            metadata=dict(data.get("metadata") or {}),
            plan=list(data.get("plan") or []),
            compressor_state=data.get("compressor_state"),
            reflexion_memory=data.get("reflexion_memory"),
            agent_config=dict(data.get("agent_config") or {}),
            cwd=str(data.get("cwd", "")),
            schema_version=version,
        )


def save_checkpoint(path: str | Path, checkpoint: RunCheckpoint) -> None:
    """checkpoint 原子落盘（同目录临时文件 + os.replace）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    tmp_path.write_text(
        json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, target)


def load_checkpoint(path: str | Path) -> RunCheckpoint:
    """加载并校验 checkpoint；版本不识别或结构损坏时抛 ValueError。"""
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Checkpoint file not found: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Checkpoint file is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Checkpoint file does not contain a JSON object.")
    return RunCheckpoint.from_dict(data)
