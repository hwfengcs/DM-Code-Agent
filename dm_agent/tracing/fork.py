"""Append-only session branching from an existing entry."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .session import find_entry_index, latest_checkpoint_entry
from .writer import TraceWriter


def _fork(
    entries: list[dict[str, Any]],
    *,
    source: Path,
    at: str,
    output: Path | None,
    as_json: bool,
) -> int:
    """把源会话截到 ``--at``（含）写成一份新会话，并指出能不能直接续跑。"""
    try:
        result = fork_session(entries, source=source, at=at, output=output)
    except ValueError as exc:
        print(f"Fork failed: {exc}", file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"Forked from: {source}")
    print(f"At entry: {result['forked_from_entry_id']}")
    print(f"Entries copied: {result['entry_count']}")
    print(f"Output: {result['output']}")
    if result["resumable_checkpoint_entry_id"]:
        print(
            f"Resumable at step {result['resumable_step_number']} "
            f"(entry {result['resumable_checkpoint_entry_id']})"
        )
        print(f"Next: dm-agent --resume {result['output']}")
    else:
        print(
            "No checkpoint entry at or before the fork point: this branch can be inspected "
            "but not resumed. Re-run the source task with --checkpoint <file>.jsonl to make "
            "forks resumable."
        )
    return 0


def fork_session(
    entries: list[dict[str, Any]],
    *,
    source: Path,
    at: str,
    output: Path | None = None,
) -> dict[str, Any]:
    """从 ``at`` 条目分叉出一份新的会话日志。

    分叉产物 = 源会话 ``[0..at]`` 的全部条目 + 一条 ``fork`` 条目（记下源文件与分叉点）。
    条目原样拷贝，因此新文件保留了原来的 id 链；``fork`` 条目的 ``parent_id`` 指回
    分叉点，把两份 JSONL 串成一棵树。

    Raises:
        ValueError: ``at`` 未命中/歧义，或目标文件已存在
    """
    index = find_entry_index(entries, at)
    entry_id = str(entries[index].get("id", ""))
    kept = entries[: index + 1]
    target = output or source.with_suffix("").with_name(f"{source.stem}.fork-{entry_id}.jsonl")
    if target.exists():
        raise ValueError(f"Refusing to overwrite an existing file: {target}")

    checkpoint = latest_checkpoint_entry(kept)
    checkpoint_payload = (checkpoint or {}).get("payload") or {}
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for entry in kept:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    writer = TraceWriter(target, fork_parent_id=entry_id)
    try:
        writer.record(
            "fork",
            {
                "source": str(source),
                "forked_from_entry_id": entry_id,
                "entry_count": len(kept),
            },
        )
    finally:
        writer.close()

    return {
        "mode": "session_fork",
        "source": str(source),
        "output": str(target),
        "forked_from_entry_id": entry_id,
        "entry_count": len(kept),
        "resumable_checkpoint_entry_id": str((checkpoint or {}).get("id", "")),
        "resumable_step_number": checkpoint_payload.get("step_number"),
    }
