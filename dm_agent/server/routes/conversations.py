"""多轮对话：长驻子进程的创建、投递、实时流与结束。

与 ``routes/runs.py`` 的区别只有一条，但它决定了整个多轮语义：**子进程不在一轮结束
后退出**。它用 ``--conversation-stdin`` 一直活着等下一轮任务，因此同一个 ``ReactAgent``
的对话历史、本地记忆与折叠状态跨轮延续。这是「真多轮」与「界面上把气泡连起来」的
全部区别所在。

三条对外约定：

* **投递是单向的**：server 只往子进程 stdin 写任务。每一轮的进展、结果、失败全都
  从会话日志里读回来（``run_start`` / ``run_end`` 本来就在），不存在第二条旁路。
* **实时流跨轮持续**：``/stream`` 只在整个对话结束时才发 ``done``，中间每一轮的
  ``run_start`` / ``run_end`` 就是天然的轮次边界。
* **停止 = 结束整个对话**，不是只打断当前这一轮。``ReactAgent`` 没有取消接口
  （见 ``process.py`` 的模块 docstring），能做的只有收掉进程。
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dm_agent.clients import PROVIDER_DEFAULTS
from dm_agent.server.process import (
    MAX_TASK_CHARS,
    RunProcess,
    RunSpec,
    SpecError,
    build_conversation_argv,
)
from dm_agent.server.runs import RunRecord, RunRegistry
from dm_agent.server.security import get_registry, get_settings, require_token, require_writable
from dm_agent.server.settings import ServerSettings
from dm_agent.server.streaming import parse_last_event_id, sse_message, stream_session_lines

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_token), Depends(require_writable)],
)


class CreateConversationRequest(BaseModel):
    """开一次多轮对话。``options`` 的键对应 ``/api/meta`` 里 capability 目录的 ``key``。

    刻意**不带首轮任务**：开关在 spawn 时就固化进 argv 了，而任务是逐轮送的。
    把两件事分开，前端才能诚实地在对话开始后锁住设置区。
    """

    provider: str = Field(default="deepseek")
    model: str = Field(default="", description="留空则用该 provider 的默认模型")
    options: dict[str, Any] = Field(default_factory=dict)


class SubmitTurnRequest(BaseModel):
    task: str = Field(min_length=1, max_length=MAX_TASK_CHARS, description="这一轮的自然语言任务")


@router.post("", summary="开一次多轮对话", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: CreateConversationRequest,
    settings: Annotated[ServerSettings, Depends(get_settings)],
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    """spawn 一个长驻 ``dm-agent --conversation-stdin`` 子进程，立刻返回 id。"""
    if registry.at_capacity():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已有运行或对话在进行中。同时跑多个 agent 会互相踩同一个工作区。",
        )

    spec = RunSpec(task="", provider=payload.provider, model=payload.model, options=payload.options)
    try:
        # 建对话时还没有任务（详见 RunSpec.validate）。
        spec.validate(set(PROVIDER_DEFAULTS), for_conversation=True)
    except SpecError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run_id = registry.new_run_id()
    session_name = f"chat-{time.strftime('%Y%m%d-%H%M%S')}-{run_id}.jsonl"
    trace_path = settings.sessions_dir / session_name
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)

    process = RunProcess(
        build_conversation_argv(spec, trace_path=trace_path),
        cwd=settings.workspace,
        trace_path=trace_path,
    )
    try:
        process.start(stdin_pipe=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"子进程启动失败：{exc}",
        ) from exc

    record = RunRecord(
        run_id=run_id,
        task="",
        session_name=session_name,
        trace_path=trace_path,
        process=process,
        kind="conversation",
    )
    registry.register(record)
    return record.to_payload()


@router.get("", summary="列出本次进程生命周期内的对话")
def list_conversations(registry: Annotated[RunRegistry, Depends(get_registry)]) -> dict[str, Any]:
    registry.reap_idle()
    return {
        "conversations": [
            record.to_payload() for record in registry.list() if record.kind == "conversation"
        ]
    }


@router.get("/{conversation_id}", summary="查询一个对话的状态")
def read_conversation(
    conversation_id: str,
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    return _require_conversation(registry, conversation_id).to_payload()


@router.post("/{conversation_id}/turns", summary="提交下一轮任务")
def submit_turn(
    conversation_id: str,
    payload: SubmitTurnRequest,
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    """把一轮任务写进子进程 stdin。

    上一轮还没跑完就再投一轮会被拒（409）——``ReactAgent`` 是单线程顺序执行的，
    排队只会让「现在到底在干哪一轮」变得不可读。前端据此禁用输入框。
    """
    record = _require_conversation(registry, conversation_id)
    if not record.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这个对话已经结束了。请新开一个对话。",
        )
    if record.is_busy:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="上一轮还在执行。等它结束（或先停止对话）再发下一轮。",
        )

    task = payload.task.strip()
    if not task:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务不能为空。")

    turn = registry.submit_turn(conversation_id, task)
    if turn is None:
        # send_line 失败：子进程在这几毫秒里死了。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="任务没能送进 agent 进程，它可能刚刚退出了。",
        )
    return {"turn": turn.to_payload(), "conversation": record.to_payload()}


@router.delete("/{conversation_id}", summary="结束整个对话")
def end_conversation(
    conversation_id: str,
    registry: Annotated[RunRegistry, Depends(get_registry)],
) -> dict[str, Any]:
    """先关 stdin 让 agent 自己收尾，超时才硬杀。

    已写入的会话日志**保留**——被中途结束的对话同样是可审计的证据。
    """
    record = _require_conversation(registry, conversation_id)
    stopped = registry.cancel(conversation_id)
    payload = record.to_payload()
    payload["stopped"] = stopped
    return payload


@router.get("/{conversation_id}/stream", summary="实时条目流（SSE，跨轮持续）")
async def stream_conversation(
    conversation_id: str,
    registry: Annotated[RunRegistry, Depends(get_registry)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """跟读该对话的会话日志。

    与单次运行的流唯一的区别：``is_finished`` 判的是**整个对话进程**是否退出，
    所以这条连接会横跨全部轮次。前端因此可以在切视图、甚至刷新页面后重新接上
    （``Last-Event-ID`` 续传），而不是每轮重连一次。
    """
    record = _require_conversation(registry, conversation_id)
    start_after = parse_last_event_id(last_event_id)

    def is_finished() -> bool:
        current = registry.get(conversation_id)
        return current is None or not current.is_running

    def finish_payload() -> dict[str, Any]:
        current = registry.get(conversation_id)
        return current.to_payload() if current else {"run_id": conversation_id, "status": "unknown"}

    async def body() -> Any:
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


def _require_conversation(registry: RunRegistry, conversation_id: str) -> RunRecord:
    record = registry.get(conversation_id)
    if record is None or record.kind != "conversation":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未知的对话：{conversation_id}",
        )
    return record
