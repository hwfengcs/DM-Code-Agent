"""``--conversation-stdin`` 长驻会话模式的行为契约。

这里最重要的一条是 ``test_second_turn_sees_the_first_turn``：它证明多轮**真的共享
对话历史**，而不是每轮从零开始。没有这条断言，「支持多轮对话」就只是界面上把气泡
排在一起而已。

全部用 ``ScriptedLLMClient`` 驱动，**零网络、零 API key**——与确定性 eval 同一套路。
"""

from __future__ import annotations

import io
import itertools
import json
import time
from pathlib import Path
from typing import Any

import pytest

from dm_agent.cli.config import Config
from dm_agent.cli.runner import run_conversation_stdin
from dm_agent.evals.scripted_client import ScriptedLLMClient


def planner_response(*actions: str) -> str:
    return json.dumps(
        {
            "plan": [
                {"step": index + 1, "action": action, "reason": "conversation test"}
                for index, action in enumerate(actions)
            ]
        },
        ensure_ascii=False,
    )


def finish_response(answer: str) -> str:
    return json.dumps(
        {
            "thought": "done",
            "action": "finish",
            "action_input": {"answer": answer},
        },
        ensure_ascii=False,
    )


def one_turn(answer: str) -> list[str]:
    """一轮 = 一次 planner 调用 + 一次 ReAct 调用。"""
    return [planner_response("task_complete"), finish_response(answer)]


@pytest.fixture
def conversation(monkeypatch: pytest.MonkeyPatch) -> Any:
    """跑一次长驻会话，返回 (退出码, scripted client, 会话条目)。

    MCP 与技能都走真实装配，只把 LLM 客户端换成脚本化的那个。``responses`` 通常是
    脚本化响应列表；需要自定义客户端行为（例如某次调用抛异常）时，也可以直接传一个
    ``ScriptedLLMClient`` 实例。

    会话在 trace 所在的临时目录里跑：``load_mcp_config()`` 读的是**当前目录**的
    ``mcp_config.json``，不切目录的话，调用 pytest 的那个目录里配了哪些 MCP 服务器
    （文档让用户把带 npx 的示例配置复制到仓库根），这里就会真的把它们拉起来。
    """

    def run(lines: list[str], responses: list[str] | ScriptedLLMClient, *, trace_path: Path) -> Any:
        monkeypatch.chdir(trace_path.parent)
        client = (
            responses if isinstance(responses, ScriptedLLMClient) else ScriptedLLMClient(responses)
        )
        monkeypatch.setattr(
            "dm_agent.cli.runner.create_llm_client",
            lambda **_kwargs: client,
        )
        monkeypatch.setattr("sys.stdin", io.StringIO("".join(f"{line}\n" for line in lines)))
        config = Config(api_key="", provider="deepseek", model="scripted", max_steps=5)
        code = run_conversation_stdin(config, trace_path=trace_path)
        entries = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return code, client, entries

    return run


def task_line(task: str) -> str:
    return json.dumps({"task": task}, ensure_ascii=False)


def events_of(entries: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry.get("event") == event]


def test_second_turn_sees_the_first_turn(conversation: Any, tmp_path: Path) -> None:
    """核心证据：第二轮发给模型的 messages 里必须含第一轮的任务与回答。

    这就是「真多轮」与「前端把气泡连起来」的区别。
    """
    code, client, _entries = conversation(
        [task_line("第一轮：记住暗号 alpha-7"), task_line("第二轮：暗号是什么")],
        one_turn("已记住 alpha-7") + one_turn("alpha-7"),
        trace_path=tmp_path / "conv.jsonl",
    )
    assert code == 0

    # requests[0]=第一轮 planner, [1]=第一轮 ReAct, [2]=第二轮 planner, [3]=第二轮 ReAct
    assert len(client.requests) == 4
    second_turn_react = "\n".join(message.get("content", "") for message in client.requests[3])
    assert "alpha-7" in second_turn_react
    assert "第一轮" in second_turn_react
    assert "第二轮" in second_turn_react


def test_each_turn_is_its_own_run_in_the_session_log(conversation: Any, tmp_path: Path) -> None:
    """一份 JSONL 里两段 run。读侧（tracing.session / 前端 splitRuns）本来就支持多段。"""
    _code, _client, entries = conversation(
        [task_line("轮一"), task_line("轮二")],
        one_turn("a") + one_turn("b"),
        trace_path=tmp_path / "conv.jsonl",
    )
    assert len(events_of(entries, "run_start")) == 2
    assert len(events_of(entries, "run_end")) == 2
    assert [entry["payload"] for entry in events_of(entries, "conversation_start")] == [
        {"turn_protocol": 1}
    ]
    assert [entry["payload"]["turn"] for entry in events_of(entries, "turn_start")] == [1, 2]
    assert [entry["payload"] for entry in events_of(entries, "turn_end")] == [
        {"turn": 1, "status": "success"},
        {"turn": 2, "status": "success"},
    ]
    assert [entry["payload"]["task"] for entry in events_of(entries, "run_start")] == [
        "轮一",
        "轮二",
    ]


