"""JSONL trace writer used to audit and replay agent runs."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRACE_SCHEMA_VERSION = "1.0"
SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


class TraceWriter:
    """Append-only JSONL trace writer.

    The default mode records enough structure to audit an agent run without storing full
    prompts or raw model responses. Set ``capture_llm_io=True`` only for private debugging.
    """

    def __init__(self, path: str | Path, *, capture_llm_io: bool = False) -> None:
        self.path = Path(path)
        self.capture_llm_io = capture_llm_io
        self.run_id = uuid.uuid4().hex
        self._handle = None
        self._started = False
        self._ended = False

    def __enter__(self) -> "TraceWriter":
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

    def start_run(self, task: str, *, metadata: Optional[Dict[str, Any]] = None) -> None:
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

    def finish_run(self, result: Dict[str, Any]) -> None:
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

    def record_skills(self, skill_names: List[str]) -> None:
        self.record("skills", {"activated": skill_names})

    def record_llm_call(
        self,
        *,
        step_number: int,
        messages: List[Dict[str, str]],
        temperature: float,
        raw_response: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "step_number": step_number,
            "temperature": temperature,
            "message_count": len(messages),
            "roles": [message.get("role", "") for message in messages],
            "prompt_chars": sum(len(message.get("content", "")) for message in messages),
        }
        if self.capture_llm_io:
            payload["messages"] = messages
            payload["raw_response"] = raw_response
        elif raw_response is not None:
            payload["response_chars"] = len(raw_response)
        self.record("llm_call", payload)

    def record_parse_error(self, *, step_number: int, raw_response: str, error: str) -> None:
        payload: Dict[str, Any] = {
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

    def record_replan(self, *, reason: str, steps: Iterable[Any]) -> None:
        plan = []
        for step in steps:
            plan.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "action": getattr(step, "action", None),
                    "reason": getattr(step, "reason", None),
                }
            )
        self.record("replan", {"reason": reason, "steps": plan})

    def record(self, event: str, payload: Dict[str, Any]) -> None:
        self.open()
        assert self._handle is not None
        envelope = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            "payload": _sanitize(payload),
        }
        self._handle.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
        self._handle.flush()


def load_trace_events(path: str | Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


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
