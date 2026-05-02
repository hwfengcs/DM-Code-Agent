"""Built-in deterministic eval tasks."""

from __future__ import annotations

import json
from typing import List

from .models import EvalExpected, EvalTask


def agent_response(thought: str, action: str, action_input) -> str:
    return json.dumps(
        {
            "thought": thought,
            "action": action,
            "action_input": action_input,
        },
        ensure_ascii=False,
    )


def planner_response(*actions: str) -> str:
    return json.dumps(
        {
            "plan": [
                {"step": index + 1, "action": action, "reason": f"eval step {index + 1}"}
                for index, action in enumerate(actions)
            ]
        },
        ensure_ascii=False,
    )


BUILTIN_TASKS: List[EvalTask] = [
    EvalTask(
        task_id="direct_finish",
        name="Direct final answer",
        prompt="Answer directly with the benchmark keyword.",
        planner_response=planner_response("task_complete"),
        agent_responses=[
            agent_response("No tool needed.", "finish", {"answer": "benchmark-ready"})
        ],
        expected=EvalExpected(final_answer_contains=["benchmark-ready"]),
        tags=["control"],
    ),
    EvalTask(
        task_id="create_file",
        name="Create a file",
        prompt="Create notes.md with a short eval marker.",
        planner_response=planner_response("create_file", "task_complete"),
        agent_responses=[
            agent_response(
                "Write the file.",
                "create_file",
                {"path": "notes.md", "content": "agent eval ready\n"},
            ),
            agent_response("Finish.", "task_complete", {"message": "created notes.md"}),
        ],
        expected=EvalExpected(
            required_actions=["create_file", "task_complete"],
            workspace_files={"notes.md": "agent eval ready"},
        ),
        tags=["tool-use", "file"],
    ),
    EvalTask(
        task_id="read_file",
        name="Read an existing file",
        prompt="Read input.txt and answer with the color.",
        planner_response=planner_response("read_file", "finish"),
        agent_responses=[
            agent_response("Read the file.", "read_file", {"path": "input.txt"}),
            agent_response("The color is visible.", "finish", {"answer": "The color is blue."}),
        ],
        setup_files={"input.txt": "secret color: blue\n"},
        expected=EvalExpected(
            required_actions=["read_file"],
            final_answer_contains=["blue"],
        ),
        tags=["tool-use", "file"],
    ),
    EvalTask(
        task_id="search_todo",
        name="Search for TODO markers",
        prompt="Find TODO markers in app.py.",
        planner_response=planner_response("search_in_file", "finish"),
        agent_responses=[
            agent_response(
                "Search for TODO.",
                "search_in_file",
                {"path": "app.py", "pattern": "TODO", "context_lines": 1},
            ),
            agent_response("TODO was found.", "finish", "Found a TODO marker."),
        ],
        setup_files={"app.py": "def run():\n    pass\n# TODO: add tests\n"},
        expected=EvalExpected(
            required_actions=["search_in_file"],
            final_answer_contains=["todo"],
        ),
        tags=["tool-use", "search"],
    ),
    EvalTask(
        task_id="code_metrics",
        name="Collect code metrics",
        prompt="Measure calc.py and summarize the code shape.",
        planner_response=planner_response("get_code_metrics", "finish"),
        agent_responses=[
            agent_response("Collect metrics.", "get_code_metrics", {"path": "calc.py"}),
            agent_response("Summarize metrics.", "finish", "calc.py has functions and one class."),
        ],
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
            final_answer_contains=["class"],
        ),
        tags=["code-analysis"],
    ),
    EvalTask(
        task_id="function_signature",
        name="Extract function signature",
        prompt="Extract the add function signature from math_utils.py.",
        planner_response=planner_response("get_function_signature", "finish"),
        agent_responses=[
            agent_response(
                "Get the signature.",
                "get_function_signature",
                {"path": "math_utils.py", "function_name": "add"},
            ),
            agent_response(
                "Return the signature.", "finish", "def add(left: int, right: int) -> int"
            ),
        ],
        setup_files={
            "math_utils.py": "def add(left: int, right: int) -> int:\n    return left + right\n"
        },
        expected=EvalExpected(
            required_actions=["get_function_signature"],
            final_answer_contains=["def add"],
        ),
        tags=["code-analysis"],
    ),
    EvalTask(
        task_id="run_python",
        name="Execute Python code",
        prompt="Run a tiny Python calculation and answer with the result.",
        planner_response=planner_response("run_python", "finish"),
        agent_responses=[
            agent_response("Run Python.", "run_python", {"code": "print(6 * 7)"}),
            agent_response("Answer with the result.", "finish", "The result is 42."),
        ],
        expected=EvalExpected(
            required_actions=["run_python"],
            final_answer_contains=["42"],
        ),
        tags=["tool-use", "execution"],
    ),
    EvalTask(
        task_id="skill_activation",
        name="Python skill activation signal",
        prompt="Write pytest guidance for a Python module with type hints.",
        planner_response=planner_response("task_complete"),
        agent_responses=[
            agent_response(
                "This is a Python testing task.",
                "task_complete",
                {"message": "pytest guidance ready"},
            )
        ],
        expected=EvalExpected(
            required_actions=["task_complete"],
            final_answer_contains=["pytest"],
        ),
        tags=["skills"],
    ),
    EvalTask(
        task_id="json_repair",
        name="Repair non-strict JSON response",
        prompt="Return a final answer even if the model emits Python-style JSON.",
        planner_response=planner_response("finish"),
        agent_responses=[
            "{'thought': 'single quotes are common model drift', 'action': 'finish', "
            "'action_input': {'answer': 'repaired json'},}"
        ],
        expected=EvalExpected(
            final_answer_contains=["repaired json"],
            metadata_min={"parse_repair_count": 1},
        ),
        tags=["recovery", "json"],
    ),
    EvalTask(
        task_id="unknown_tool_recovery",
        name="Recover from unknown tool",
        prompt="Recover after selecting a tool that does not exist.",
        planner_response=planner_response("missing_tool", "finish"),
        replan_response=planner_response("finish"),
        agent_responses=[
            agent_response("Try a non-existent tool.", "missing_tool", {"value": "x"}),
            agent_response(
                "Recover with a final answer.", "finish", "Recovered from unknown tool."
            ),
        ],
        expected=EvalExpected(
            final_answer_contains=["recovered"],
            metadata_min={"unknown_tool_count": 1},
        ),
        tags=["recovery"],
    ),
    EvalTask(
        task_id="tool_failure_replan",
        name="Recover from failed file read",
        prompt="If reading missing.txt fails, create recovered.txt instead.",
        planner_response=planner_response("read_file", "create_file", "task_complete"),
        replan_response=planner_response("create_file", "task_complete"),
        agent_responses=[
            agent_response("Try to read the file.", "read_file", {"path": "missing.txt"}),
            agent_response(
                "Create a recovery file.",
                "create_file",
                {"path": "recovered.txt", "content": "recovered after failure\n"},
            ),
            agent_response("Finish recovery.", "task_complete", {"message": "recovered"}),
        ],
        expected=EvalExpected(
            required_actions=["read_file", "create_file", "task_complete"],
            workspace_files={"recovered.txt": "recovered after failure"},
        ),
        tags=["recovery", "replan"],
    ),
    EvalTask(
        task_id="argument_recovery",
        name="Recover from invalid tool arguments",
        prompt="Recover after passing invalid action_input to run_python.",
        planner_response=planner_response("run_python", "finish"),
        agent_responses=[
            agent_response("Pass invalid arguments first.", "run_python", "print(1)"),
            agent_response("Retry with valid arguments.", "run_python", {"code": "print('ok')"}),
            agent_response("Finish.", "finish", "Argument recovery ok."),
        ],
        expected=EvalExpected(
            required_actions=["run_python"],
            final_answer_contains=["recovery ok"],
            metadata_min={"argument_error_count": 1},
        ),
        tags=["recovery", "arguments"],
    ),
]


def get_builtin_tasks() -> List[EvalTask]:
    return list(BUILTIN_TASKS)