def test_entry_ids_stay_a_single_chain_across_turns(conversation: Any, tmp_path: Path) -> None:
    """条目树不能因为跨轮而断链——``parent_id`` 必须一路指回上一条。"""
    _code, _client, entries = conversation(
        [task_line("轮一"), task_line("轮二")],
        one_turn("a") + one_turn("b"),
        trace_path=tmp_path / "conv.jsonl",
    )
    for previous, current in itertools.pairwise(entries):
        assert current["parent_id"] == previous["id"]


def test_reset_clears_the_shared_history(conversation: Any, tmp_path: Path) -> None:
    """``{"type": "reset"}`` 之后，下一轮不该再看得见 reset 之前的内容。"""
    _code, client, entries = conversation(
        [task_line("记住暗号 alpha-7"), json.dumps({"type": "reset"}), task_line("暗号是什么")],
        one_turn("已记住") + one_turn("不知道"),
        trace_path=tmp_path / "conv.jsonl",
    )
    after_reset = "\n".join(message.get("content", "") for message in client.requests[3])
    assert "alpha-7" not in after_reset
    assert len(events_of(entries, "conversation_reset")) == 1


class OutageOnceClient(ScriptedLLMClient):
    """第 ``fail_on_call`` 次调用抛异常且不消耗脚本，其余调用照常按脚本应答。"""

    def __init__(self, responses: list[str], *, fail_on_call: int) -> None:
        super().__init__(responses)
        self.fail_on_call = fail_on_call
        self.seen = 0

    def respond(self, messages: list[dict[str, str]], **extra: Any) -> str:
        self.seen += 1
        if self.seen == self.fail_on_call:
            raise RuntimeError("simulated provider outage")
        return super().respond(messages, **extra)


def test_a_failing_turn_does_not_kill_the_conversation(conversation: Any, tmp_path: Path) -> None:
    """单轮炸了要记一条证据然后继续等下一轮，而不是让整个会话进程退出。"""
    # 让第 2 次模型调用（第一轮的 ReAct 请求）抛异常：planner 的失败会被内核吞掉走
    # 常规模式，ReAct 请求的异常才会真正逸出这一轮。异常不消耗脚本，所以第二轮照常
    # 拿到自己的 planner + ReAct 响应。
    client = OutageOnceClient(
        [planner_response("task_complete"), *one_turn("第二轮成功")], fail_on_call=2
    )
    code, _client, entries = conversation(
        [task_line("会失败的一轮"), task_line("正常的一轮")],
        client,
        trace_path=tmp_path / "conv.jsonl",
    )
    assert code == 0

    # 证据：只有炸掉的那一轮留下 run_error，它也没有伪造出一条 run_end。
    errors = events_of(entries, "run_error")
    assert [error["payload"]["turn"] for error in errors] == [1]
    assert errors[0]["payload"]["error_type"] == "RuntimeError"
    # 会话活到了第二轮，而且第二轮真的成功了。
    ends = events_of(entries, "run_end")
    assert [end["payload"]["status"] for end in ends] == ["success"]
    assert ends[0]["payload"]["final_answer"] == "第二轮成功"
    assert [entry["payload"] for entry in events_of(entries, "turn_end")] == [
        {"turn": 1, "status": "error"},
        {"turn": 2, "status": "success"},
    ]
    assert [entry["payload"] for entry in events_of(entries, "conversation_end")] == [
        {"turns": 2, "reason": "eof"}
    ]


def test_blank_and_malformed_lines_are_ignored(conversation: Any, tmp_path: Path) -> None:
    """坏行不该炸掉会话，也不该被当成一轮任务。"""
    _code, _client, entries = conversation(
        ["", "not json at all", "[1, 2, 3]", json.dumps({"task": "   "}), task_line("唯一的一轮")],
        one_turn("ok"),
        trace_path=tmp_path / "conv.jsonl",
    )
    assert len(events_of(entries, "run_start")) == 1
    assert events_of(entries, "conversation_end")[0]["payload"]["turns"] == 1


