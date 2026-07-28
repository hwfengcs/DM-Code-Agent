"""针对 ``ReactAgent`` 内部分支的行为测试。

这些分支此前只有间接覆盖或完全没有覆盖（`pytest --cov=dm_agent.core` 报告的
`agent.py` 未覆盖行）。拆分 `agent.py` 之前先把它们钉住，重构才有安全网。
"""

from __future__ import annotations

import json

from dm_agent.core.agent import ReactAgent
from dm_agent.core.context_window import should_log_memory_status
from dm_agent.core.planner import PlanStep
from dm_agent.core.prompting import build_user_prompt
from dm_agent.tools.base import Tool
from dm_agent.tracing import TraceWriter, load_trace_events


class FakeRespondClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.model = "fake-model"

    def respond(self, messages, **extra):
        if not self.responses:
            raise AssertionError("FakeRespondClient ran out of responses")
        return self.responses.pop(0)


def _action(action: str, action_input) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


def _tools():
    return [
        Tool("echo", "Echo text", lambda arguments: f"echo:{arguments.get('text', '')}"),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]


def _agent(responses, **kwargs):
    kwargs.setdefault("enable_planning", False)
    kwargs.setdefault("enable_compression", False)
    return ReactAgent(FakeRespondClient(responses), _tools(), **kwargs)


# --- 响应解析：空响应 / 围栏 JSON / 非对象 JSON ---------------------------------


def test_empty_model_response_is_reported_as_parse_error():
    agent = _agent(["", _action("finish", {"answer": "recovered"})])

    result = agent.run("recover from an empty response", max_steps=3)

    assert result["metadata"]["parse_error_count"] == 1
    assert "模型返回空响应" in result["steps"][0]["observation"]
    assert result["final_answer"] == "recovered"


def test_fenced_json_response_is_parsed_and_counted_as_repaired():
    payload = json.dumps(
        {"thought": "t", "action": "finish", "action_input": {"answer": "fenced ok"}},
        ensure_ascii=False,
    )
    agent = _agent([f"这是结果：\n```json\n{payload}\n```\n"])

    result = agent.run("parse a fenced json response", max_steps=2)

    assert result["final_answer"] == "fenced ok"
    assert result["metadata"]["parse_repair_count"] == 1
    assert result["metadata"]["parse_error_count"] == 0


def test_non_object_json_response_is_rejected():
    agent = _agent(["[1, 2, 3]", _action("finish", {"answer": "recovered"})])

    result = agent.run("reject a json array response", max_steps=3)

    assert result["metadata"]["parse_error_count"] == 1
    assert "Response is not a valid JSON object." in result["steps"][0]["observation"]
    assert result["final_answer"] == "recovered"


# --- 完成判定与摘要 -------------------------------------------------------------


def test_finish_with_non_string_payload_falls_back_to_json_dump():
    agent = _agent([_action("finish", [1, 2])])

    result = agent.run("finish with a list payload", max_steps=2)

    assert result["final_answer"] == "[1, 2]"
    assert result["metadata"]["status"] == "success"


def test_completion_summary_lists_tools_when_answer_is_empty():
    agent = _agent([_action("echo", {"text": "one"}), _action("finish", {"answer": ""})])

    result = agent.run("summarize an empty answer by tool", max_steps=3)

    assert result["final_answer"] == ""
    assert result["metadata"]["completion_summary"] == "任务已完成。本轮通过 echo 完成处理。"


def test_completion_summary_falls_back_without_tool_steps():
    agent = _agent([_action("finish", {"answer": ""})])

    result = agent.run("summarize an empty answer without tools", max_steps=2)

    assert result["metadata"]["completion_summary"] == "任务已完成。本轮对话已收尾。"


# --- 工具入参归一化与校验 -------------------------------------------------------


def test_task_complete_accepts_missing_arguments():
    agent = _agent([_action("task_complete", None)])

    result = agent.run("finish with null task_complete arguments", max_steps=2)

    assert result["final_answer"] == "done"
    assert result["metadata"]["status"] == "success"
    assert result["metadata"]["argument_error_count"] == 0


def test_task_complete_accepts_string_arguments():
    agent = _agent([_action("task_complete", "all set")])

    result = agent.run("finish with string task_complete arguments", max_steps=2)

    assert result["final_answer"] == "all set"
    assert result["metadata"]["argument_error_count"] == 0


def test_task_complete_ignores_non_object_arguments():
    agent = _agent([_action("task_complete", [1, 2])])

    result = agent.run("finish with list task_complete arguments", max_steps=2)

    assert result["final_answer"] == "done"
    assert result["metadata"]["argument_error_count"] == 0


def test_null_arguments_for_regular_tool_are_reported():
    agent = _agent([_action("echo", None), _action("finish", {"answer": "recovered"})])

    result = agent.run("reject null tool arguments", max_steps=3)

    assert result["metadata"]["argument_error_count"] == 1
    assert result["steps"][0]["observation"] == "Tool arguments missing: action_input is null."
    assert result["final_answer"] == "recovered"


# --- 重规划的失败与空计划分支 ---------------------------------------------------


def _replan_agent(replan_impl):
    plan_response = json.dumps(
        {
            "plan": [
                {"step": 1, "action": "explode", "reason": "trigger failure"},
                {"step": 2, "action": "task_complete", "reason": "finish"},
            ]
        }
    )
    client = FakeRespondClient([plan_response, _action("explode", {})])
    tools = [
        Tool("explode", "Fail", lambda arguments: (_ for _ in ()).throw(RuntimeError("boom"))),
        Tool("task_complete", "Finish", lambda arguments: arguments.get("message", "done")),
    ]
    agent = ReactAgent(client, tools, enable_planning=True, enable_compression=False)
    assert agent.planner is not None
    agent.planner.replan = replan_impl
    return agent


