"""会话日志的读侧原语：条目身份、老格式归一化、上下文重建。

一次 run 的历史被写成 append-only 的 JSONL 会话日志，每条带 ``id`` 与 ``parent_id``，
于是「线性日志」变成「可导航的树」：能定位到某条条目续跑（``--resume-at``），
也能从某条条目分叉（``dm-agent-trace fork``）。

写侧在 ``tracing/writer.py``；本模块只负责读：把文件（含 1.x 的老 trace）归一化成
统一的条目列表，并在此之上提供两个能力——按 id 定位条目、按 ``compaction`` 条目
重建当时发给 LLM 的上下文。后者是 ``no_compression`` ablation 的基础：同一份日志
既能复现「真正发出去的窗口」，也能复现「假装从没压缩过的全量历史」。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# 1.x 的老 trace 没有条目 id，读进来时按序合成，保证下游工具一律可用。
LEGACY_ID_PREFIX = "legacy-"

MESSAGE_EVENT = "message"
COMPACTION_EVENT = "compaction"
CHECKPOINT_EVENT = "checkpoint"
FORK_EVENT = "fork"
RUN_START_EVENT = "run_start"


def new_entry_id(run_id: str, seq: int) -> str:
    """构造条目 id：``<run_id 前 8 位>-<四位序号>``。

    刻意做成可读、可手敲的短串——``--at`` / ``--resume-at`` 接受唯一前缀，
    用户从 ``dm-agent-trace view`` 的输出里抄一段就能用。
    """
    return f"{(run_id or 'run')[:8]}-{seq:04d}"


def normalize_entries(raw_entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """补齐缺失的 ``id`` / ``parent_id``，让老格式与新格式在读侧无差别。

    只补不改：已有 id 的条目原样保留，因此新旧混写的文件（同一路径先被 1.x
    写过、又被 2.0 追加）也能正确串起来。
    """
    entries: list[dict[str, Any]] = []
    previous_id = ""
    for index, raw in enumerate(raw_entries):
        entry = dict(raw)
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            entry_id = f"{LEGACY_ID_PREFIX}{index:04d}"
            entry["id"] = entry_id
        if entry.get("parent_id") is None:
            entry["parent_id"] = previous_id
        previous_id = entry_id
        entries.append(entry)
    return entries


def load_session_entries(path: str | Path) -> list[dict[str, Any]]:
    """读取会话日志（或老 trace）并归一化。"""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return normalize_entries(json.loads(line) for line in lines if line.strip())


def find_entry_index(entries: list[dict[str, Any]], reference: str) -> int:
    """按 id 精确或唯一前缀定位条目下标；未命中/歧义时抛 ValueError。"""
    reference = str(reference or "").strip()
    if not reference:
        raise ValueError("Entry id is required.")
    exact = [index for index, entry in enumerate(entries) if entry.get("id") == reference]
    if exact:
        return exact[0]
    prefixed = [
        index
        for index, entry in enumerate(entries)
        if str(entry.get("id", "")).startswith(reference)
    ]
    if not prefixed:
        raise ValueError(f"No session entry matches id {reference!r}.")
    if len(prefixed) > 1:
        matched = ", ".join(str(entries[index].get("id")) for index in prefixed[:5])
        raise ValueError(f"Entry id {reference!r} is ambiguous; matches: {matched} ...")
    return prefixed[0]


def find_entry(entries: list[dict[str, Any]], reference: str) -> dict[str, Any]:
    """按 id 精确或唯一前缀取条目。"""
    return entries[find_entry_index(entries, reference)]


def message_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """按写入顺序取出所有对话消息条目。"""
    return [entry for entry in entries if entry.get("event") == MESSAGE_EVENT]


def conversation_from_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """从消息条目还原对话历史。

    脱敏档里 assistant 消息只留 ``content_chars`` / ``content_sha256``，此时用
    ``<redacted:...>`` 占位——序列与角色仍然逐位可比，这正是「压缩非破坏性」
    验收要比的东西。
    """
    history: list[dict[str, str]] = []
    for entry in message_entries(entries):
        payload = entry.get("payload") or {}
        history.append(
            {
                "role": str(payload.get("role", "")),
                "content": _message_content(payload),
            }
        )
    return history


def rebuild_context(
    entries: Iterable[dict[str, Any]],
    *,
    apply_compaction: bool = True,
    until_entry_id: str | None = None,
) -> list[dict[str, str]]:
    """重建某一步发给 LLM 的对话窗口（不含 system prompt）。

    ``apply_compaction=True`` 复现当时真正发出去的窗口；``False`` 则无视所有
    ``compaction`` 条目，得到「假装从没压缩过」的全量历史。两者相减就是这次
    压缩折叠掉的原文——``no_compression`` ablation 需要的正是这个差值。

    Args:
        entries: 会话条目（已归一化）
        apply_compaction: 是否套用 ``compaction`` 条目的折叠区间
        until_entry_id: 只看这条之前（含）的条目；``None`` 表示看到末尾
    """
    collected = list(entries)
    if until_entry_id is not None:
        collected = collected[: find_entry_index(collected, until_entry_id) + 1]

    history: list[dict[str, str]] = []
    history_ids: list[str] = []
    summary = ""
    first_kept_entry_id = ""
    for entry in collected:
        event = entry.get("event")
        payload = entry.get("payload") or {}
        if event == RUN_START_EVENT:
            # 一个 writer 可以连续记录多个 run；run_start 是对话窗口的硬边界，旧 run
            # 的消息与 compaction 仍留在 append-only 日志里，但不得混进当前窗口。
            history.clear()
            history_ids.clear()
            summary = ""
            first_kept_entry_id = ""
        elif event == MESSAGE_EVENT:
            history.append(
                {"role": str(payload.get("role", "")), "content": _message_content(payload)}
            )
            history_ids.append(str(entry.get("id", "")))
        elif event == COMPACTION_EVENT and apply_compaction:
            summary = str(payload.get("summary", ""))
            first_kept_entry_id = str(payload.get("first_kept_entry_id", ""))

    if not (apply_compaction and first_kept_entry_id):
        return history

    try:
        start = history_ids.index(first_kept_entry_id)
    except ValueError:
        # 折叠起点不在本次截断范围内（例如 until_entry_id 早于压缩点），按未压缩处理。
        return history
    memory = [{"role": "user", "content": summary}] if summary else []
    return memory + history[start:]


def latest_checkpoint_entry(
    entries: list[dict[str, Any]],
    *,
    until_entry_id: str | None = None,
) -> dict[str, Any] | None:
    """取最后一条 ``checkpoint`` 条目；``until_entry_id`` 限定不晚于该条目。"""
    scoped = entries
    if until_entry_id is not None:
        scoped = entries[: find_entry_index(entries, until_entry_id) + 1]
    for entry in reversed(scoped):
        if entry.get("event") == CHECKPOINT_EVENT:
            return entry
    return None


def _message_content(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    digest = payload.get("content_sha256") or ""
    chars = payload.get("content_chars") or 0
    return f"<redacted:{chars}chars:{digest}>"
