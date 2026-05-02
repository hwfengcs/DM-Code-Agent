"""Real-model evaluation runner for DM-Code-Agent."""

from __future__ import annotations

import os
import tempfile
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.core import ReactAgent
from dm_agent.skills import SkillManager
from dm_agent.tools import default_tools

from .models import EvalExpected, EvalResult, EvalTask
from .runner import (
    EvalVariant,
    _validate,
    _write_setup_files,
    chdir,
    summarize_results,
)

REAL_DEFAULT_VARIANTS: List[EvalVariant] = [
    EvalVariant("full", True, True, True),
    EvalVariant("no_planning", False, True, True),
    EvalVariant("no_skills", True, False, True),
]


PROVIDER_API_KEY_ENV = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@dataclass(frozen=True)
class RealEvalConfig:
    provider: str = "deepseek"
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    timeout: int = 120
    temperature: float = 0.0
    repeat: int = 1
    cost_per_1k_tokens: float = 0.0
    quiet: bool = True


@dataclass
class UsageTotals:
    request_count: int = 0
    prompt_chars: int = 0
    completion_chars: int = 0
    estimated_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class UsageTrackingClient:
    """Wrap a provider client and collect usage without changing agent code."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.model = client.model
        self.base_url = client.base_url
        self.timeout = client.timeout
        self.usage = UsageTotals()

    def complete(self, messages: List[Dict[str, str]], **extra: Any) -> Dict[str, Any]:
        return self.client.complete(messages, **extra)

    def extract_text(self, data: Dict[str, Any]) -> str:
        return self.client.extract_text(data)

    def respond(self, messages: List[Dict[str, str]], **extra: Any) -> str:
        self.usage.request_count += 1
        self.usage.prompt_chars += sum(len(message.get("content", "")) for message in messages)

        data = self.complete(messages, **extra)
        text = self.extract_text(data)

        self.usage.completion_chars += len(text)
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            self.usage.prompt_tokens += _int_value(usage.get("prompt_tokens"))
            self.usage.completion_tokens += _int_value(usage.get("completion_tokens"))
            self.usage.total_tokens += _int_value(usage.get("total_tokens"))

        approx_tokens = (self.usage.prompt_chars + self.usage.completion_chars + 3) // 4
        self.usage.estimated_tokens = self.usage.total_tokens or approx_tokens
        return text


def get_real_tasks() -> List[EvalTask]:
    """Return live-model tasks with explicit prompts and deterministic validators."""

    return [
        EvalTask(
            task_id="real_direct_finish",
            name="Real direct final answer",
            prompt=(
                "Do not use tools. Finish immediately. The final answer must contain "
                "the exact token benchmark-ready."
            ),
            planner_response=None,
            agent_responses=[],
            expected=EvalExpected(final_answer_contains=["benchmark-ready"]),
            max_steps=4,
            tags=["real", "control"],
        ),
        EvalTask(
            task_id="real_create_file",
            name="Real create file",
            prompt=(
                "Create a file named notes.md in the current working directory. "
                "Its content must be exactly: agent eval ready\\n. "
                "Then finish with a message that mentions notes.md."
            ),
            planner_response=None,
            agent_responses=[],
            expected=EvalExpected(
                required_actions=["create_file"],
                final_answer_contains=["notes.md"],
                workspace_files={"notes.md": "agent eval ready"},
            ),
            max_steps=6,
            tags=["real", "tool-use", "file"],
        ),
        EvalTask(
            task_id="real_read_file",
            name="Real read file",
            prompt=(
                "Read input.txt and finish with the secret color. "
                "The final answer must include the word blue."
            ),
            planner_response=None,
            agent_responses=[],
            setup_files={"input.txt": "secret color: blue\n"},
            expected=EvalExpected(
                required_actions=["read_file"],
                final_answer_contains=["blue"],
            ),
            max_steps=6,
            tags=["real", "tool-use", "file"],
        ),
        EvalTask(
            task_id="real_search_todo",
            name="Real search TODO",
            prompt=(
                "Use search_in_file to find TODO markers in app.py. "
                "Finish with a short answer that includes TODO."
            ),
            planner_response=None,
            agent_responses=[],
            setup_files={"app.py": "def run():\n    pass\n# TODO: add tests\n"},
            expected=EvalExpected(
                required_actions=["search_in_file"],
                final_answer_contains=["todo"],
            ),
            max_steps=6,
            tags=["real", "tool-use", "search"],
        ),
        EvalTask(
            task_id="real_run_python",
            name="Real run Python",
            prompt=(
                "Use run_python to calculate 6 * 7. " "Finish with an answer that includes 42."
            ),
            planner_response=None,
            agent_responses=[],
            expected=EvalExpected(
                required_actions=["run_python"],
                final_answer_contains=["42"],
            ),
            max_steps=6,
            tags=["real", "tool-use", "execution"],
        ),
        EvalTask(
            task_id="real_code_metrics",
            name="Real code metrics",
            prompt=(
                "Use get_code_metrics on calc.py and finish with a concise summary. "
                "The final answer must mention class."
            ),
            planner_response=None,
            agent_responses=[],
            setup_files={
                "calc.py": (
                    "class Calculator:\n"
                    "    def add(self, left: int, right: int) -> int:\n"
                    "        return left + right\n\n"
                    "def mul(left: int, right: int) -> int:\n"
                    "    return left * right\n"
                )
            },
            expected=EvalExpected(
                required_actions=["get_code_metrics"],
                final_answer_contains_any=[["class", "类"]],
            ),
            max_steps=6,
            tags=["real", "code-analysis"],
        ),
        EvalTask(
            task_id="real_tool_failure_recovery",
            name="Real missing-file recovery",
            prompt=(
                "First try to read missing.txt. If it is missing, recover by creating "
                "recovered.txt with exactly this content: recovered after failure\\n. "
                "Then finish with a message that includes recovered."
            ),
            planner_response=None,
            agent_responses=[],
            expected=EvalExpected(
                required_actions=["read_file", "create_file"],
                final_answer_contains=["recovered"],
                workspace_files={"recovered.txt": "recovered after failure"},
            ),
            max_steps=8,
            tags=["real", "recovery"],
        ),
    ]


def run_real_suite(
    *,
    tasks: Optional[Sequence[EvalTask]] = None,
    variants: Optional[Sequence[EvalVariant]] = None,
    task_ids: Optional[Iterable[str]] = None,
    variant_names: Optional[Iterable[str]] = None,
    config: Optional[RealEvalConfig] = None,
) -> Dict[str, Any]:
    config = config or RealEvalConfig()
    selected_tasks = list(tasks or get_real_tasks())
    selected_variants = list(variants or REAL_DEFAULT_VARIANTS)

    if task_ids:
        allowed_tasks = set(task_ids)
        selected_tasks = [task for task in selected_tasks if task.task_id in allowed_tasks]

    if variant_names:
        allowed_variants = set(variant_names)
        selected_variants = [
            variant for variant in selected_variants if variant.name in allowed_variants
        ]

    if config.repeat < 1:
        raise ValueError("repeat must be at least 1")

    results: List[EvalResult] = []
    for repeat_index in range(config.repeat):
        for variant in selected_variants:
            for task in selected_tasks:
                results.append(run_real_task(task, variant, config, repeat_index=repeat_index))

    provider = config.provider.lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    return {
        "mode": "real",
        "provider": provider,
        "model": config.model or defaults.get("model"),
        "base_url": config.base_url or defaults.get("base_url"),
        "repeat": config.repeat,
        "summary": summarize_results(results),
        "results": [result.to_dict() for result in results],
        "tasks": [task.to_public_dict() for task in selected_tasks],
        "variants": [variant.__dict__ for variant in selected_variants],
    }


def run_real_task(
    task: EvalTask,
    variant: EvalVariant,
    config: RealEvalConfig,
    *,
    repeat_index: int = 0,
) -> EvalResult:
    client = _build_tracking_client(config)

    with tempfile.TemporaryDirectory(prefix=f"dm-agent-real-eval-{task.task_id}-") as tmp:
        workspace = Path(tmp)
        _write_setup_files(workspace, task.setup_files)

        skill_manager = None
        if variant.enable_skills:
            skill_manager = SkillManager()
            skill_manager.load_all()

        agent = ReactAgent(
            client,
            default_tools(include_mcp=False),
            max_steps=task.max_steps,
            temperature=config.temperature,
            enable_planning=variant.enable_planning,
            enable_compression=variant.enable_compression,
            skill_manager=skill_manager,
        )

        with chdir(workspace):
            try:
                if config.quiet:
                    with redirect_stdout(StringIO()):
                        raw_result = agent.run(task.prompt)
                else:
                    raw_result = agent.run(task.prompt)
            except Exception as exc:  # noqa: BLE001
                raw_result = {
                    "final_answer": "",
                    "steps": [],
                    "metadata": {
                        "status": "exception",
                        "failure_reason": str(exc),
                        "duration_seconds": 0.0,
                    },
                }

        success, failure_reason = _validate(task, raw_result, workspace)

    steps = raw_result.get("steps", [])
    actions = [step.get("action", "") for step in steps]
    metadata = raw_result.get("metadata", {})
    metadata.update(
        {
            "mode": "real",
            "provider": config.provider.lower(),
            "model": client.model,
            "request_count": client.usage.request_count,
            "prompt_tokens": client.usage.prompt_tokens,
            "completion_tokens": client.usage.completion_tokens,
            "total_tokens": client.usage.total_tokens,
            "repeat_index": repeat_index,
        }
    )

    estimated_cost = client.usage.estimated_tokens / 1000 * config.cost_per_1k_tokens

    return EvalResult(
        task_id=task.task_id,
        task_name=task.name,
        variant=variant.name,
        success=success,
        final_answer=raw_result.get("final_answer", ""),
        failure_reason=failure_reason,
        actions=actions,
        steps_count=len(steps),
        tool_calls=sum(1 for action in actions if action not in {"finish", "error"}),
        duration_seconds=float(metadata.get("duration_seconds", 0.0)),
        prompt_chars=client.usage.prompt_chars,
        completion_chars=client.usage.completion_chars,
        estimated_tokens=client.usage.estimated_tokens,
        estimated_cost_usd=estimated_cost,
        metadata=metadata,
    )


def _build_tracking_client(config: RealEvalConfig) -> UsageTrackingClient:
    provider = config.provider.lower()
    env_name = config.api_key_env or PROVIDER_API_KEY_ENV.get(provider)
    if not env_name:
        raise ValueError(f"No default API key environment variable for provider: {provider}")

    api_key = os.environ.get(env_name)
    if not api_key:
        raise ValueError(f"Missing API key. Set {env_name} before running real evals.")

    defaults = PROVIDER_DEFAULTS.get(provider, {})
    client = create_llm_client(
        provider=provider,
        api_key=api_key,
        model=config.model or defaults.get("model"),
        base_url=config.base_url or defaults.get("base_url"),
        timeout=config.timeout,
    )
    return UsageTrackingClient(client)


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0
