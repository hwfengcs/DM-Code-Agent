"""``is_failure_observation`` 的分层判定。

回归背景：早期实现对整条观察全文扫描 ``FAILURE_MARKERS``，于是工具**搬运**来的内容
（文件正文、子进程 stdout）里只要出现 "error" 就把一次成功的调用判成失败，白烧一次
重规划。实测一轮 30 题 benchmark 里 84 条失败观察中有 38 条是这样来的。

下面的用例按"自述 vs 搬运"这条线组织：搬运来的内容不参与判定，工具自己写的状态才算数。
"""

from __future__ import annotations

from dm_agent.core.observation import _STRUCTURED_OUTPUT_TOOLS, is_failure_observation
from dm_agent.tools import _builtin_tools

# --- 搬运来的内容不算失败（这批就是当初的误报） ---


def test_read_file_content_mentioning_error_is_not_a_failure() -> None:
    observation = (
        "from errors import ServiceError\n"
        "from storage import StorageError\n"
        "\n"
        "def fetch(storage, key):\n"
        '    """Read a key and translate storage failures to the public contract."""\n'
    )
    assert not is_failure_observation(observation, action="read_file")


def test_edit_file_echo_carrying_error_identifiers_is_not_a_failure() -> None:
    observation = (
        "已按内容替换 service.py 的 1 处（278 -> 375 字符）。\n"
        "[编辑后] 第 1-12 行（共 12 行）：\n"
        ">    1 | from errors import NotFound, Unavailable\n"
        ">    2 | from storage import StorageError\n"
    )
    assert not is_failure_observation(observation, action="edit_file")


def test_directory_listing_containing_errors_py_is_not_a_failure() -> None:
    assert not is_failure_observation(
        "errors.py\nservice.py\nstorage.py\ntests/", action="list_directory"
    )


def test_successful_script_printing_the_word_error_is_not_a_failure() -> None:
    # 探测脚本自己打印的预期输出：退出码 0 才是权威信号。
    observation = (
        "2024-01-31 + 1 ERROR: ValueError day is out of range for month\n"
        "2024-01-15 + 1: 2024-02-14\n"
        "returncode: 0"
    )
    assert not is_failure_observation(observation, action="run_python")


def test_test_source_named_after_errors_is_not_a_failure() -> None:
    observation = (
        "from retry import should_retry\n"
        "\n"
        "def test_retries_server_errors():\n"
        "    assert should_retry(status_code=503, attempt=1, max_attempts=3) is True\n"
    )
    assert not is_failure_observation(observation, action="read_file")


# --- 工具自述的状态仍然算失败 ---


def test_nonzero_returncode_is_a_failure() -> None:
    assert is_failure_observation("stderr:\nboom\nreturncode: 1", action="run_python")


def test_returncode_other_than_one_is_a_failure() -> None:
    # 旧实现只认字面量 "returncode: 1"，returncode 255 靠子串巧合才命中。
    assert is_failure_observation(
        "stderr:\n系统找不到指定的路径。\nreturncode: 255", action="run_shell"
    )


def test_reading_a_directory_as_a_file_is_a_failure() -> None:
    # 旧实现漏判："不是文件" 不在 FAILURE_MARKERS 里。
    assert is_failure_observation("路径 tests 不是文件。", action="read_file")


def test_missing_file_is_a_failure() -> None:
    assert is_failure_observation("文件 test_filenames.py 不存在。", action="read_file")


def test_line_range_out_of_bounds_is_a_failure() -> None:
    assert is_failure_observation("行号范围 10-20 超出文件范围（共 5 行）。", action="edit_file")


def test_kernel_failure_prefix_is_a_failure() -> None:
    assert is_failure_observation("Tool execution failed: boom", action="edit_file")
    assert is_failure_observation(
        "Tool arguments missing: action_input is null.", action="read_file"
    )


def test_syntax_check_failure_survives_a_successful_write() -> None:
    # 文件落盘了但语法是坏的（"只报告不回滚"），仍须重规划。
    observation = (
        "已将 120 个字符写入 mod.py。\n"
        "[语法检查] 未通过：第 3 行 invalid syntax。文件已写入，请修正后再继续。"
    )
    assert is_failure_observation(observation, action="create_file")


def test_returncode_inside_read_source_does_not_flip_the_verdict() -> None:
    # 被读取的测试代码里提到 returncode，不该被当成本次调用的退出码。
    observation = "def test_exit():\n    assert result.returncode == 1\n"
    assert not is_failure_observation(observation, action="read_file")


# --- 兼容性：未知来源仍走全文扫描 ---


def test_unknown_tool_falls_back_to_full_text_scan() -> None:
    assert is_failure_observation("Error: third party tool broke", action="some_extension_tool")


def test_omitted_action_preserves_legacy_behaviour() -> None:
    assert is_failure_observation("from errors import X")


def test_structured_tool_list_covers_every_builtin_tool() -> None:
    """新增内置工具时必须确认其输出格式符合契约，再加进精确判定清单。"""
    builtin = {tool.name for tool in _builtin_tools()}
    assert builtin == set(_STRUCTURED_OUTPUT_TOOLS), (
        "内置工具与 _STRUCTURED_OUTPUT_TOOLS 不一致；"
        "请确认新工具的失败自述符合 _TOOL_REFUSAL_RE / returncode 契约后再登记。"
    )
