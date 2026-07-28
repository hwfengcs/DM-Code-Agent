"""Critic 完成门禁：以 ``before_finish`` 钩子实现的内置扩展。

迁移前这段逻辑是 ``ReactAgent._review_completion`` / ``_format_critic_observation``
/ ``_critic_review_trace_payload`` 三个私有方法，由 ``--enable-critic`` 通过构造函数
的 ``critic=`` 参数打开。现在它只是一个注册在 ``before_finish`` 上的处理器，内核
不再知道 Critic 的存在。

刻意保留的一点：Critic 自身抛异常时**不能**让事件总线的异常隔离兜底——总线会跳过
失败的处理器并放行完成，而迁移前的语义是「审查失败即否决」。所以异常在本模块内
捕获并转成 block 结果。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dm_agent.core.capabilities import CapabilityContext
from dm_agent.core.events import BeforeFinishEvent

if TYPE_CHECKING:
    from dm_agent.core.critic import CriticAgent, CriticReview


class CriticGate:
    """在 ``finish`` / ``task_complete`` 被接受前跑一次 Critic 审查。"""

    def __init__(self, critic: CriticAgent) -> None:
        self.critic = critic
        self.trace_writer: Any | None = None

    def install(self, context: CapabilityContext) -> None:
        # 走 phase 包装客户端，Critic 的请求同样经过 before_llm_request 钩子。
        self.critic.client = context.client_for("critic")
        self.trace_writer = context.trace_writer
        context.event_bus.on("before_finish", self.before_finish, name="builtin.critic_gate")

    def before_finish(self, event: BeforeFinishEvent) -> dict[str, Any] | None:
        metadata = event.metadata
        try:
            review = self.critic.review(
                task=event.task,
                candidate_answer=event.completion_text,
                metadata=metadata,
                steps=event.steps,
                failure_feedback=metadata.get("failure_reason", ""),
            )
        except Exception as exc:
            metadata["critic_error"] = str(exc)
            failure_observation = f"Critic review failed: {exc}"
            if self.trace_writer:
                self.trace_writer.record_critic_review(
                    step_number=event.step_number,
                    review={
                        "action": event.action,
                        "passed": False,
                        "score": 0.0,
                        "summary": failure_observation,
                        "reasons": [str(exc)],
                        "suggested_fixes": [],
                        "error": type(exc).__name__,
                    },
                )
            return {"block": True, "reason": failure_observation}

        metadata["critic_review_count"] = int(metadata.get("critic_review_count", 0)) + 1
        metadata["critic_last_score"] = review.score
        metadata["critic_last_passed"] = review.passed
        if review.passed:
            metadata["critic_pass_count"] = int(metadata.get("critic_pass_count", 0)) + 1
        else:
            metadata["critic_fail_count"] = int(metadata.get("critic_fail_count", 0)) + 1
            metadata["critic_reject_count"] = int(metadata.get("critic_reject_count", 0)) + 1
            metadata["failure_reason"] = review.summary or (
                review.reasons[0] if review.reasons else "Critic rejected completion"
            )

        if self.trace_writer:
            self.trace_writer.record_critic_review(
                step_number=event.step_number,
                review=self._trace_payload(review, action=event.action),
            )

        if review.passed:
            return None
        return {
            "block": True,
            "reason": _format_critic_observation(review, event.completion_text),
        }

    def _trace_payload(self, review: CriticReview, *, action: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "passed": review.passed,
            "score": review.score,
            "summary": review.summary,
            "reasons": list(review.reasons),
            "suggested_fixes": list(review.suggested_fixes),
            "action": action,
        }
        if self.trace_writer and getattr(self.trace_writer, "capture_llm_io", False):
            payload["raw"] = review.raw
            payload["metadata"] = review.metadata
        return payload


def _format_critic_observation(review: CriticReview, completion_text: str) -> str:
    details = []
    if review.summary:
        details.append(review.summary)
    if review.reasons:
        details.append("Reasons: " + "; ".join(review.reasons))
    if review.suggested_fixes:
        details.append("Fixes: " + "; ".join(review.suggested_fixes))
    details.append(f"Candidate completion: {completion_text}")
    return "Critic rejected completion.\n" + "\n".join(details)
