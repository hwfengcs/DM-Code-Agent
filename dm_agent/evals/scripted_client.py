"""Scripted LLM client used by no-key deterministic evals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ScriptedUsage:
    calls: int = 0
    prompt_chars: int = 0
    completion_chars: int = 0

    @property
    def estimated_tokens(self) -> int:
        return max(1, (self.prompt_chars + self.completion_chars + 3) // 4)


class ScriptedLLMClient:
    """A tiny client with the same `respond` surface used by ReactAgent."""

    def __init__(self, responses: List[str], *, model: str = "scripted-eval") -> None:
        self.responses = list(responses)
        self.model = model
        self.usage = ScriptedUsage()
        self.requests: List[List[Dict[str, str]]] = []

    def respond(self, messages: List[Dict[str, str]], **extra) -> str:  # noqa: ARG002
        self.requests.append(messages)
        self.usage.calls += 1
        self.usage.prompt_chars += sum(len(message.get("content", "")) for message in messages)

        if not self.responses:
            raise AssertionError("ScriptedLLMClient ran out of responses")

        response = self.responses.pop(0)
        self.usage.completion_chars += len(response)
        return response