def test_replan_exception_is_recorded_without_breaking_the_run():
    def boom(*args, **kwargs):
        raise RuntimeError("planner down")

    agent = _replan_agent(boom)

    result = agent.run("survive a replan failure", max_steps=1)

    assert result["metadata"]["status"] == "max_steps_exceeded"
    assert result["metadata"]["failure_reason"] == "Replan failed: planner down"
    assert result["metadata"]["replan_count"] == 0


def test_empty_replan_keeps_the_previous_plan():
    agent = _replan_agent(lambda *args, **kwargs: [])

    result = agent.run("keep the plan when replan returns nothing", max_steps=1)

    assert result["metadata"]["replan_count"] == 0
    # 预算未耗尽，说明 replan 确实被调用过，只是返回了空计划。
    assert result["metadata"]["replan_skipped_count"] == 0
    assert result["metadata"]["replan_budget_exhausted_count"] == 0


# --- 上下文压缩的预算、记忆卫生与 LLM 摘要分支 -----------------------------------


def _budget_agent(responses, **kwargs):
    kwargs.setdefault("enable_planning", False)
    kwargs.setdefault("enable_compression", True)
    kwargs.setdefault("context_token_budget", 10)
    agent = ReactAgent(FakeRespondClient(responses), _tools(), **kwargs)
    assert agent.compressor is not None
    # 拉高压缩节奏阈值，只留 token 预算这一条触发路径。
    agent.compressor.compress_every = 100
    agent.compressor.keep_recent = 1
    return agent


def test_token_budget_compression_is_traced(tmp_path):
    trace_path = tmp_path / "budget.jsonl"
    writer = TraceWriter(trace_path)
    agent = _budget_agent(
        [_action("echo", {"text": "x" * 400}), _action("finish", {"answer": "done"})],
        trace_writer=writer,
    )

    result = agent.run("compress by token budget", max_steps=2)
    writer.close()

    phases = [
        event["payload"]["phase"]
        for event in load_trace_events(trace_path)
        if event["event"] == "context_budget"
    ]
    assert "forced_compress" in phases
    assert "post_compress_still_over" in phases
    assert result["metadata"]["budget_compression_count"] == 1
    assert result["metadata"]["memory_compression_count"] == 1


def test_llm_compression_counters_are_reported():
    agent = _budget_agent(
        [
            _action("echo", {"text": "x" * 400}),
            "旧上下文摘要：读过一个文件。",
            _action("finish", {"answer": "done"}),
        ],
        enable_llm_compression=True,
    )

    result = agent.run("compress with an llm summary", max_steps=2)

    assert result["metadata"]["llm_compression_enabled"] is True
    assert result["metadata"]["llm_summary_count"] == 1
    assert result["metadata"]["llm_summary_error_count"] == 0


def test_memory_hygiene_invalidation_is_traced(tmp_path):
    trace_path = tmp_path / "hygiene.jsonl"
    writer = TraceWriter(trace_path)
    agent = ReactAgent(
        FakeRespondClient(
            [
                _action("echo", {"text": "pytest returncode: 1 AssertionError in retry.py"}),
                _action("echo", {"text": "retry.py tests completed successfully returncode: 0"}),
                _action("echo", {"text": "wrap up"}),
                _action("finish", {"answer": "done"}),
            ]
        ),
        _tools(),
        enable_planning=False,
        enable_compression=True,
        enable_memory_hygiene=True,
        trace_writer=writer,
    )
    assert agent.compressor is not None
    agent.compressor.compress_every = 1
    agent.compressor.keep_recent = 1

    result = agent.run("supersede a failure memory after success", max_steps=4)
    writer.close()

    invalidations = [
        event for event in load_trace_events(trace_path) if event["event"] == "memory_invalidation"
    ]
    assert invalidations
    assert invalidations[0]["payload"]["superseded"] >= 1
    assert result["metadata"]["memory_invalidation_count"] >= 1


# --- 记忆状态日志节流 -----------------------------------------------------------


def test_memory_status_log_throttle_branches():
    def should_log(**kwargs):
        base = {
            "compression_count": 2,
            "saved_messages": 0,
            "memory_items": 0,
            "last_logged_saved_messages": 0,
            "last_logged_memory_items": 0,
        }
        base.update(kwargs)
        return should_log_memory_status(**base)

    # 第一次压缩总是播报；此后按固定间隔播报。
    assert should_log(compression_count=1) is True
    assert should_log(compression_count=5) is True
    # 节省的消息数或记忆条数出现明显增量时也播报。
    assert should_log(saved_messages=20) is True
    assert should_log(memory_items=7) is True
    # 增量不足则保持安静。
    assert should_log(saved_messages=1, memory_items=1) is False


# --- 用户提示词与公开接口 -------------------------------------------------------


def test_build_user_prompt_renders_task_and_plan():
    plan = [
        PlanStep(
            step_number=1,
            action="echo",
            reason="inspect the file",
        )
    ]

    prompt = build_user_prompt("排查回归", plan)

    assert "任务：排查回归" in prompt
    assert "执行计划：" in prompt
    assert "[todo] 步骤 1: echo - inspect the file" in prompt
    assert "之前的步骤：" not in prompt


def test_get_conversation_history_returns_a_copy():
    agent = _agent([_action("finish", {"answer": "done"})])
    agent.run("build some history", max_steps=2)

    history = agent.get_conversation_history()
    assert history
    history.append({"role": "user", "content": "外部追加不应影响 agent"})

    assert len(agent.get_conversation_history()) == len(history) - 1
