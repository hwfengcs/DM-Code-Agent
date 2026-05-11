import json

from dm_agent.core.critic import CriticAgent
from dm_agent.core.self_consistency import SelfConsistencyRunner


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def respond(self, messages, **extra):
        self.requests.append((messages, extra))
        if not self.responses:
            raise AssertionError("FakeRespondClient ran out of responses")
        return self.responses.pop(0)


def test_self_consistency_majority_vote_selects_most_common_answer():
    candidates = [
        {
            "final_answer": "alpha",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "beta",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "alpha",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
    ]

    runner = SelfConsistencyRunner(
        lambda run_index, task, **kwargs: candidates[run_index - 1],
        num_runs=3,
        strategy="majority_vote",
    )

    result = runner.run("choose the best answer")

    assert result["final_answer"] == "alpha"
    assert result["metadata"]["self_consistency"]["strategy"] == "majority_vote"
    assert result["metadata"]["self_consistency"]["selected_index"] == 1
    uncertainty = result["metadata"]["self_consistency"]["uncertainty"]
    assert uncertainty["vote_distribution"] == {"alpha": 2, "beta": 1}
    assert uncertainty["selected_support"] == 2
    assert uncertainty["unique_votes"] == 2
    assert uncertainty["runner_confidence"] == "medium"


def test_self_consistency_majority_vote_prefers_patch_fingerprint_when_present():
    candidates = [
        {
            "final_answer": "alpha wording",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success", "patch_fingerprint": "patch-a"},
        },
        {
            "final_answer": "beta wording",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success", "patch_fingerprint": "patch-a"},
        },
        {
            "final_answer": "gamma wording",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success", "patch_fingerprint": "patch-b"},
        },
    ]

    runner = SelfConsistencyRunner(
        lambda run_index, task, **kwargs: candidates[run_index - 1],
        num_runs=3,
        strategy="majority_vote",
    )

    result = runner.run("choose the best patch")
    metadata = result["metadata"]["self_consistency"]
    uncertainty = metadata["uncertainty"]

    assert result["final_answer"] == "alpha wording"
    assert uncertainty["vote_distribution"] == {"patch-a": 2, "patch-b": 1}
    assert uncertainty["selected_vote_key"] == "patch-a"
    assert uncertainty["selected_vote_key_source"] == "patch_fingerprint"
    assert metadata["candidates"][0]["patch_fingerprint"] == "patch-a"
    assert metadata["candidates"][0]["vote_key_source"] == "patch_fingerprint"


def test_self_consistency_majority_vote_falls_back_to_final_answer_without_patch_fingerprint():
    candidates = [
        {
            "final_answer": "alpha",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "alpha",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "beta",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
    ]

    runner = SelfConsistencyRunner(
        lambda run_index, task, **kwargs: candidates[run_index - 1],
        num_runs=3,
        strategy="majority_vote",
    )

    result = runner.run("choose the best answer")
    uncertainty = result["metadata"]["self_consistency"]["uncertainty"]

    assert uncertainty["vote_distribution"] == {"alpha": 2, "beta": 1}
    assert uncertainty["selected_vote_key"] == "alpha"
    assert uncertainty["selected_vote_key_source"] == "final_answer"


def test_self_consistency_critic_score_selects_highest_reviewed_candidate():
    client = FakeRespondClient(
        [
            json.dumps(
                {
                    "passed": False,
                    "score": 0.2,
                    "reasons": ["needs more work"],
                    "suggested_fixes": ["tighten the final check"],
                    "summary": "Not good enough.",
                }
            ),
            json.dumps(
                {
                    "passed": True,
                    "score": 0.9,
                    "reasons": [],
                    "suggested_fixes": [],
                    "summary": "Looks good.",
                }
            ),
        ]
    )
    critic = CriticAgent(client)
    candidates = [
        {
            "final_answer": "first",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "second",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
    ]

    runner = SelfConsistencyRunner(
        lambda run_index, task, **kwargs: candidates[run_index - 1],
        num_runs=2,
        strategy="critic_score",
        critic=critic,
    )

    result = runner.run("pick the stronger answer")

    assert result["final_answer"] == "second"
    assert result["metadata"]["self_consistency"]["strategy"] == "critic_score"
    assert result["metadata"]["self_consistency"]["candidates"][1]["critic_review"]["score"] == 0.9


def test_self_consistency_visible_test_selects_passing_candidate():
    candidates = [
        {
            "final_answer": "bad",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "failure"},
        },
        {
            "final_answer": "good",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
    ]

    runner = SelfConsistencyRunner(
        lambda run_index, task, **kwargs: candidates[run_index - 1],
        num_runs=2,
        strategy="test_pass",
        visible_test=lambda result: result["metadata"]["status"] == "success",
    )

    result = runner.run("choose the passing candidate")

    assert result["final_answer"] == "good"
    assert result["metadata"]["self_consistency"]["strategy"] == "test_pass"
    assert result["metadata"]["self_consistency"]["candidates"][1]["passed"] is True


def test_self_consistency_uncertainty_marks_all_different_outputs_as_low_confidence():
    candidates = [
        {
            "final_answer": "alpha",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "beta",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
        {
            "final_answer": "gamma",
            "steps": [{"action": "finish"}],
            "metadata": {"status": "success"},
        },
    ]

    runner = SelfConsistencyRunner(
        lambda run_index, task, **kwargs: candidates[run_index - 1],
        num_runs=3,
        strategy="majority_vote",
    )

    result = runner.run("choose among disagreements")
    uncertainty = result["metadata"]["self_consistency"]["uncertainty"]

    assert uncertainty["unique_votes"] == 3
    assert uncertainty["selected_support"] == 1
    assert uncertainty["tie_detected"] is True
    assert uncertainty["disagreement_reason"] == "selection_tie"
    assert uncertainty["runner_confidence"] == "low"
