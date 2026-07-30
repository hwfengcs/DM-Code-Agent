"""运行的创建、实时流与取消。

这三个端点都是**写操作**（发起运行会在你的工作区真实读写文件），所以全部挂
``require_writable``——``--read-only`` 下一律 403。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dm_agent.clients import PROVIDER_DEFAULTS
from dm_agent.server.process import RunProcess, RunSpec, SpecError, build_argv
from dm_agent.server.runs import RunRecord, RunRegistry
from dm_agent.server.security import get_registry, get_settings, require_token, require_writable
from dm_agent.server.settings import ServerSettings, SessionPathError, resolve_session_path
from dm_agent.server.streaming import parse_last_event_id, sse_message, stream_session_lines

router = APIRouter(
    prefix="/api/runs",
    tags=["runs"],
    dependencies=[Depends(require_token), Depends(require_writable)],
)


class CreateRunRequest(BaseModel):
    """发起一次运行。``options`` 的键对应 ``/api/meta`` 里 capability 目录的 ``key``。"""

    task: str = Field(min_length=1, description="自然语言任务")
    provider: str = Field(default="deepseek")
    model: str = Field(default="", description="留空则用该 provider 的默认模型")
    options: dict[str, Any] = Field(default_factory=dict)


@router.post("", summary="发起一次运行", status_code=status.HTTP_201_CREATED)
def create_run(
    payload: CreateRunRequest,
    settings: Annotated[ServerSettings, Depends(get_settings)],
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    """spawn 一个 ``dm-agent`` 子进程，立刻返回 run_id。

    进度不在这个响应里——客户端接着连 ``/api/runs/{id}/stream`` 看实时条目。
    """
    if registry.at_capacity():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已有运行在进行中。同时跑多个 agent 会互相踩同一个工作区，请先等它结束或取消。",
        )

    spec = RunSpec(
        task=payload.task,
        provider=payload.provider,
        model=payload.model,
        options=payload.options,
    )
    try:
        spec.validate(set(PROVIDER_DEFAULTS))
    except SpecError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run_id = registry.new_run_id()
    session_name = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{run_id}.jsonl"
    trace_path = settings.sessions_dir / session_name
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)

    process = RunProcess(
        build_argv(spec, trace_path=trace_path),
        cwd=settings.workspace,
        trace_path=trace_path,
    )
    try:
        process.start()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"子进程启动失败：{exc}",
        ) from exc

    record = RunRecord(
        run_id=run_id,
        task=spec.task,
        session_name=session_name,
        trace_path=trace_path,
        process=process,
    )
    registry.register(record)
    return record.to_payload()


@router.get("", summary="列出本次进程生命周期内的运行")
def list_runs(registry: Annotated[RunRegistry, Depends(get_registry)]) -> dict[str, Any]:
    """注册表是内存态，控制台重启后清空——已完成运行的真相在会话 JSONL 里。"""
    return {"runs": [record.to_payload() for record in registry.list()]}


@router.get("/{run_id}", summary="查询单个运行的状态")
def read_run(
    run_id: str,
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    return _require_record(registry, run_id).to_payload()


@router.delete("/{run_id}", summary="取消一个在跑的运行")
def cancel_run(
    run_id: str,
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    """终止子进程树。

    已写入的会话日志**保留**——被取消的运行同样是可审计的证据，
    事后还能看它走到哪一步、为什么想停。
    """
    record = _require_record(registry, run_id)
    stopped = registry.cancel(run_id)
    payload = record.to_payload()
    payload["stopped"] = stopped
    return payload


@router.get("/{run_id}/stream", summary="实时条目流（SSE）")
async def stream_run(
    run_id: str,
    registry: Annotated[RunRegistry, Depends(get_registry)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """跟读该运行的会话日志，每条条目发一个 ``entry`` 事件，结束时发 ``done``。

    断线重连时浏览器会自动带上 ``Last-Event-ID``，据此跳过已收到的行。
    """
    record = _require_record(registry, run_id)
    start_after = parse_last_event_id(last_event_id)

    def is_finished() -> bool:
        current = registry.get(run_id)
        return current is None or not current.is_running

    def finish_payload() -> dict[str, Any]:
        current = registry.get(run_id)
        return current.to_payload() if current else {"run_id": run_id, "status": "unknown"}

    async def body() -> Any:
        # 先把当前状态发出去，前端不用等第一条条目才知道自己连上了。
        yield sse_message(event="status", data=record.to_payload())
        async for chunk in stream_session_lines(
            record.trace_path,
            start_after=start_after,
            is_finished=is_finished,
            finish_payload=finish_payload,
        ):
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # nginx 一类反代默认会缓冲响应体，那会让「实时」变成「一次性」。
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _require_record(registry: RunRegistry, run_id: str) -> RunRecord:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未知的运行：{run_id}")
    return record


def resolve_run_session(settings: ServerSettings, name: str) -> Path:
    """运行产生的会话名也要过同一道边界检查。"""
    try:
        return resolve_session_path(settings, name)
    except SessionPathError as exc:  # pragma: no cover - 由会话路由覆盖
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
