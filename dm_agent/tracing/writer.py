"""JSONL session/trace writer used to audit, resume, and replay agent runs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from dm_agent.memory.context_budget import estimate_tokens_from_chars

from .session import new_entry_id, normalize_entries

# 2.0: 每条 entry 带 id/parent_id，会话日志成为可导航的树；新增 message /
# compaction / checkpoint / fork 四类条目。老字段（event/payload）一个没动，
# 1.x 的文件仍然可读（读侧按序补 id），下游分析工具行为不变。
# 1.2: 新增 hook_error 增量事件；不改变既有 envelope 与字段语义。
# 1.1: additive events (observation_truncated, context_budget, edit_guard, ...)
# and the llm_call estimated_prompt_tokens field. Older traces stay parseable.
TRACE_SCHEMA_VERSION = "2.0"
SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


class TraceWriter:
    """Append-only JSONL session writer.

    The default mode records enough structure to audit an agent run without storing full
    prompts or raw model responses. Set ``capture_llm_io=True`` only for private debugging.

    每条 entry 都有 ``id``（``<run_id 前 8 位>-<四位序号>``）与 ``parent_id``（上一条的
    id）。``fork_parent_id`` 让分叉出来的会话第一条指回源会话的分叉点，从而把多份
    JSONL 串成一棵树。
    """

    def __init__(
        self,
        path: str | Path,
        *,
        capture_llm_io: bool = False,
        fork_parent_id: str = "",
        redact: bool = True,
        auto_close: bool = False,
    ) -> None:
        self.path = Path(path)
        self.capture_llm_io = capture_llm_io
        self.redact = redact
        self.auto_close = auto_close
        self.run_id = uuid.uuid4().hex
        self._handle: TextIO | None = None
        self._started = False
        self._ended = False
        self._seq = 0
        self._last_entry_id = fork_parent_id

    def __enter__(self) -> TraceWriter:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc is not None and self._started and not self._ended:
            self.record(
                "run_error",
                {
                    "error_type": getattr(exc_type, "__name__", str(exc_type)),
                    "message": str(exc),
                },
            )
        self.close()

    def open(self) -> None:
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def start_run(self, task: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._started = True
        self._ended = False
        self.record(
            "run_start",
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "task": task,
                "cwd": str(Path.cwd()),
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "capture_llm_io": self.capture_llm_io,
                "metadata": metadata or {},
            },
        )

    def finish_run(self, result: dict[str, Any]) -> None:
        self._ended = True
        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        self.record(
            "run_end",
            {
                "status": metadata.get("status"),
                "duration_seconds": metadata.get("duration_seconds"),
                "final_answer": result.get("final_answer", "") if isinstance(result, dict) else "",
                "metadata": metadata,
            },
        )

    def record_plan(self, steps: Iterable[Any]) -> None:
        plan = []
        for step in steps:
            plan.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "action": getattr(step, "action", None),
                    "reason": getattr(step, "reason", None),
                    "completed": getattr(step, "completed", False),
                }
            )
        self.record("plan", {"steps": plan})

    def record_plan_error(self, error: str) -> None:
        self.record("plan_error", {"error": error})

    def record_skills(self, skill_names: list[str]) -> None:
        self.record("skills", {"activated": skill_names})

    def record_llm_call(
        self,
        *,
        step_number: int,
        messages: list[dict[str, str]],
        temperature: float,
        raw_response: str | None = None,
    ) -> None:
        prompt_chars = sum(len(message.get("content", "")) for message in messages)
        payload: dict[str, Any] = {
            "step_number": step_number,
            "temperature": temperature,
            "message_count": len(messages),
            "roles": [message.get("role", "") for message in messages],
            "prompt_chars": prompt_chars,
            "estimated_prompt_tokens": estimate_tokens_from_chars(prompt_chars),
        }
        if self.capture_llm_io:
            payload["messages"] = messages
            payload["raw_response"] = raw_response
        elif raw_response is not None:
            payload["response_chars"] = len(raw_response)
        self.record("llm_call", payload)

    def record_parse_error(self, *, step_number: int, raw_response: str, error: str) -> None:
        payload: dict[str, Any] = {
            "step_number": step_number,
            "error": error,
            "response_chars": len(raw_response),
        }
        if self.capture_llm_io:
            payload["raw_response"] = raw_response
        self.record("parse_error", payload)

    def record_tool_call(
        self,
        *,
        step_number: int,
        action: str,
        action_input: Any,
        observation: str,
        failed: bool = False,
    ) -> None:
        self.record(
            "tool_call",
            {
                "step_number": step_number,
                "action": action,
                "action_input": action_input,
                "observation": observation,
                "failed": failed,
            },
        )

    def record_step(self, *, step_number: int, step: Any) -> None:
        payload = {
            "step_number": step_number,
            "thought": getattr(step, "thought", ""),
            "action": getattr(step, "action", ""),
            "action_input": getattr(step, "action_input", None),
            "observation": getattr(step, "observation", ""),
        }
        if self.capture_llm_io:
            payload["raw"] = getattr(step, "raw", "")
        self.record("step", payload)

    def record_replan(
        self,
        *,
        reason: str,
        steps: Iterable[Any],
        strategy: str = "",
        signal: dict[str, Any] | None = None,
    ) -> None:
        plan = []
        for step in steps:
            plan.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "action": getattr(step, "action", None),
                    "reason": getattr(step, "reason", None),
                }
            )
        payload: dict[str, Any] = {"reason": reason, "steps": plan}
        if strategy:
            payload["strategy"] = strategy
        if signal:
            payload["signal"] = signal
        self.record("replan", payload)

    def record_message(self, *, role: str, content: str, step_number: int, kind: str) -> str:
        """记录一条进入对话历史的消息，返回它的 entry id。

        保真档沿用既有口径：模型原始输出（``assistant``）默认只留长度与摘要指纹，
        ``capture_llm_io=True`` 时才落全文；其余角色记全文——它们的内容本来就是
        ``tool_call`` / ``step`` 条目里默认全量记录的观察结果的包装。
        """
        payload: dict[str, Any] = {
            "step_number": step_number,
            "role": role,
            "kind": kind,
            "content_chars": len(content),
        }
        if role == "assistant" and self.redact and not self.capture_llm_io:
            payload["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        else:
            payload["content"] = content
        return self.record("message", payload)

    def record_compaction(
        self,
        payload: dict[str, Any],
        *,
        first_kept_index: int | None = None,
        folded_indexes: Iterable[int] = (),
    ) -> str:
        """记录一次非破坏式折叠：原始消息条目一条不删，只记下这次跳过了哪些。"""
        return self.record("compaction", payload)

    def record_checkpoint_state(self, *, step_number: int, state: dict[str, Any]) -> str:
        """把可恢复状态作为一条条目追加进会话日志（不脱敏，见 record 的说明）。"""
        return self.record(
            "checkpoint",
            {"step_number": step_number, "state": state},
            sanitize=False,
        )

    def record(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        sanitize: bool | None = None,
    ) -> str:
        """追加一条会话条目，返回它的 entry id。

        ``sanitize=False`` 只给 ``checkpoint`` 条目用：脱敏会把 ``$HOME`` 改写成
        ``~``、把疑似密钥替换掉，写进可恢复状态会污染续跑的上下文。
        """
        self.open()
        assert self._handle is not None
        self._seq += 1
        entry_id = new_entry_id(self.run_id, self._seq)
        envelope = {
            "id": entry_id,
            "parent_id": self._last_entry_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            "payload": (
                _sanitize(payload) if (self.redact if sanitize is None else sanitize) else payload
            ),
        }
        self._handle.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
        self._handle.flush()
        self._last_entry_id = entry_id
        if self.auto_close:
            self.close()
        return entry_id


def load_trace_events(path: str | Path) -> list[dict[str, Any]]:
    """读取会话日志（或 1.x 的老 trace），缺失的 id/parent_id 在读侧补齐。"""
    events: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return normalize_entries(events)


class SessionWriter:
    """把会话事件扇出到多个保真档的门面。

    每个 ``TraceWriter`` 都保留自己的序号、父指针和隐私策略；本类只维护逻辑消息
    下标到各 sink 本地 entry id 的映射。这样同一条消息在 trace 与 checkpoint 中
    可以有不同 payload 和不同 id，而 ``compaction`` 仍能准确指向各自文件中的条目。
    """

    def __init__(self, trace_writer: TraceWriter | None = None) -> None:
        self._sinks: dict[str, TraceWriter] = {}
        self._message_entry_ids: dict[str, list[str]] = {}
        self._disabled_checkpoint_paths: set[Path] = set()
        if trace_writer is not None:
            self._sinks["trace"] = trace_writer
            self._message_entry_ids["trace"] = []

    def __bool__(self) -> bool:
        return bool(self._sinks)

    @property
    def run_id(self) -> str:
        writer = self._primary_writer()
        return str(getattr(writer, "run_id", "")) if writer is not None else ""

    @property
    def capture_llm_io(self) -> bool:
        """只暴露 trace sink 的 opt-in 状态，避免 checkpoint 反向打开脱敏档原文。"""
        writer = self._sinks.get("trace")
        return bool(getattr(writer, "capture_llm_io", False)) if writer is not None else False

    def start_run(self, task: str, *, metadata: dict[str, Any] | None = None) -> None:
        self._message_entry_ids = {name: [] for name in self._sinks}
        self._fanout("start_run", task, metadata=metadata)

    def finish_run(self, result: dict[str, Any]) -> None:
        self._fanout("finish_run", result)

    def close(self) -> None:
        for writer in list(self._sinks.values()):
            writer.close()

    def record(self, event: str, payload: dict[str, Any], *, sanitize: bool | None = None) -> str:
        return self._fanout("record", event, payload, sanitize=sanitize)

    def record_message(self, *, role: str, content: str, step_number: int, kind: str) -> str:
        """同时写入各 sink，并返回主 sink 的本地 entry id。"""
        results: dict[str, str] = {}
        for name, writer in list(self._sinks.items()):
            try:
                entry_id = writer.record_message(
                    role=role,
                    content=content,
                    step_number=step_number,
                    kind=kind,
                )
            except OSError as exc:
                self._disable_checkpoint_sink(name, exc)
                continue
            self._message_entry_ids.setdefault(name, []).append(entry_id)
            results[name] = entry_id
        return results.get(self._primary_name(), "")

    def record_compaction(
        self,
        payload: dict[str, Any],
        *,
        first_kept_index: int | None = None,
        folded_indexes: Iterable[int] = (),
    ) -> str:
        """按每个 sink 的消息 id 映射写折叠条目。"""
        folded_indexes = tuple(folded_indexes)
        results: dict[str, str] = {}
        for name, writer in list(self._sinks.items()):
            local_payload = dict(payload)
            if first_kept_index is not None:
                ids = self._message_entry_ids.get(name, [])
                local_payload["first_kept_entry_id"] = _local_message_id(ids, first_kept_index)
                local_payload["folded_entry_ids"] = [
                    _local_message_id(ids, index) for index in folded_indexes
                ]
            try:
                results[name] = writer.record_compaction(local_payload)
            except OSError as exc:
                self._disable_checkpoint_sink(name, exc)
        return results.get(self._primary_name(), "")

    def record_checkpoint_state(self, *, step_number: int, state: dict[str, Any]) -> str:
        """checkpoint 状态只进入本地完整 sink，不泄露到分享档。"""
        writer = self._sinks.get("checkpoint")
        if writer is None:
            return ""
        try:
            return writer.record_checkpoint_state(step_number=step_number, state=state)
        except OSError as exc:
            self._disable_checkpoint_sink("checkpoint", exc)
            return ""

    def ensure_checkpoint_sink(self, path: str | Path) -> None:
        """为 ``*.jsonl`` checkpoint 准备本地完整 sink。"""
        target = Path(path)
        if target.suffix.lower() != ".jsonl":
            return
        resolved = target.resolve()
        if resolved in self._disabled_checkpoint_paths:
            return
        for name, writer in self._sinks.items():
            if writer.path.resolve() == resolved:
                if name == "trace":
                    raise ValueError("--trace 与 --checkpoint 不能指向同一个文件。")
                return
        old = self._sinks.get("checkpoint")
        if old is not None:
            old.close()
        self._sinks["checkpoint"] = TraceWriter(
            target,
            capture_llm_io=False,
            redact=False,
            auto_close=True,
        )
        self._message_entry_ids["checkpoint"] = []

    def __getattr__(self, name: str) -> Any:
        """把新增的 ``record_*`` 方法透明转发给所有 sink。"""
        if name.startswith("record_"):
            return lambda *args, **kwargs: self._fanout(name, *args, **kwargs)
        raise AttributeError(name)

    def _fanout(self, method: str, *args: Any, **kwargs: Any) -> str:
        results: dict[str, Any] = {}
        for name, writer in list(self._sinks.items()):
            try:
                results[name] = getattr(writer, method)(*args, **kwargs)
            except OSError as exc:
                self._disable_checkpoint_sink(name, exc)
        return results.get(self._primary_name(), "")

    def _primary_name(self) -> str:
        if "trace" in self._sinks:
            return "trace"
        if "checkpoint" in self._sinks:
            return "checkpoint"
        return ""

    def _primary_writer(self) -> TraceWriter | None:
        name = self._primary_name()
        return self._sinks.get(name) if name else None

    def _disable_checkpoint_sink(self, name: str, error: OSError) -> None:
        if name != "checkpoint":
            raise error
        writer = self._sinks.pop(name, None)
        self._message_entry_ids.pop(name, None)
        if writer is not None:
            self._disabled_checkpoint_paths.add(writer.path.resolve())
            writer.close()
        print(f"[warn] checkpoint 会话写入失败，已停用该 sink：{error}")


def _local_message_id(entry_ids: list[str], index: int) -> str:
    if 0 <= index < len(entry_ids):
        return entry_ids[index]
    return ""


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_text(text: str) -> str:
    sanitized = text
    for name, value in os.environ.items():
        if len(value) < 6:
            continue
        if any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS):
            sanitized = sanitized.replace(value, f"<redacted-env:{name}>")

    home = str(Path.home())
    if home and home in sanitized:
        sanitized = sanitized.replace(home, "~")

    sanitized = re.sub(
        r"(?i)(api[_-]?key|token|secret|password)(\s*[=:]\s*)([^\s,'\"}]+)",
        r"\1\2<redacted>",
        sanitized,
    )
    sanitized = re.sub(r"(?i)(bearer\s+)[a-z0-9._\-]+", r"\1<redacted>", sanitized)
    return sanitized
