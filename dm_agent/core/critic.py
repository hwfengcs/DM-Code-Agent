"""Critic helpers for opt-in peer review of agent outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ..clients.base_client import BaseLLMClient


@dataclass(frozen=True)
class CriticReview:
    """Structured result of a critic pass."""

    passed: bool
    score: float
    summary: str
    reasons: List[str] = field(default_factory=list)
    suggested_fixes: List[str] = field(default_factory=list)
    raw: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "summary": self.summary,
            "reasons": list(self.reasons),
            "suggested_fixes": list(self.suggested_fixes),
            "raw": self.raw,
            "metadata": self.metadata,
        }


class CriticAgent:
    """LLM-backed reviewer for agent outputs and completion candidates."""

    def __init__(
        self,
        client: BaseLLMClient,
        *,
        temperature: float = 0.0,
        max_step_chars: int = 4000,
        max_candidate_chars: int = 4000,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_step_chars = max_step_chars
        self.max_candidate_chars = max_candidate_chars

    def review(
        self,
        *,
        task: str,
        candidate_answer: Any = None,
        final_answer: Any = None,
        steps: Iterable[Dict[str, Any]] = (),
        metadata: Optional[Dict[str, Any]] = None,
        failure_feedback: Optional[str] = None,
    ) -> CriticReview:
        """Return a structured verdict for a candidate completion."""
        if candidate_answer is None:
            candidate_answer = final_answer
        metadata = metadata or {}
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict code-review critic for a code agent. "
                    "Judge whether the candidate should be accepted. "
                    "Return JSON only with keys passed, score, summary, reasons, and suggested_fixes."
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(
                    task=task,
                    candidate_answer=candidate_answer,
                    steps=steps,
                    metadata=metadata,
                    failure_feedback=failure_feedback,
                ),
            },
        ]
        raw = self.client.respond(messages, temperature=self.temperature)
        return self._parse_review(raw)

    def _build_prompt(
        self,
        *,
        task: str,
        candidate_answer: Any,
        steps: Iterable[Dict[str, Any]],
        metadata: Dict[str, Any],
        failure_feedback: Optional[str],
    ) -> str:
        payload = {
            "task": task[:3000],
            "candidate_answer": _json_safe(candidate_answer, max_chars=self.max_candidate_chars),
            "metadata": _safe_metadata(metadata),
            "failure_feedback": (failure_feedback or "")[:3000],
            "recent_steps": _summarize_steps(steps, limit=self.max_step_chars),
        }
        return (
            "Review the candidate completion for correctness, safety, and whether it actually "
            "solves the task.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "Return JSON like:\n"
            '{\n  "passed": true,\n  "score": 8.5,\n  "summary": "short verdict",\n'
            '  "reasons": ["..."],\n  "suggested_fixes": ["..."]\n}'
        )

    def _parse_review(self, raw: str) -> CriticReview:
        parsed = self._load_json(raw)
        if not isinstance(parsed, dict):
            text = " ".join(raw.strip().split())
            if not text:
                text = "Critic review was empty."
            return CriticReview(
                passed=False,
                score=0.0,
                summary=text,
                reasons=[text],
                suggested_fixes=[],
                raw=raw,
            )

        passed = bool(parsed.get("passed", False))
        score_value = parsed.get("score")
        try:
            score = float(score_value) if score_value is not None else (10.0 if passed else 0.0)
        except (TypeError, ValueError):
            score = 10.0 if passed else 0.0
        reasons = _normalize_list(parsed.get("reasons"))
        suggested_fixes = _normalize_list(parsed.get("suggested_fixes"))
        summary = str(
            parsed.get("summary") or " ".join(reasons) or ("Accepted" if passed else "Rejected")
        )
        return CriticReview(
            passed=passed,
            score=score,
            summary=summary.strip(),
            reasons=reasons,
            suggested_fixes=suggested_fixes,
            raw=raw,
            metadata={
                key: parsed.get(key)
                for key in ("confidence", "severity", "verdict")
                if key in parsed
            },
        )

    @staticmethod
    def _load_json(raw: str) -> Any:
        candidate = raw.strip()
        if not candidate:
            return None

        for snippet in _json_candidates(candidate):
            parsed = _parse_json(snippet)
            if parsed is not None:
                return parsed
        return None


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        items = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    return [text] if text else []


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
        "reflexion_lesson_count",
        "rag_retrieval_count",
        "critic_review_count",
        "critic_reject_count",
        "critic_pass_count",
    }
    return {key: metadata.get(key) for key in sorted(allowed) if key in metadata}


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


def _json_safe(value: Any, *, max_chars: int) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item, max_chars=max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item, max_chars=max_chars) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item, max_chars=max_chars) for item in value]
    if isinstance(value, str):
        return value[:max_chars]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)[:max_chars]


def _json_candidates(candidate: str) -> List[str]:
    candidates = [candidate]

    fence_match = _extract_fence(candidate)
    if fence_match:
        candidates.append(fence_match)

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(candidate[start : end + 1])

    repaired_candidates = []
    for item in candidates:
        repaired = _repair_json_text(item)
        if repaired != item:
            repaired_candidates.append(repaired)

    return candidates + repaired_candidates


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import ast

            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
        return parsed


def _extract_fence(candidate: str) -> str:
    import re

    fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return ""


def _repair_json_text(text: str) -> str:
    import re

    text = text.strip()
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text
