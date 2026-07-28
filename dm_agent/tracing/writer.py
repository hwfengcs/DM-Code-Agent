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
    ) -> None:
        self.path = Path(path)
        self.capture_llm_io = capture_llm_io
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

    def record_critic_review(self, *, step_number: int, review: dict[str, Any]) -> None:
        payload = {"step_number": step_number}
        payload.update(review)
        self.record("critic_review", payload)

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
        if role == "assistant" and not self.capture_llm_io:
            payload["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        else:
            payload["content"] = content
        return self.record("message", payload)

    def record_compaction(self, payload: dict[str, Any]) -> str:
        """记录一次非破坏式折叠：原始消息条目一条不删，只记下这次跳过了哪些。"""
        return self.record("compaction", payload)

    def record_checkpoint_state(self, *, step_number: int, state: dict[str, Any]) -> str:
        """把可恢复状态作为一条条目追加进会话日志（不脱敏，见 record 的说明）。"""
        return self.record(
            "checkpoint",
            {"step_number": step_number, "state": state},
            sanitize=False,
        )

    def record(self, event: str, payload: dict[str, Any], *, sanitize: bool = True) -> str:
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
            "payload": _sanitize(payload) if sanitize else payload,
        }
        self._handle.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
        self._handle.flush()
        self._last_entry_id = entry_id
        return entry_id


def load_trace_events(path: str | Path) -> list[dict[str, Any]]:
    """读取会话日志（或 1.x 的老 trace），缺失的 id/parent_id 在读侧补齐。"""
    events: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return normalize_entries(events)


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
