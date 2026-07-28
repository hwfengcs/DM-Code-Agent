"""Reflexion 多 trial：以 ``on_run_start`` + ``on_run_end`` 实现的内置扩展。

迁移前这是 ``ReactAgent._run_with_reflexion`` / ``_reflect_after_failed_trial`` /
``_fallback_lesson`` / ``_trial_summary`` 四个方法，外加 ``run()`` 里的一个分支：
Reflexion 开启时整个 run 被包成多次 trial，失败后反思出一条经验再重跑。

搬出来之后，"重跑" 变成了 ``on_run_end`` 返回 ``{"retry": True}``，"把经验带进下一轮"
变成了 ``on_run_start`` 返回 prompt 追加内容。内核只剩一个通用的 attempt 循环。

经验记忆（``EpisodicMemory``）仍然挂在 ``ReactAgent.reflexion_memory`` 上：它是需要
随 checkpoint 存取、随 ``--reflexion-memory-file`` 落盘的**状态**，不是行为分支。
本扩展与 Agent 共享同一个实例。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dm_agent.core.capabilities import CapabilityContext
from dm_agent.core.events import RunEndEvent, RunStartEvent

if TYPE_CHECKING:
    from dm_agent.core.reflexion import EpisodicMemory, Reflector


class ReflexionLoop:
    """失败后反思出一条经验，带着它重跑，直到成功或用完 trial 预算。"""

    def __init__(
        self,
        *,
        memory: EpisodicMemory,
        max_trials: int = 3,
        reflector: Reflector | None = None,
    ) -> None:
        if max_trials < 1:
            raise ValueError("max_trials must be at least 1.")
        self.memory = memory
        self.max_trials = max_trials
        self.reflector = reflector
        self.trace_writer: Any | None = None
        self._trial_summaries: list[dict[str, Any]] = []

    def install(self, context: CapabilityContext) -> None:
        from dm_agent.core.reflexion import Reflector

        client = context.client_for("reflexion")
        if self.reflector is None:
            self.reflector = Reflector(client)
        else:
            # 注入的 Reflector 也要接到 phase 包装客户端上，保持钩子覆盖。
            self.reflector.client = client
        self.trace_writer = context.trace_writer
        context.event_bus.on("on_run_start", self.on_run_start, name="builtin.reflexion_trial")
        context.event_bus.on("on_run_end", self.on_run_end, name="builtin.reflexion_reflect")

    def on_run_start(self, event: RunStartEvent) -> str:
        if event.attempt == 1:
            self._trial_summaries = []
        event.metadata["reflexion_enabled"] = True
        event.metadata["max_trials"] = self.max_trials
        event.metadata["reflexion_lesson_count"] = len(self.memory)
        lesson_prompt = self.memory.render_for_prompt()
        if self.trace_writer:
            self.trace_writer.record(
                "trial_start",
                {
                    "trial": event.attempt,
                    "max_trials": self.max_trials,
                    "lesson_count": len(self.memory),
                },
            )
        if not lesson_prompt:
            return event.prompt_suffix
        if not event.prompt_suffix:
            return lesson_prompt
        return event.prompt_suffix + "\n\n" + lesson_prompt

    def on_run_end(self, event: RunEndEvent) -> dict[str, Any] | None:
        metadata = event.metadata
        summary = _trial_summary(event.result, event.attempt)
        self._trial_summaries.append(summary)
        metadata["trials"] = list(self._trial_summaries)
        metadata["trial_count"] = event.attempt
        metadata["reflexion_lesson_count"] = len(self.memory)

        if self.trace_writer:
            self.trace_writer.record("trial_end", summary)

        if metadata.get("status") == "success" or event.attempt >= self.max_trials:
            return None

        lesson = self._reflect(event.task, event.result, event.attempt)
        self.memory.add(
            lesson,
            source="agent_failure",
            metadata={
                "trial": event.attempt,
                "status": metadata.get("status"),
                "failure_reason": metadata.get("failure_reason", ""),
            },
        )
        metadata["reflexion_lesson_count"] = len(self.memory)
        if self.trace_writer:
            self.trace_writer.record(
                "reflexion",
                {
                    "trial": event.attempt,
                    "lesson": lesson,
                    "lesson_count": len(self.memory),
                },
            )
        return {"retry": True}

    def _reflect(
        self,
        task: str,
        result: dict[str, Any],
        trial: int,
        *,
        failure_feedback: str | None = None,
    ) -> str:
        metadata = result.get("metadata", {})
        if self.reflector is None:
            return _fallback_lesson(metadata)
        try:
            return self.reflector.reflect(
                task=task,
                final_answer=str(result.get("final_answer", "")),
                metadata=metadata,
                steps=result.get("steps", []),
                failure_feedback=failure_feedback,
            )
        except Exception as exc:
            metadata["reflexion_error"] = f"trial {trial}: {exc}"
            return _fallback_lesson(metadata)


def _fallback_lesson(metadata: dict[str, Any]) -> str:
    reason = metadata.get("failure_reason") or metadata.get("status") or "unknown failure"
    return (
        f"Previous trial failed with {reason}. Inspect the concrete failure signal first, "
        "then make a smaller targeted change before finishing."
    )


def _trial_summary(result: dict[str, Any], trial: int) -> dict[str, Any]:
    metadata = result.get("metadata", {})
    return {
        "trial": trial,
        "status": metadata.get("status"),
        "failure_reason": metadata.get("failure_reason", ""),
        "steps": len(result.get("steps", [])),
        "final_answer_chars": len(str(result.get("final_answer", ""))),
    }
