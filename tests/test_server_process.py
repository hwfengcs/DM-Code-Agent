"""子进程执行器：argv 白名单、请求校验、真实的启动与终止。

这一层不需要 fastapi，也不需要 API key——终止测试 spawn 的是 ``python -c sleep``，
不是真的 agent。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from dm_agent.clients import PROVIDER_DEFAULTS
from dm_agent.server.process import (
    MAX_TASK_CHARS,
    RunProcess,
    RunSpec,
    SpecError,
    build_argv,
    build_conversation_argv,
)

PROVIDERS = set(PROVIDER_DEFAULTS)


def spec(task: str = "修一个 bug", **kwargs: object) -> RunSpec:
    options = kwargs.pop("options", {})
    return RunSpec(
        task=task,
        provider=str(kwargs.pop("provider", "deepseek")),
        model=str(kwargs.pop("model", "")),
        options=dict(options),  # type: ignore[arg-type]
    )


# --- 校验 ---------------------------------------------------------------


def test_rejects_empty_task() -> None:
    with pytest.raises(SpecError, match="任务不能为空"):
        spec("   ").validate(PROVIDERS)


def test_rejects_overlong_task() -> None:
    with pytest.raises(SpecError, match="任务过长"):
        spec("x" * (MAX_TASK_CHARS + 1)).validate(PROVIDERS)


def test_rejects_unknown_provider() -> None:
    with pytest.raises(SpecError, match="未知的 provider"):
        spec(provider="definitely-not-a-provider").validate(PROVIDERS)


def test_accepts_every_real_provider() -> None:
    for provider in PROVIDERS:
        spec(provider=provider).validate(PROVIDERS)


@pytest.mark.parametrize("model", ["a" * 201, "gpt\x00evil", "line\nbreak"])
def test_rejects_bad_model_names(model: str) -> None:
    with pytest.raises(SpecError, match="模型名"):
        spec(model=model).validate(PROVIDERS)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_steps", 0),
        ("max_steps", 1001),
        ("temperature", -0.1),
        ("temperature", 2.1),
        ("llm_max_retries", 11),
        ("max_replans", -2),
    ],
)
def test_rejects_out_of_range_numbers(key: str, value: float) -> None:
    with pytest.raises(SpecError, match="超出允许范围"):
        spec(options={key: value}).validate(PROVIDERS)


def test_rejects_wrong_types() -> None:
    with pytest.raises(SpecError, match="必须是布尔值"):
        spec(options={"enable_adaptive_replanning": "yes"}).validate(PROVIDERS)
    with pytest.raises(SpecError, match="必须是数值"):
        spec(options={"max_steps": "many"}).validate(PROVIDERS)
    # bool 是 int 的子类，但 --max-steps True 显然是错的，必须拒绝。
    with pytest.raises(SpecError, match="必须是数值"):
        spec(options={"max_steps": True}).validate(PROVIDERS)


def test_unknown_option_keys_are_ignored_not_rejected() -> None:
    """前端可能比后端新。多传字段不该让整个请求失败，但也不该进 argv。"""
    request = spec(options={"some_future_flag": True, "max_steps": 5})
    request.validate(PROVIDERS)
    argv = build_argv(request, trace_path=Path("t.jsonl"))
    assert "--some-future-flag" not in argv
    assert "some_future_flag" not in " ".join(argv)
    assert "--max-steps" in argv


# --- argv 拼装 ----------------------------------------------------------


def test_argv_uses_module_entry_not_console_script() -> None:
    """console script 不一定在 PATH 上；sys.executable 一定是当前解释器。"""
    argv = build_argv(spec(), trace_path=Path("sessions/x.jsonl"))
    assert argv[:3] == [sys.executable, "-m", "dm_agent.cli"]


def test_argv_always_writes_a_trace() -> None:
    """会话日志是实时流的唯一数据源，必须落盘。"""
    argv = build_argv(spec(), trace_path=Path("sessions/x.jsonl"))
    assert "--trace" in argv
    assert argv[argv.index("--trace") + 1] == str(Path("sessions/x.jsonl"))


def test_task_goes_last_after_a_double_dash() -> None:
    """以 -- 开头的任务不能被 argparse 当成选项。"""
    argv = build_argv(spec("--help 这个选项坏了"), trace_path=Path("t.jsonl"))
    assert argv[-2] == "--"
    assert argv[-1] == "--help 这个选项坏了"


def test_shell_metacharacters_stay_in_one_argv_element() -> None:
    """shell=False + 单元素 = 没有命令注入。这条断言就是那个保证的具体形态。"""
    nasty = 'x"; rm -rf / #$(whoami)`id`'
    argv = build_argv(spec(nasty), trace_path=Path("t.jsonl"))
    assert argv[-1] == nasty
    assert argv.count(nasty) == 1


def test_boolean_flags_only_appear_when_true() -> None:
    off = build_argv(
        spec(options={"enable_adaptive_replanning": False}), trace_path=Path("t.jsonl")
    )
    assert "--enable-adaptive-replanning" not in off
    on = build_argv(spec(options={"enable_adaptive_replanning": True}), trace_path=Path("t.jsonl"))
    assert "--enable-adaptive-replanning" in on


def test_edit_guard_is_a_reverse_flag() -> None:
    """守卫默认开，只有显式关掉才加 --disable-edit-guard。"""
    default = build_argv(spec(), trace_path=Path("t.jsonl"))
    assert "--disable-edit-guard" not in default
    kept = build_argv(spec(options={"enable_edit_guard": True}), trace_path=Path("t.jsonl"))
    assert "--disable-edit-guard" not in kept
    disabled = build_argv(spec(options={"enable_edit_guard": False}), trace_path=Path("t.jsonl"))
    assert "--disable-edit-guard" in disabled


def test_model_omitted_when_empty() -> None:
    assert "--model" not in build_argv(spec(model=""), trace_path=Path("t.jsonl"))
    argv = build_argv(spec(model="deepseek-chat"), trace_path=Path("t.jsonl"))
    assert argv[argv.index("--model") + 1] == "deepseek-chat"


ALL_OPTIONS: dict[str, object] = {
    "enable_adaptive_replanning": True,
    "enable_edit_guard": False,
    "max_steps": 10,
    "temperature": 0.5,
    "max_observation_chars": 1000,
    "context_token_budget": 2000,
    "llm_max_retries": 1,
    "max_replans": 3,
}


def test_generated_argv_is_accepted_by_the_real_cli_parser() -> None:
    """防漂移：生成的 argv 必须能被 ``dm_agent.cli`` 真正的解析器吃下。

    这条断言的价值在于「有人改了 CLI 开关名而忘了改 server」时立刻红，而不是等到
    运行时子进程报 unrecognized arguments。直接喂真解析器比比对开关名集合更强：
    参数元数（要不要跟值）、类型转换、`--` 分隔都一并验了。
    """
    from dm_agent.cli.args import parse_args

    request = spec("--help 这个选项坏了", model="m", options=ALL_OPTIONS)
    request.validate(PROVIDERS)
    argv = build_argv(request, trace_path=Path("sessions/t.jsonl"))

    # argv[:3] 是 [python, -m, dm_agent.cli]，解析器只看后面的部分。
    parsed = parse_args(argv[3:])

    assert parsed.task == "--help 这个选项坏了"
    assert parsed.provider == "deepseek"
    assert parsed.model == "m"
    # CLI 的 --trace 是 type=Path，所以解析结果是 Path 而不是字符串。
    assert Path(parsed.trace) == Path("sessions/t.jsonl")
    # 数值确实经过了类型转换，而不是留成字符串。
    assert parsed.max_steps == 10
    assert parsed.temperature == pytest.approx(0.5)
    assert parsed.max_replans == 3
    # 布尔开关生效。
    # --disable-edit-guard 的 dest 是 enable_edit_guard + store_false，
    # 所以「传了这个开关」在解析结果里表现为 enable_edit_guard=False。
    assert parsed.enable_edit_guard is False


def test_default_argv_is_also_accepted(tmp_path: Path) -> None:
    """最小请求（不带任何 options）同样要能被解析。"""
    from dm_agent.cli.args import parse_args

    argv = build_argv(spec(), trace_path=tmp_path / "t.jsonl")
    parsed = parse_args(argv[3:])
    assert parsed.task == "修一个 bug"
    # 没传 --disable-edit-guard，守卫保持默认开启。
    assert parsed.enable_edit_guard is True


# --- 对话模式的 argv ------------------------------------------------------


def test_conversation_argv_has_no_positional_task() -> None:
    """对话模式的任务是逐轮从 stdin 送的，argv 里**不能**有位置参数任务。"""
    argv = build_conversation_argv(spec(), trace_path=Path("sessions/c.jsonl"))
    assert "--conversation-stdin" in argv
    assert "--" not in argv
    assert "修一个 bug" not in argv


def test_conversation_argv_keeps_the_same_switch_whitelist() -> None:
    """两条入口共用一份开关翻译——对话模式不该有自己的一套开关语义。"""
    request = spec("", model="m", options=ALL_OPTIONS)
    run_argv = build_argv(request, trace_path=Path("sessions/t.jsonl"))
    chat_argv = build_conversation_argv(request, trace_path=Path("sessions/t.jsonl"))
    # 一次性运行的尾巴是 ["--", task]，对话的尾巴是 ["--conversation-stdin"]。
    assert chat_argv[:-1] == run_argv[:-2]


def test_conversation_argv_is_accepted_by_the_real_cli_parser() -> None:
    """同样的防漂移断言：对话 argv 必须过真解析器 **且** 过真的互斥校验。

    只测 parse_args 不够——``--conversation-stdin`` 的前置条件（必须配 --trace、
    不能带位置任务）住在 ``validate_feature_args`` 里，那才是子进程真正会执行的检查。
    这条断言最初就抓到了「server 会拼出一个子进程直接 exit 2 的 argv」。
    """
    from dm_agent.cli.args import parse_args, validate_feature_args

    request = spec("", model="m", options=ALL_OPTIONS)
    request.validate(PROVIDERS, for_conversation=True)
    argv = build_conversation_argv(request, trace_path=Path("sessions/c.jsonl"))

    parsed = parse_args(argv[3:])
    assert parsed.conversation_stdin is True
    assert parsed.task is None
    assert Path(parsed.trace) == Path("sessions/c.jsonl")
    assert parsed.max_steps == 10
    assert parsed.enable_edit_guard is False
    assert validate_feature_args(parsed) == ""


def test_conversation_spec_may_skip_task_validation() -> None:
    """建对话时还没有任务；其余校验（provider / 数值范围）一条不能少。"""
    RunSpec(task="", provider="deepseek").validate(PROVIDERS, for_conversation=True)

    with pytest.raises(SpecError):
        RunSpec(task="", provider="deepseek").validate(PROVIDERS)
    with pytest.raises(SpecError):
        RunSpec(task="", provider="nope").validate(PROVIDERS, for_conversation=True)
    with pytest.raises(SpecError):
        RunSpec(task="", provider="deepseek", options={"max_steps": 9999}).validate(
            PROVIDERS, for_conversation=True
        )


# --- 真实的启动与终止 ---------------------------------------------------


def _sleeper(seconds: int = 60) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def test_process_starts_and_reports_pid(tmp_path: Path) -> None:
    process = RunProcess(_sleeper(), cwd=tmp_path, trace_path=tmp_path / "t.jsonl")
    process.start()
    try:
        assert process.pid > 0
        assert process.poll() is None  # 还在跑
    finally:
        process.stop(grace_seconds=1.0)


def test_stop_actually_terminates_the_process(tmp_path: Path) -> None:
    """Windows 与 POSIX 走的是不同的终止路径，这条在两边都必须过。"""
    process = RunProcess(_sleeper(), cwd=tmp_path, trace_path=tmp_path / "t.jsonl")
    process.start()
    assert process.stop(grace_seconds=2.0) is True

    # 给操作系统一点时间回收，然后确认真的结束了。
    deadline = time.time() + 10
    while time.time() < deadline and process.poll() is None:
        time.sleep(0.1)
    assert process.poll() is not None, "stop() 之后子进程仍在运行"


def test_stop_on_finished_process_returns_false(tmp_path: Path) -> None:
    process = RunProcess(
        [sys.executable, "-c", "pass"], cwd=tmp_path, trace_path=tmp_path / "t.jsonl"
    )
    process.start()
    deadline = time.time() + 10
    while time.time() < deadline and process.poll() is None:
        time.sleep(0.05)
    assert process.stop() is False


def test_exit_code_is_reported(tmp_path: Path) -> None:
    process = RunProcess(
        [sys.executable, "-c", "raise SystemExit(3)"],
        cwd=tmp_path,
        trace_path=tmp_path / "t.jsonl",
    )
    process.start()
    deadline = time.time() + 10
    while time.time() < deadline and process.poll() is None:
        time.sleep(0.05)
    assert process.poll() == 3


def test_child_runs_in_the_configured_workspace(tmp_path: Path) -> None:
    """agent 必须在 --workspace 里读写，不是在控制台进程的 cwd 里。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    process = RunProcess(
        [sys.executable, "-c", "from pathlib import Path; Path('proof.txt').write_text('ok')"],
        cwd=workspace,
        trace_path=tmp_path / "t.jsonl",
    )
    process.start()
    deadline = time.time() + 10
    while time.time() < deadline and process.poll() is None:
        time.sleep(0.05)
    assert (workspace / "proof.txt").read_text() == "ok"
