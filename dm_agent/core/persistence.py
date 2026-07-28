"""checkpoint 的编解码与写前备份。

``core/checkpoint.py`` 提供的是存储原语（原子写、schema 校验、备份文件拷贝）；
本模块负责把 ``ReactAgent`` 的运行期状态在「内存对象」与「checkpoint 字典」之间
来回翻译，并承担落盘失败、备份失败这类尽力而为的容错。

哪些状态值得存进 checkpoint 由 agent 决定（它才拥有这些状态）；
怎么存、存不下来怎么办由这里决定。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .checkpoint import RunCheckpoint, backup_file, save_checkpoint
from .planner import PlanStep
from .run_state import RunContext, Step

# resume 时会与 checkpoint 逐项比对的配置键（顺序即告警打印顺序）。
COMPARED_CONFIG_KEYS = (
    "temperature",
    "model",
    "enable_planning",
    "enable_compression",
    "enable_edit_guard",
    "max_observation_chars",
    "context_token_budget",
)


class RunPersistence:
    """写前备份与 checkpoint 落盘的执行者。

    两件事都是**尽力而为**：备份或落盘失败绝不能中断任务，只记录并继续。
    """

    def __init__(self, *, trace_writer: Any | None = None) -> None:
        self.trace_writer = trace_writer

    def backup_before_write(self, action_input: Any, context: RunContext) -> None:
        """写入类工具执行前备份原文件（尽力而为，失败不影响任务）。"""
        if not isinstance(action_input, dict):
            return
        path = action_input.get("path")
        if not isinstance(path, str) or not path:
            return
        backup_path = backup_file(path, run_id=context.run_id, step=context.step_number)
        if backup_path is None:
            return
        metadata = context.metadata
        metadata["backup_count"] += 1
        metadata["backup_dir"] = str(backup_path.parent)
        if self.trace_writer:
            self.trace_writer.record(
                "file_backup",
                {
                    "step_number": context.step_number,
                    "path": path,
                    "backup_path": str(backup_path),
                },
            )

    def save(self, path: Path, checkpoint: RunCheckpoint) -> None:
        """原子落盘一份快照；磁盘出问题时告警并继续执行。"""
        try:
            save_checkpoint(path, checkpoint)
        except OSError as exc:
            print(f"[warn] checkpoint 保存失败：{exc}")
            return
        if self.trace_writer:
            self.trace_writer.record(
                "checkpoint_saved",
                {"step_number": checkpoint.step_count, "path": str(path)},
            )


def agent_config_snapshot(
    *,
    temperature: float,
    model: str,
    enable_planning: bool,
    enable_compression: bool,
    enable_edit_guard: bool,
    max_observation_chars: int,
    context_token_budget: int,
    max_steps: int | None = None,
) -> dict[str, Any]:
    """构造 checkpoint 里的 ``agent_config``，以及 resume 时的比对基准。

    ``max_steps`` 只有落盘时才带上，resume 比对不看它（换更大的步数上限续跑是
    正常用法）。键顺序即 checkpoint JSON 的字段顺序。
    """
    snapshot: dict[str, Any] = {
        "temperature": temperature,
        "model": model,
        "enable_planning": enable_planning,
        "enable_compression": enable_compression,
        "enable_edit_guard": enable_edit_guard,
        "max_observation_chars": max_observation_chars,
        "context_token_budget": context_token_budget,
    }
    if max_steps is None:
        return snapshot
    return {"max_steps": max_steps, **snapshot}


def warn_on_config_mismatch(saved_config: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    """逐项比对 resume 前后的配置，不一致时告警（不阻断）。"""
    for key, value in current.items():
        saved = saved_config.get(key)
        if saved is not None and saved != value:
            print(f"[warn] resume 配置不一致：{key} checkpoint={saved} 当前={value}")


def json_safe_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """把 metadata 过一遍 JSON 往返，确保落盘的是可序列化的纯数据。"""
    return dict(json.loads(json.dumps(metadata, ensure_ascii=False, default=str)))


def plan_to_checkpoint(plan: Iterable[PlanStep]) -> list[dict[str, Any]]:
    """计划步骤 -> checkpoint 字典。"""
    return [
        {
            "step_number": step.step_number,
            "action": step.action,
            "reason": step.reason,
            "completed": step.completed,
            "result": step.result,
        }
        for step in plan
    ]


def plan_from_checkpoint(raw_plan: Iterable[Mapping[str, Any]]) -> list[PlanStep]:
    """checkpoint 字典 -> 计划步骤。"""
    return [
        PlanStep(
            step_number=int(item.get("step_number", index + 1)),
            action=str(item.get("action", "")),
            reason=str(item.get("reason", "")),
            completed=bool(item.get("completed", False)),
            result=item.get("result"),
        )
        for index, item in enumerate(raw_plan)
    ]


def steps_from_checkpoint(raw_steps: Iterable[Mapping[str, Any]]) -> list[Step]:
    """checkpoint 字典 -> 推理步骤。"""
    return [
        Step(
            thought=str(raw_step.get("thought", "")),
            action=str(raw_step.get("action", "")),
            action_input=raw_step.get("action_input"),
            observation=str(raw_step.get("observation", "")),
            raw=str(raw_step.get("raw", "")),
        )
        for raw_step in raw_steps
    ]


def metadata_from_checkpoint(
    raw_metadata: Mapping[str, Any], *, resume_from: int
) -> dict[str, Any]:
    """还原 metadata：状态改回 running，丢掉上一轮的耗时，记下续跑起点。"""
    restored = dict(raw_metadata)
    restored["status"] = "running"
    restored.pop("duration_seconds", None)
    restored["resumed_from_step"] = resume_from
    return restored
