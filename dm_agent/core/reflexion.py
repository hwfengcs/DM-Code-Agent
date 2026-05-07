"""Reflexion helpers for retrying failed agent trials.

The implementation is intentionally prompt-based and small: failed trials are
summarized into lessons, lessons are kept in an episodic memory, and the next
trial receives those lessons as additional context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ..clients.base_client import BaseLLMClient


@dataclass(frozen=True)
class Lesson:
    """One reusable lesson learned from a failed trial."""

    text: str
    source: str = "agent_failure"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lesson":
        return cls(
            text=str(data.get("text", "")),
            source=str(data.get("source", "agent_failure")),
            metadata=dict(data.get("metadata", {})),
        )


class EpisodicMemory:
    """Bounded memory of lessons from previous failed trials."""

    def __init__(self, lessons: Optional[Iterable[Lesson | str]] = None, *, max_lessons: int = 5):
        if max_lessons < 1:
            raise ValueError("max_lessons must be at least 1")
        self.max_lessons = max_lessons
        self.lessons: List[Lesson] = []
        for item in lessons or []:
            if isinstance(item, Lesson):
                self.add(item.text, source=item.source, metadata=item.metadata)
            else:
                self.add(str(item))

    def __len__(self) -> int:
        return len(self.lessons)

    def add(
        self,
        lesson: str,
        *,
        source: str = "agent_failure",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        text = " ".join(lesson.strip().split())
        if not text:
            return
        self.lessons.append(Lesson(text=text, source=source, metadata=metadata or {}))
        if len(self.lessons) > self.max_lessons:
            self.lessons = self.lessons[-self.max_lessons :]

    def clear(self) -> None:
        self.lessons = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_lessons": self.max_lessons,
            "lessons": [lesson.to_dict() for lesson in self.lessons],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EpisodicMemory":
        return cls(
            [Lesson.from_dict(item) for item in data.get("lessons", [])],
            max_lessons=int(data.get("max_lessons", 5)),
        )

    def render_for_prompt(self) -> str:
        """Return a prompt block suitable for injecting into the next trial."""
        if not self.lessons:
            return ""
        lines = [
            "<reflexion_memory>",
            "Use these lessons from previous failed attempts. Avoid repeating the same mistake.",
        ]
        for index, lesson in enumerate(self.lessons, start=1):
            lines.append(f"{index}. {lesson.text}")
        lines.append("</reflexion_memory>")
        return "\n".join(lines)


class Reflector:
    """LLM-backed reflection generator."""

    def __init__(
        self,
        client: BaseLLMClient,
        *,
        temperature: float = 0.0,
        max_step_chars: int = 4000,
        max_lesson_chars: int = 1200,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_step_chars = max_step_chars
        self.max_lesson_chars = max_lesson_chars

    def reflect(
        self,
        *,
        task: str,
        final_answer: str,
        metadata: Dict[str, Any],
        steps: Iterable[Dict[str, Any]],
        failure_feedback: Optional[str] = None,
    ) -> str:
        """Generate a concise lesson for the next trial."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a code-agent Reflexion module. Given a failed trial, "
                    "write one concise lesson for the next attempt. Focus on what "
                    "went wrong and what to do differently. Do not solve the whole "
                    "task; produce an actionable memory item."
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(
                    task=task,
                    final_answer=final_answer,
                    metadata=metadata,
                    steps=steps,
                    failure_feedback=failure_feedback,
                ),
            },
        ]
        raw = self.client.respond(messages, temperature=self.temperature)
        return self._normalize_lesson(raw)

    def _build_prompt(
        self,
        *,
        task: str,
        final_answer: str,
        metadata: Dict[str, Any],
        steps: Iterable[Dict[str, Any]],
        failure_feedback: Optional[str],
    ) -> str:
        step_summary = _summarize_steps(steps, limit=self.max_step_chars)
        payload = {
            "task": task[:3000],
            "final_answer": final_answer[:1000],
            "metadata": _safe_metadata(metadata),
            "failure_feedback": (failure_feedback or "")[:3000],
            "steps": step_summary,
        }
        return (
            "The previous trial failed. Return one short lesson for the next trial.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "Lesson:"
        )

    def _normalize_lesson(self, raw: str) -> str:
        text = " ".join(raw.strip().split())
        if not text:
            return "Inspect the failure signal first, then make a smaller targeted change."
        return text[: self.max_lesson_chars]


def _summarize_steps(steps: Iterable[Dict[str, Any]], *, limit: int) -> List[Dict[str, str]]:
    summary: List[Dict[str, str]] = []
    used_chars = 0
    for step in steps:
        item = {
            "thought": str(step.get("thought", ""))[:500],
            "action": str(step.get("action", ""))[:120],
            "observation": str(step.get("observation", ""))[-800:],
        }
        used_chars += sum(len(value) for value in item.values())
        summary.append(item)
        if used_chars >= limit:
            break
    return summary


def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "status",
        "failure_reason",
        "parse_error_count",
        "tool_error_count",
        "unknown_tool_count",
        "argument_error_count",
        "replan_count",
        "trial",
        "trial_count",
    }
    return {key: metadata.get(key) for key in sorted(allowed) if key in metadata}