def test_eof_ends_the_conversation_cleanly(conversation: Any, tmp_path: Path) -> None:
    code, _client, entries = conversation([], [], trace_path=tmp_path / "conv.jsonl")
    assert code == 0
    end = events_of(entries, "conversation_end")
    assert len(end) == 1
    assert end[0]["payload"] == {"turns": 0, "reason": "eof"}


# --- 真进程端到端 ----------------------------------------------------------

# 一个脚本化的 provider 扩展：把每次请求的全文追加进日志文件，并按顺序吐预设响应。
# 这样就能在**真子进程**里验证「第二轮看得见第一轮」，而不必联网或配 key。
SCRIPTED_PROVIDER = """
import json, os, pathlib

LOG = pathlib.Path(os.environ["DM_TEST_PROMPT_LOG"])
RESPONSES = json.loads(os.environ["DM_TEST_RESPONSES"])


class ScriptedClient:
    model = "scripted"
    total_respond_retries = 0

    def __init__(self):
        self.index = 0

    def respond(self, messages, **kwargs):
        text = "\\n".join(message.get("content", "") for message in messages)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"prompt": text}, ensure_ascii=False) + "\\n")
        reply = RESPONSES[self.index % len(RESPONSES)]
        self.index += 1
        return reply


def setup(api):
    api.register_provider("scripted", lambda **kwargs: ScriptedClient())
"""


def test_real_subprocess_carries_context_between_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端到端：真的 spawn CLI 子进程，用 server 的 argv 构造器，喂两轮任务。

    这条把最后一段缝隙也焊上了——前面的用例分别覆盖「CLI 内部的多轮语义」和
    「server 的对话端点」，这条则证明**server 生成的那条命令行**真的能起一个
    跨轮共享上下文的进程。全程离线：provider 由 ``--extension`` 注入。
    """
    from dm_agent.server.process import RunProcess, RunSpec, build_conversation_argv

    extension = tmp_path / "scripted_provider.py"
    extension.write_text(SCRIPTED_PROVIDER, encoding="utf-8")
    prompt_log = tmp_path / "prompts.jsonl"
    trace_path = tmp_path / "chat.jsonl"

    spec = RunSpec(task="", provider="scripted", options={"max_steps": 3})
    argv = build_conversation_argv(spec, trace_path=trace_path)
    # provider 由扩展注册，所以要把扩展显式挂上；--no-extensions 会把它一起关掉。
    argv = [*argv, "--extension", str(extension)]

    # 必须用 setenv 真正改 os.environ：Popen 继承的是进程的真实环境，
    # monkeypatch.setattr(os, "environ", {...}) 只换掉 Python 侧的字典，传不下去。
    monkeypatch.setenv("DM_TEST_PROMPT_LOG", str(prompt_log))
    monkeypatch.setenv(
        "DM_TEST_RESPONSES",
        json.dumps(
            [planner_response("task_complete"), finish_response("好的")], ensure_ascii=False
        ),
    )

    process = RunProcess(argv, cwd=tmp_path, trace_path=trace_path)
    process.start(stdin_pipe=True)
    try:
        assert process.send_line({"task": "第一轮：记住暗号 alpha-7"})
        _wait_for_run_ends(trace_path, 1, process=process)
        assert process.send_line({"task": "第二轮：暗号是什么"})
        _wait_for_run_ends(trace_path, 2, process=process)
    finally:
        process.close_stdin()
        process.wait(20.0)
        process.stop()

    prompts = [
        json.loads(line)["prompt"]
        for line in prompt_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # 最后一次请求是第二轮的 ReAct 调用，它必须带着第一轮的内容。
    assert "alpha-7" in prompts[-1]
    assert "第一轮" in prompts[-1] and "第二轮" in prompts[-1]

    entries = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(events_of(entries, "run_start")) == 2
    assert len(events_of(entries, "run_end")) == 2


def _wait_for_run_ends(
    trace_path: Path, count: int, *, process: Any, timeout: float = 60.0
) -> None:
    """等会话日志里出现 ``count`` 条 ``run_end``。

    子进程提前死掉时立刻失败并把它的 stdout 带出来——否则这里只会干等到超时，
    再从「没有 run_end」这条毫无信息量的断言去猜发生了什么。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if trace_path.is_file():
            text = trace_path.read_text(encoding="utf-8", errors="replace")
            if sum(1 for line in text.splitlines() if '"run_end"' in line) >= count:
                return
        if process.poll() is not None:
            raise AssertionError(f"子进程提前退出（{process.poll()}）：{process.read_output()}")
        time.sleep(0.1)
    raise AssertionError(f"等了 {timeout}s 仍没有 {count} 条 run_end")
