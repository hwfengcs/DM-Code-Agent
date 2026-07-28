"""checkpoint 的编解码与写前备份。

``core/checkpoint.py`` 提供的是存储原语（原子写、schema 校验、备份文件拷贝）；
本模块负责把 ``ReactAgent`` 的运行期状态在「内存对象」与「checkpoint 字典」之间
来回翻译，并承担落盘失败、备份失败这类尽力而为的容错。

哪些状态值得存进 checkpoint 由 agent 决定（它才拥有这些状态）；
怎么存、存不下来怎么办由这里决定。

落盘有两种形态，按扩展名分流：

- ``*.jsonl`` —— append-only 的**会话日志**，每步追加一条 ``checkpoint`` 条目。
  于是 checkpoint 退化成「记住某个 entry id」，``--resume-at`` 可以挑更早的条目，
  ``dm-agent-trace fork`` 可以从任意条目分叉。
- 其余后缀 —— 原来的单文件 JSON 快照，原子覆盖写，语义完全不变。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from dm_agent.tracing.session import latest_checkpoint_entry, load_session_entries
from dm_agent.tracing.writer import SessionWriter, TraceWriter

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

# 会话日志形态的 checkpoint 文件后缀。
SESSION_SUFFIX = ".jsonl"


def is_session_checkpoint(path: str | Path) -> bool:
    """``*.jsonl`` 走会话日志形态，其余走单文件快照。"""
    return Path(path).suffix.lower() == SESSION_SUFFIX


class RunPersistence:
    """写前备份与 checkpoint 落盘的执行者。

    两件事都是**尽力而为**：备份或落盘失败绝不能中断任务，只记录并继续。
    """

    def __init__(self, *, trace_writer: Any | None = None) -> None:
        self.trace_writer = trace_writer
        # 旧的直接使用 RunPersistence 的调用方仍可走兼容 fallback；Agent 主路径
        # 使用共享 SessionWriter，因此 checkpoint 与普通会话条目共用同一条写入链。
        self._session_writer: TraceWriter | None = None

    def prepare_session_checkpoint(self, path: str | Path) -> None:
        """在 run_start 前准备 JSONL checkpoint sink，让首条消息也能被扇出。"""
        if not is_session_checkpoint(path):
            return
        if isinstance(self.trace_writer, SessionWriter):
            self.trace_writer.ensure_checkpoint_sink(path)

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
        """落盘一份可恢复状态；磁盘出问题时告警并继续执行。

        ``*.jsonl`` 追加一条 ``checkpoint`` 会话条目（append-only，历史快照全部留着，
        于是 ``--resume-at`` 能挑更早的条目）；其余后缀走原子覆盖写的单文件快照。
        """
        try:
            if is_session_checkpoint(path):
                self._append_session_checkpoint(path, checkpoint)
            else:
                save_checkpoint(path, checkpoint)
        except OSError as exc:
            print(f"[warn] checkpoint 保存失败：{exc}")
            return
        if self.trace_writer:
            self.trace_writer.record(
                "checkpoint_saved",
                {"step_number": checkpoint.step_count, "path": str(path)},
            )

    def _append_session_checkpoint(self, path: Path, checkpoint: RunCheckpoint) -> None:
        if isinstance(self.trace_writer, SessionWriter):
            self.trace_writer.ensure_checkpoint_sink(path)
            self.trace_writer.record_checkpoint_state(
                step_number=checkpoint.step_count,
                state=checkpoint.to_dict(),
            )
            return
        if self._session_writer is None:
            self._session_writer = TraceWriter(path)
        writer = self._session_writer
        try:
            writer.record_checkpoint_state(
                step_number=checkpoint.step_count,
                state=checkpoint.to_dict(),
            )
        finally:
            writer.close()


def load_resume_state(path: str | Path, *, at: str | None = None) -> RunCheckpoint:
    """加载 ``--resume`` 的起点，自动识别单文件快照与会话日志两种形态。

    Args:
        path: 老快照（整个文件是一个 JSON 对象）或会话日志（JSONL）
        at: 只对会话日志有效——从该 entry **或之前**最近的一条 checkpoint 条目恢复

    Raises:
        ValueError: 文件不存在、格式不识别、或会话日志里没有可用的 checkpoint 条目
    """
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Checkpoint file not found: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Checkpoint file is unreadable: {exc}") from exc

    snapshot = _as_json_object(text)
    if snapshot is not None:
        if at:
            raise ValueError("--resume-at 只适用于 JSONL 会话日志，单文件快照没有条目 id。")
        return RunCheckpoint.from_dict(snapshot)

    try:
        entries = load_session_entries(source)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Checkpoint file is neither a JSON snapshot nor session JSONL: {exc}"
        ) from exc
    entry = latest_checkpoint_entry(entries, until_entry_id=at)
    if entry is None:
        scope = f"at or before {at}" if at else "in this session"
        raise ValueError(
            f"No resumable checkpoint entry {scope}. "
            "会话日志需要用 --checkpoint *.jsonl 跑过才会有 checkpoint 条目。"
        )
    state = (entry.get("payload") or {}).get("state")
    if not isinstance(state, dict):
        raise ValueError(f"Checkpoint entry {entry.get('id')} carries no resumable state.")
    return RunCheckpoint.from_dict(state)


def _as_json_object(text: str) -> dict[str, Any] | None:
    """整个文件恰好是一个 JSON 对象时返回它，否则返回 None（按会话日志处理）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


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
