"""会话（trace/checkpoint JSONL）的只读 API。

这一层几乎不写业务逻辑：会话摘要、诊断、行为 diff、分叉全都直接复用
``dm_agent.tracing`` 里已经被 ``dm-agent-trace`` 与其测试固化过的纯函数，
保证 Web 控制台和 CLI 看到的是同一套结论。

两条对外约定：

* **只暴露相对会话名**，绝不把开发机的绝对路径写进响应——只读展厅是要公开分享的。
* 子资源用查询参数 ``?name=`` 而不是路径段。会话名可以含子目录，
  ``/{name:path}/summary`` 这种写法会被贪婪匹配吃掉后缀，不可靠。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from dm_agent.server.security import get_settings, require_token, require_writable
from dm_agent.server.settings import (
    ServerSettings,
    SessionPathError,
    relative_session_name,
    resolve_session_path,
)
from dm_agent.tracing.analysis import analyze_events
from dm_agent.tracing.fork import fork_session
from dm_agent.tracing.session import load_session_entries
from dm_agent.tracing.summary import diff_events, summarize_events

router = APIRouter(prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(require_token)])

# 单次 entries 请求的返回上限。长会话靠 offset 翻页，避免一口气把几万条 payload
# 塞进一个响应里把浏览器打死。
DEFAULT_ENTRY_LIMIT = 1000
MAX_ENTRY_LIMIT = 5000

# 会话卡片缓存：路径 → (mtime_ns, size, card)。会话日志是 append-only 的，
# mtime+size 一致就说明内容没变，可以直接复用上次的解析结果。
_CARD_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}


class ForkRequest(BaseModel):
    """从某条会话条目分叉出一份新会话。"""

    name: str = Field(description="源会话名，相对 sessions 目录")
    at: str = Field(description="分叉点的 entry id 或其可唯一匹配的前缀")
    output: str | None = Field(
        default=None,
        description="目标会话名；省略时由 tracing 层按 <源名>.fork-<entry id>.jsonl 生成",
    )


def _load(settings: ServerSettings, name: str) -> list[dict[str, Any]]:
    """解析会话名并读出全部条目，把两类失败翻译成合适的 HTTP 状态码。"""
    try:
        path = resolve_session_path(settings, name)
    except SessionPathError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        return load_session_entries(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"会话文件无法解析：{exc}",
        ) from exc


def _session_card(settings: ServerSettings, path: Path) -> dict[str, Any]:
    """会话列表里的一张卡片：摘要 + 健康度 + 文件元信息。"""
    stat = path.stat()
    cache_key = str(path)
    cached = _CARD_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]

    entries = load_session_entries(path)
    summary = summarize_events(entries)
    analysis = analyze_events(entries)
    card = {
        "name": relative_session_name(settings, path),
        "run_id": summary.get("run_id", ""),
        "task": summary.get("task", ""),
        "status": summary.get("status", ""),
        "provider": summary.get("provider"),
        "model": summary.get("model"),
        "step_count": summary.get("step_count", 0),
        "event_count": summary.get("event_count", 0),
        "tool_call_count": summary.get("tool_call_count", 0),
        "replan_count": summary.get("replan_count", 0),
        "duration_seconds": summary.get("duration_seconds"),
        # 一个 JSONL 可以连续记录多个 run；摘要口径与 dm-agent-trace 一致（取首个
        # run_start + 末个 run_end），但把 run 数量透出来，前端好提示「这里有多段」。
        "run_count": sum(1 for entry in entries if entry.get("event") == "run_start"),
        "health": analysis.get("trace_health", {}),
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
    }
    _CARD_CACHE[cache_key] = (stat.st_mtime_ns, stat.st_size, card)
    return card


@router.get("", summary="列出全部会话")
def list_sessions(
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> dict[str, Any]:
    """扫描 sessions 目录，按修改时间倒序返回会话卡片。"""
    cards: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if settings.sessions_dir.is_dir():
        for path in sorted(settings.sessions_dir.rglob("*.jsonl")):
            if not path.is_file():
                continue
            try:
                cards.append(_session_card(settings, path))
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                # 坏文件不能让整个列表 500——单独列出来，前端标成不可读。
                errors.append({"name": relative_session_name(settings, path), "error": str(exc)})
    cards.sort(key=lambda card: card["modified"], reverse=True)
    grades = [str(card["health"].get("grade", "")) for card in cards]
    return {
        "sessions": cards,
        "errors": errors,
        "aggregate": {
            "total": len(cards),
            "unreadable": len(errors),
            "by_status": _count(str(card["status"]) for card in cards),
            "by_health": _count(grades),
        },
    }


@router.get("/entries", summary="读取会话条目（分页）")
def read_entries(
    settings: Annotated[ServerSettings, Depends(get_settings)],
    name: Annotated[str, Query(description="会话名，相对 sessions 目录")],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_ENTRY_LIMIT)] = DEFAULT_ENTRY_LIMIT,
) -> dict[str, Any]:
    """返回条目原文。id / parent_id 已由 tracing 读侧补齐（含 1.x 老 trace）。"""
    entries = _load(settings, name)
    window = entries[offset : offset + limit]
    return {
        "name": name,
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "entries": window,
    }


@router.get("/summary", summary="会话摘要")
def read_summary(
    settings: Annotated[ServerSettings, Depends(get_settings)],
    name: Annotated[str, Query()],
) -> dict[str, Any]:
    """等价于 ``dm-agent-trace view --json``。"""
    return {"name": name, "summary": summarize_events(_load(settings, name))}


@router.get("/analysis", summary="会话诊断")
def read_analysis(
    settings: Annotated[ServerSettings, Depends(get_settings)],
    name: Annotated[str, Query()],
) -> dict[str, Any]:
    """等价于 ``dm-agent-trace analyze --json``：失败阶段、恢复链路、验证缺口、幻觉信号。"""
    return {"name": name, "analysis": analyze_events(_load(settings, name))}


@router.get("/diff", summary="两次运行的行为 diff")
def read_diff(
    settings: Annotated[ServerSettings, Depends(get_settings)],
    a: Annotated[str, Query(description="基准会话名")],
    b: Annotated[str, Query(description="对比会话名")],
) -> dict[str, Any]:
    """等价于 ``dm-agent-trace diff --json``。"""
    return {
        "a": a,
        "b": b,
        "diff": diff_events(_load(settings, a), _load(settings, b)),
    }


@router.post(
    "/fork",
    summary="从某条条目分叉出新会话",
    dependencies=[Depends(require_writable)],
    status_code=status.HTTP_201_CREATED,
)
def create_fork(
    settings: Annotated[ServerSettings, Depends(get_settings)],
    payload: ForkRequest,
) -> dict[str, Any]:
    """等价于 ``dm-agent-trace fork --at <id>``。

    目标路径也要过 ``sessions_dir`` 的边界检查——``output`` 是外部输入，
    不能让它把文件写到目录外。
    """
    entries = _load(settings, payload.name)
    source = resolve_session_path(settings, payload.name)

    output: Path | None = None
    if payload.output:
        try:
            output = _resolve_new_session_path(settings, payload.output)
        except SessionPathError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        result = fork_session(entries, source=source, at=payload.at, output=output)
    except ValueError as exc:
        # at 未命中/歧义，或目标已存在——都是客户端可修正的输入问题。
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    result["source"] = relative_session_name(settings, Path(result["source"]))
    result["output"] = relative_session_name(settings, Path(result["output"]))
    return result


def _resolve_new_session_path(settings: ServerSettings, name: str) -> Path:
    """校验一个**尚不存在**的目标会话名。

    ``resolve_session_path`` 要求文件已存在，分叉的目标恰好相反，所以这里单独做
    同样的后缀 / 绝对路径 / 越界三道检查，只是不检查存在性。
    """
    candidate = Path(name)
    if candidate.is_absolute() or candidate.drive or name.startswith(("/", "\\")):
        raise SessionPathError(f"目标会话名必须是相对路径：{name}")
    if candidate.suffix.lower() != ".jsonl":
        raise SessionPathError(f"目标会话名必须以 .jsonl 结尾：{name}")
    target = (settings.sessions_dir / candidate).resolve()
    try:
        target.relative_to(settings.sessions_dir)
    except ValueError as exc:
        raise SessionPathError(f"目标会话名越出了 sessions 目录：{name}") from exc
    return target


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value) or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
