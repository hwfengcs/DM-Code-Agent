"""Self-consistency runner for choosing the best of several independent runs."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from .critic import CriticAgent, CriticReview

TrialRunner = Callable[[int, str], Dict[str, Any]]
VisibleTest = Callable[[Dict[str, Any]], float | int | bool]


@dataclass(frozen=True)
class SelfConsistencyCandidate:
    """A single candidate result from one independent run."""

    run_index: int
    result: Dict[str, Any]
    vote_key: str
    score: float
    passed: bool
    critic_review: Optional[CriticReview] = None
    note: str = ""

    def summary(self) -> Dict[str, Any]:
        metadata = self.result.get("metadata", {}) if isinstance(self.result, dict) else {}
        return {
            "run_index": self.run_index,
            "vote_key": self.vote_key,
            "score": self.score,
            "passed": self.passed,
            "status": metadata.get("status"),
            "failure_reason": metadata.get("failure_reason", ""),
            "steps": len(self.result.get("steps", [])) if isinstance(self.result, dict) else 0,
            "final_answer": (
                self.result.get("final_answer", "") if isinstance(self.result, dict) else ""
            ),
            "note": self.note,
            "critic_review": self.critic_review.to_dict() if self.critic_review else None,
        }


@dataclass(frozen=True)
class SelfConsistencyResult:
    """Selection summary for a self-consistency run."""

    strategy: str
    selected_index: int
    candidates: List[SelfConsistencyCandidate] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "selected_index": self.selected_index,
            "candidates": [candidate.summary() for candidate in self.candidates],
        }


class SelfConsistencyRunner:
    """Run the same task multiple times and choose the best candidate."""

    def __init__(
        self,
        trial_runner: TrialRunner,
        *,
        num_runs: int = 3,
        strategy: str = "majority_vote",
        critic: Optional[CriticAgent] = None,
        visible_test: Optional[VisibleTest] = None,
    ) -> None:
        if num_runs < 1:
            raise ValueError("num_runs must be at least 1")
        if strategy not in {"majority_vote", "critic_score", "test_pass"}:
            raise ValueError("strategy must be one of: majority_vote, critic_score, test_pass")
        if strategy == "critic_score" and critic is None:
            raise ValueError("critic_score strategy requires a critic")
        if strategy == "test_pass" and visible_test is None:
            raise ValueError("test_pass strategy requires a visible_test callback")

        self.trial_runner = trial_runner
        self.num_runs = num_runs
        self.strategy = strategy
        self.critic = critic
        self.visible_test = visible_test

    def run(self, task: str, **trial_kwargs: Any) -> Dict[str, Any]:
        """Execute several independent runs and return the selected result."""
        candidates = self.run_candidates(task, **trial_kwargs)
        selected = self._select_candidate(candidates)
        result = deepcopy(selected.result)
        metadata = result.setdefault("metadata", {})
        metadata["self_consistency"] = SelfConsistencyResult(
            strategy=self.strategy,
            selected_index=selected.run_index,
            candidates=candidates,
        ).to_dict()
        return result

    def run_candidates(self, task: str, **trial_kwargs: Any) -> List[SelfConsistencyCandidate]:
        """Run all candidates and return their scored summaries."""
        candidates: List[SelfConsistencyCandidate] = []
        for run_index in range(1, self.num_runs + 1):
            result = self._run_trial(run_index, task, **trial_kwargs)
            candidates.append(self._build_candidate(run_index, task, result, **trial_kwargs))
        return candidates

    def _run_trial(self, run_index: int, task: str, **trial_kwargs: Any) -> Dict[str, Any]:
        try:
            result = self.trial_runner(run_index, task, **trial_kwargs)
        except Exception as exc:  # noqa: BLE001 - one failed trial should not abort selection
            return {
                "final_answer": "",
                "steps": [],
                "metadata": {
                    "status": "exception",
                    "failure_reason": str(exc),
                    "self_consistency_error": type(exc).__name__,
                },
            }
        if not isinstance(result, dict):
            return {
                "final_answer": str(result),
                "steps": [],
                "metadata": {
                    "status": "success",
                    "failure_reason": "",
                    "self_consistency_note": "Non-dict result coerced to string.",
                },
            }
        result.setdefault("metadata", {})
        return result

    def _build_candidate(
        self,
        run_index: int,
        task: str,
        result: Dict[str, Any],
        **trial_kwargs: Any,
    ) -> SelfConsistencyCandidate:
        if self.strategy == "critic_score":
            review = self.critic.review(
                task=task,
                candidate_answer=str(result.get("final_answer", "")),
                metadata=result.get("metadata", {}),
                steps=result.get("steps", []),
                failure_feedback=result.get("metadata", {}).get("failure_reason", ""),
            )
            score = review.score
            passed = review.passed
            vote_key = str(result.get("final_answer", "")).strip()
            note = review.summary
            result.setdefault("metadata", {})["critic_review"] = review.to_dict()
            result["metadata"]["critic_score"] = review.score
            result["metadata"]["critic_passed"] = review.passed
            return SelfConsistencyCandidate(
                run_index=run_index,
                result=result,
                vote_key=vote_key,
                score=score,
                passed=passed,
                critic_review=review,
                note=note,
            )

        if self.strategy == "test_pass":
            assert self.visible_test is not None
            test_score = self.visible_test(result)
            score = _coerce_score(test_score)
            passed = score >= 0.5
            vote_key = str(result.get("final_answer", "")).strip()
            note = "visible test passed" if passed else "visible test failed"
            result.setdefault("metadata", {})["visible_test_score"] = score
            result["metadata"]["visible_test_passed"] = passed
            return SelfConsistencyCandidate(
                run_index=run_index,
                result=result,
                vote_key=vote_key,
                score=score,
                passed=passed,
                note=note,
            )

        vote_key = _normalise_vote_key(result)
        score = 1.0 if _is_success(result) else 0.0
        return SelfConsistencyCandidate(
            run_index=run_index,
            result=result,
            vote_key=vote_key,
            score=score,
            passed=_is_success(result),
            note="majority_vote",
        )

    def _select_candidate(
        self, candidates: List[SelfConsistencyCandidate]
    ) -> SelfConsistencyCandidate:
        if not candidates:
            raise ValueError("No candidates were produced.")

        if self.strategy == "majority_vote":
            grouped: Dict[str, List[SelfConsistencyCandidate]] = defaultdict(list)
            for candidate in candidates:
                grouped[candidate.vote_key].append(candidate)
            ranked_groups = sorted(
                grouped.items(),
                key=lambda item: (
                    len(item[1]),
                    _mean(candidate.score for candidate in item[1]),
                    max(1 if candidate.passed else 0 for candidate in item[1]),
                    -min(candidate.run_index for candidate in item[1]),
                ),
                reverse=True,
            )
            best_group = ranked_groups[0][1]
            return max(
                best_group,
                key=lambda candidate: (candidate.score, candidate.passed, -candidate.run_index),
            )

        return max(
            candidates,
            key=lambda candidate: (candidate.score, candidate.passed, -candidate.run_index),
        )


def _normalise_vote_key(result: Dict[str, Any]) -> str:
    answer = str(result.get("final_answer", "")).strip()
    if answer:
        return answer
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and metadata.get("prediction"):
        return str(metadata["prediction"]).strip()
    return ""


def _is_success(result: Dict[str, Any]) -> bool:
    metadata = result.get("metadata", {})
    return isinstance(metadata, dict) and metadata.get("status") == "success"


def _coerce_score(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score > 1.0:
        if score <= 10.0:
            score = score / 10.0
        else:
            score = 1.0
    return max(0.0, min(score, 1.0))


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0
