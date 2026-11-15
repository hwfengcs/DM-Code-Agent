"""把一次运行请求翻译成 ``dm-agent`` 子进程。

**为什么是子进程而不是在 server 进程里直接构造 ReactAgent**：

* ``ReactAgent`` 没有取消接口，钩子抛异常按文档等价于放行——想支持「停止运行」
  就得改内核；子进程 ``terminate()`` 就够了。
* MCP 的 stdio 服务器是子进程，随 agent 进程一起收掉最干净。
* 崩溃隔离：agent 炸了不影响控制台。
* **最重要的一条**：CLI 是本项目的参考实现。走子进程意味着 Web 控制台是 CLI 的
  前端，而不是第二套装配逻辑——两边不会漂移。

安全模型：argv 全部由白名单拼装，``shell=False``，任务文本作为**单个 argv 元素**
放在 ``--`` 之后（防止以 ``--`` 开头的任务被 argparse 当成选项）。这里不做任何
字符串插值。
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dm_agent.processes import ProcessTree

__all__ = [
    "RunProcess",
    "RunSpec",
    "SpecError",
    "build_argv",
    "build_conversation_argv",
]

# 任务文本上限。防止有人把一整个仓库粘进来撑爆 argv（Windows 命令行约 32K 上限）。
MAX_TASK_CHARS = 8000
MAX_OUTPUT_BYTES = 64 * 1024


class SpecError(ValueError):
    """运行请求不合法。"""


# 白名单：请求字段 → CLI 开关。**只有这张表里的键会被翻译成 argv**，
# 请求里多出来的字段一律忽略，不存在「传个奇怪的键就能注入参数」这条路。
BOOL_FLAGS: dict[str, str] = {
    "enable_adaptive_replanning": "--enable-adaptive-replanning",
}

# 数值开关 → (CLI 开关, 最小值, 最大值)。超范围直接拒绝，不静默截断。
NUMBER_FLAGS: dict[str, tuple[str, float, float]] = {
    "max_steps": ("--max-steps", 1, 1000),
    "temperature": ("--temperature", 0.0, 2.0),
    "max_observation_chars": ("--max-observation-chars", 0, 1_000_000),
    "context_token_budget": ("--context-token-budget", 0, 1_000_000),
    "llm_max_retries": ("--llm-max-retries", 0, 10),
    "max_replans": ("--max-replans", -1, 100),
}


@dataclass(frozen=True)
class RunSpec:
    """一次运行请求。字段名与 ``/api/meta`` 里 capability 目录的 ``key`` 对应。"""

    task: str
    provider: str
    model: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    def validate(self, allowed_providers: set[str], *, for_conversation: bool = False) -> None:
        """校验请求。

        ``for_conversation=True`` 时只有一处不同：建对话时**还没有任务**
        （第一轮随后从 stdin 送进去），所以跳过任务非空检查。

        其余校验（provider、model、开关取值范围）两种模式完全一致。
        """
        if not for_conversation and not self.task.strip():
            raise SpecError("任务不能为空。")
        if len(self.task) > MAX_TASK_CHARS:
            raise SpecError(f"任务过长（{len(self.task)} 字，上限 {MAX_TASK_CHARS}）。")
        if "\x00" in self.task:
            # NUL 进不了 argv：不在这里拒绝的话，Popen 会抛 ValueError，路由只认 OSError。
            raise SpecError("任务不能包含 NUL 字符。")
        if self.provider not in allowed_providers:
            raise SpecError(f"未知的 provider：{self.provider}")
        # 模型名会作为 argv 元素传给子进程。不做 shell 解析，所以只需挡住
        # 控制字符（它们进日志会破坏 JSONL 的可读性）与超长值。
        if len(self.model) > 200 or any(ord(char) < 32 for char in self.model):
            raise SpecError("模型名不合法。")
        for key, value in self.options.items():
            # enable_edit_guard 是反向开关（--disable-edit-guard），不在 BOOL_FLAGS 里，
            # 但校验规则与布尔开关完全相同。
            if key in BOOL_FLAGS or key == "enable_edit_guard":
                if not isinstance(value, bool):
                    raise SpecError(f"{key} 必须是布尔值。")
            elif key in NUMBER_FLAGS:
                _, low, high = NUMBER_FLAGS[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise SpecError(f"{key} 必须是数值。")
                if key != "temperature" and not isinstance(value, int):
                    raise SpecError(f"{key} 必须是整数。")
                if not low <= value <= high:
                    raise SpecError(f"{key} 超出允许范围 [{low}, {high}]。")
                if key == "max_observation_chars" and 0 < value < 200:
                    raise SpecError("max_observation_chars 必须为 0（禁用）或至少 200。")
            # 其余键静默忽略——前端可能比后端新，多传字段不该让整个请求失败。


def _base_argv(spec: RunSpec, *, trace_path: Path) -> list[str]:
    """单次运行与对话模式共用的那一段命令行。

    用 ``python -m dm_agent.cli`` 而不是 ``dm-agent``：console script 不一定在 PATH 上
    （editable 安装、未激活 venv 都可能没有），而 ``sys.executable`` 一定是当前解释器。
    """
    argv = [sys.executable, "-m", "dm_agent.cli", "--no-config"]
    argv += ["--provider", spec.provider]
    if spec.model:
        argv.append(f"--model={spec.model}")
    # 会话日志是控制台实时流的唯一数据源，必须落盘。
    argv += ["--trace", str(trace_path)]

    for key, flag in BOOL_FLAGS.items():
        if spec.options.get(key) is True:
            argv.append(flag)
    # 反向开关：守卫默认开，只有显式关掉时才加 --disable-edit-guard。
    if spec.options.get("enable_edit_guard") is False:
        argv.append("--disable-edit-guard")

    for key, (flag, _low, _high) in NUMBER_FLAGS.items():
        value = spec.options.get(key)
        if value is not None and not isinstance(value, bool):
            argv += [flag, str(value)]
    return argv


def build_argv(spec: RunSpec, *, trace_path: Path) -> list[str]:
    """把一次性运行的请求拼成完整的子进程命令行。"""
    argv = _base_argv(spec, trace_path=trace_path)
    # `--` 之后的一切都被 argparse 当成位置参数。以 `--` 开头的任务文本
    # （"--help 这个选项坏了"）才不会被解析成选项。
    argv += ["--", spec.task]
    return argv


def build_conversation_argv(spec: RunSpec, *, trace_path: Path) -> list[str]:
    """把一次多轮对话的请求拼成命令行。

    与 ``build_argv`` 的唯一区别是**没有位置参数任务**，改成 ``--conversation-stdin``：
    任务逐轮从 stdin 送进去，子进程用同一个 agent 跑完全部轮次。
    """
    return [*_base_argv(spec, trace_path=trace_path), "--conversation-stdin"]


def _child_env() -> dict[str, str]:
    """子进程的环境变量：让它按 UTF-8 写 stdout / stderr。

    ``read_output`` 按 UTF-8 解码，而 Windows 上子解释器写管道默认用 ANSI 代码页——
    最常见的失败（缺 API key、参数无效）的中文报错到了控制台里就是一串乱码。
    用户已显式设置时尊重其取值。
    """
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


class RunProcess:
    """一个在跑的 ``dm-agent`` 子进程。"""

    def __init__(self, argv: list[str], *, cwd: Path, trace_path: Path) -> None:
        self.argv = argv
        self.cwd = cwd
        self.trace_path = trace_path
        self._process: subprocess.Popen[bytes] | None = None
        self._tree: ProcessTree | None = None
        self._output = bytearray()
        self._output_lock = threading.Lock()
        self._output_thread: threading.Thread | None = None

    def start(self, *, stdin_pipe: bool = False) -> None:
        """拉起子进程。

        ``stdin_pipe=True`` 给对话模式用：子进程会一直活着等下一轮任务从 stdin 进来，
        因此 stdin 必须是管道而不是 DEVNULL（DEVNULL 会让它立刻读到 EOF 然后退出）。
        """
        # argv 全部由白名单拼装、shell=False，任务文本作为单个元素传入（见模块 docstring）。
        self._tree = ProcessTree(
            self.argv,
            cwd=str(self.cwd),
            env=_child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
            shell=False,
        )
        self._process = self._tree.process
        self._output_thread = threading.Thread(target=self._drain_output, daemon=True)
        self._output_thread.start()

    def _drain_output(self) -> None:
        """持续排空输出管道，避免详细 CLI 输出填满管道后卡住 agent。"""
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            # BufferedReader.read(n) 会等满 n 字节或 EOF；直接读管道才能及时收到少量输出。
            while chunk := os.read(process.stdout.fileno(), 8192):
                with self._output_lock:
                    self._output.extend(chunk)
                    del self._output[:-MAX_OUTPUT_BYTES]
        except (OSError, ValueError):
            pass
        finally:
            process.stdout.close()

    def send_line(self, payload: dict[str, Any]) -> bool:
        """往子进程 stdin 写一行 JSON。写不进去（进程已死 / 管道已关）返回 False。

        必须显式 ``flush()``：管道是块缓冲的，不刷的话这一轮任务会一直卡在缓冲区里，
        子进程根本收不到。
        """
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return False
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            process.stdin.write(line.encode("utf-8"))
            process.stdin.flush()
        except (OSError, ValueError):
            return False
        return True

    def close_stdin(self) -> None:
        """关掉 stdin，让对话子进程读到 EOF 后自己优雅退出。"""
        process = self._process
        if process is None or process.stdin is None:
            return
        with contextlib.suppress(OSError, ValueError):
            process.stdin.close()

    def wait(self, timeout: float) -> int | None:
        """等子进程退出；超时返回 None。"""
        process = self._process
        if process is None:
            return None
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    @property
    def pid(self) -> int:
        return self._process.pid if self._process else -1

    def poll(self) -> int | None:
        """还在跑返回 None，结束了返回退出码。"""
        return self._process.poll() if self._process else None

    def stop(self, *, grace_seconds: float = 3.0) -> bool:
        """Release the owned tree even if its root already exited."""
        if self._tree is None:
            return False
        was_running = self._process is not None and self._process.poll() is None
        self._tree.stop(grace_seconds=grace_seconds)
        self.close_stdin()
        if self._output_thread is not None:
            self._output_thread.join(timeout=5)
        return was_running

    def shutdown(self, *, grace_seconds: float = 5.0) -> bool:
        """优雅结束一个对话子进程：先关 stdin 让它自己收尾，超时才动粗。

        比直接 ``stop()`` 好在于：agent 有机会写完最后一条 ``conversation_end``、
        并把 MCP 服务器正常关掉。
        """
        process = self._process
        if process is None:
            return False
        if process.poll() is not None:
            return self.stop(grace_seconds=0)
        self.close_stdin()
        if self.wait(grace_seconds) is not None:
            self.stop(grace_seconds=0)
            return True
        return self.stop()

    def read_output(self, limit: int = 8000) -> str:
        """取 stdout/stderr 的有限尾部，用于展示失败原因。"""
        if self._output_thread is not None and self.poll() is not None:
            self._output_thread.join(timeout=1.0)
        with self._output_lock:
            data = bytes(self._output)
        text = data.decode("utf-8", errors="replace")
        return text[-limit:] if len(text) > limit else text
