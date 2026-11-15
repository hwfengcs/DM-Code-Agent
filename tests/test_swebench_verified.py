from __future__ import annotations

import builtins
import json
import os
import subprocess
import tarfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar

import pytest

from dm_agent.core import ReactAgent
from dm_agent.core.capabilities import CapabilityContext
from dm_agent.core.events import (
    AfterToolResultEvent,
    BeforeToolCallEvent,
    EventBus,
    RunStartEvent,
)
from dm_agent.tools.base import Tool
from dm_agent.tools.file_tools import create_file, edit_file, read_file
from dm_agent.tracing import TraceWriter, load_trace_events
from swebench_verified import evaluate, predict
from swebench_verified.progress_guard import SWEProgressLoopGuard


class _FakeAgent:
    result: dict[str, Any] | Exception
    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, *_args: Any, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs

    def run(self, _prompt: str) -> dict[str, Any]:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _instance() -> dict[str, Any]:
    return {
        "instance_id": "owner__repo-1",
        "repo": "owner/repo",
        "base_commit": "abc123",
        "problem_statement": "fix it",
        "difficulty": "easy",
    }


def _prepare_predict(monkeypatch, tmp_path: Path, result: dict[str, Any] | Exception) -> Path:
    workspace_root = tmp_path / "workspaces"

    def materialize(_instance_id: str, destination: Path) -> Path:
        destination.mkdir(parents=True)
        return destination

    _FakeAgent.result = result
    monkeypatch.setattr(predict, "materialize_workspace", materialize)
    monkeypatch.setattr(predict, "build_client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(predict, "ReactAgent", _FakeAgent)
    monkeypatch.setattr(predict, "default_tools", lambda **_kwargs: [])
    monkeypatch.setattr(predict, "extract_patch", lambda _workspace: "diff --git a/a b/a\n")
    return workspace_root


def test_extract_workspace_archive_materializes_symlinks_as_git_link_text(tmp_path):
    archive_path = tmp_path / "workspace.tar"
    regular = b"image bytes"
    with tarfile.open(archive_path, "w") as archive:
        directory = tarfile.TarInfo("docs/static")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        file_info = tarfile.TarInfo("docs/static/icon.png")
        file_info.size = len(regular)
        archive.addfile(file_info, BytesIO(regular))
        link_info = tarfile.TarInfo("docs/theme/icon.png")
        link_info.type = tarfile.SYMTYPE
        link_info.linkname = "../static/icon.png"
        archive.addfile(link_info)

    destination = tmp_path / "workspace"
    predict._extract_workspace_archive(archive_path, destination, windows_semantics=True)

    assert (destination / "docs/static/icon.png").read_bytes() == regular
    link = destination / "docs/theme/icon.png"
    assert link.is_file()
    assert not link.is_symlink()
    assert link.read_bytes() == b"../static/icon.png"


@pytest.mark.skipif(os.name == "nt", reason="Windows CI may not permit native symlink creation")
def test_extract_workspace_archive_preserves_native_symlink_and_mode(tmp_path):
    archive_path = tmp_path / "workspace.tar"
    payload = b"#!/bin/sh\n"
    with tarfile.open(archive_path, "w") as archive:
        file_info = tarfile.TarInfo("bin/tool")
        file_info.mode = 0o755
        file_info.size = len(payload)
        archive.addfile(file_info, BytesIO(payload))
        link_info = tarfile.TarInfo("tool-link")
        link_info.type = tarfile.SYMTYPE
        link_info.linkname = "bin/tool"
        archive.addfile(link_info)

    destination = tmp_path / "workspace"
    predict._extract_workspace_archive(archive_path, destination, windows_semantics=False)

    assert (destination / "tool-link").is_symlink()
    assert (destination / "tool-link").read_bytes() == payload
    assert (destination / "bin/tool").stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize(
    "member_name",
    ["../outside.txt", "..\\outside.txt", "/outside.txt", "C:/outside.txt", "docs/a:b.txt"],
)
def test_extract_workspace_archive_rejects_path_traversal(tmp_path, member_name):
    archive_path = tmp_path / "unsafe.tar"
    payload = b"outside"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(payload)
        archive.addfile(member, BytesIO(payload))

    with pytest.raises(RuntimeError, match="不安全路径"):
        predict._extract_workspace_archive(
            archive_path, tmp_path / "workspace", windows_semantics=True
        )

    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.skipif(os.name == "nt", reason="':' is a legal file name character only on POSIX")
def test_extract_workspace_archive_keeps_colon_names_under_posix_semantics(tmp_path):
    archive_path = tmp_path / "workspace.tar"
    payload = b"data"
    with tarfile.open(archive_path, "w") as archive:
        file_info = tarfile.TarInfo("docs/a:b.txt")
        file_info.size = len(payload)
        archive.addfile(file_info, BytesIO(payload))
        link_info = tarfile.TarInfo("docs/latest")
        link_info.type = tarfile.SYMTYPE
        link_info.linkname = "a:b.txt"
        archive.addfile(link_info)

    destination = tmp_path / "workspace"
    predict._extract_workspace_archive(archive_path, destination, windows_semantics=False)

    assert (destination / "docs/a:b.txt").read_bytes() == payload
    assert (destination / "docs/latest").is_symlink()
    assert (destination / "docs/latest").read_bytes() == payload


@pytest.mark.parametrize("member_name", ["CON", "docs/NUL.txt", "name. "])
def test_extract_workspace_archive_rejects_windows_incompatible_paths(tmp_path, member_name):
    archive_path = tmp_path / "unsafe.tar"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo(member_name)
        archive.addfile(member, BytesIO())

    with pytest.raises(RuntimeError, match="Windows 不兼容路径"):
        predict._extract_workspace_archive(
            archive_path, tmp_path / "workspace", windows_semantics=True
        )


def test_extract_workspace_archive_rejects_duplicate_windows_targets(tmp_path):
    archive_path = tmp_path / "duplicate.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name in ("README.md", "readme.md"):
            member = tarfile.TarInfo(name)
            archive.addfile(member, BytesIO())

    with pytest.raises(RuntimeError, match="重复目标"):
        predict._extract_workspace_archive(
            archive_path, tmp_path / "workspace", windows_semantics=True
        )


def test_copy_workspace_from_container_cleans_temp_tar_on_launch_error(monkeypatch, tmp_path):
    destination = tmp_path / "workspace"

    def fail_run(*_args, **_kwargs):
        raise FileNotFoundError("docker missing")

    monkeypatch.setattr(predict.subprocess, "run", fail_run)

    with pytest.raises(FileNotFoundError, match="docker missing"):
        predict._copy_workspace_from_container("container", destination)

    assert list(tmp_path.glob(".workspace-*.tar")) == []
    assert not destination.exists()


def test_copy_workspace_from_container_streams_tar_and_cleans_temp(monkeypatch, tmp_path):
    destination = tmp_path / "workspace"
    payload = b"content"
    tar_path = tmp_path / "source.tar"
    with tarfile.open(tar_path, "w") as archive:
        member = tarfile.TarInfo("file.txt")
        member.size = len(payload)
        archive.addfile(member, BytesIO(payload))
    tar_bytes = tar_path.read_bytes()

    def copy_run(command, *, stdout, stderr):
        assert command == ["docker", "cp", "container:/testbed/.", "-"]
        assert stderr == subprocess.PIPE
        stdout.write(tar_bytes)
        return subprocess.CompletedProcess(command, 0, stderr=b"")

    monkeypatch.setattr(predict.subprocess, "run", copy_run)
    predict._copy_workspace_from_container("container", destination)

    assert (destination / "file.txt").read_bytes() == payload
    assert list(tmp_path.glob(".workspace-*.tar")) == []


def test_ensure_image_retries_timed_out_pulls(monkeypatch):
    calls = 0

    def run(command, **kwargs):
        nonlocal calls
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")
        calls += 1
        assert kwargs["timeout"] == predict.IMAGE_PULL_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(predict, "_run", run)
    monkeypatch.setattr(predict.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="超过 3600 秒"):
        predict.ensure_image("owner__repo-1", quiet=True)

    assert calls == 3


def test_docker_preflight_reports_a_missing_docker_binary(monkeypatch):
    def missing_binary(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", "docker")

    monkeypatch.setattr(predict, "_run", missing_binary)

    assert predict.docker_preflight().startswith("无法执行 docker 命令")


def _stub_git_for_extract_patch(monkeypatch, *, returncode: int, stdout: bytes, stderr: bytes):
    """让 extract_patch 不碰真实 git：add 走文本模式的 _run，diff 必须走字节模式。"""
    diff_calls: list[tuple[list[str], dict[str, Any]]] = []

    def run_add(command, **_kwargs):
        assert command == ["git", "add", "-A"]
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def run_diff(command, **kwargs):
        diff_calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(predict, "_assert_git_root", lambda *_args: None)
    monkeypatch.setattr(predict, "_run", run_add)
    monkeypatch.setattr(predict.subprocess, "run", run_diff)
    return diff_calls


def test_extract_patch_reads_the_diff_as_bytes_with_a_pinned_format(monkeypatch, tmp_path):
    """文本模式的通用换行会吃掉 patch 里的 CR；输出格式也不能随用户的全局 git 配置变化。"""
    raw = (
        b"diff --git a/win.py b/win.py\n"
        b"--- a/win.py\n"
        b"+++ b/win.py\n"
        b"@@ -1,2 +1,3 @@\n"
        b" keep = 1\r\n"
        b"-value = 1\r\n"
        b"+value = 2\r\n"
        b"+bar = 'pro\rgress'\n"
    )
    diff_calls = _stub_git_for_extract_patch(monkeypatch, returncode=0, stdout=raw, stderr=b"")

    patch = predict.extract_patch(tmp_path)

    assert patch.encode("utf-8") == raw
    assert diff_calls == [
        (
            [
                "git",
                "diff",
                "--cached",
                "--binary",
                "--no-color",
                "--no-ext-diff",
                "--no-textconv",
                "--src-prefix=a/",
                "--dst-prefix=b/",
            ],
            {"cwd": str(tmp_path), "capture_output": True},
        )
    ]


def test_extract_patch_reports_a_failed_diff_with_readable_stderr(monkeypatch, tmp_path):
    _stub_git_for_extract_patch(
        monkeypatch, returncode=128, stdout=b"", stderr="fatal: 索引已损坏\n".encode()
    )

    with pytest.raises(RuntimeError, match="git diff 失败：fatal: 索引已损坏"):
        predict.extract_patch(tmp_path)


def test_extract_patch_can_be_applied_with_crlf_binary_and_custom_diff_settings(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "empty-git-config"))

    def git(*args, input=None):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, input=input, capture_output=True, check=True
        )

    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    git("config", "core.autocrlf", "false")
    (tmp_path / ".gitattributes").write_text("*.py diff=custom -text\n", encoding="utf-8")
    source = tmp_path / "win.py"
    source.write_bytes(b"value = 1\r\n")
    git("add", ".")
    git("commit", "-m", "baseline")
    git("config", "diff.custom.textconv", "git hash-object")
    git("config", "diff.noprefix", "true")
    git("config", "color.ui", "always")
    git("config", "diff.external", "unused-external-diff")
    updated = b"value = 2\r\n"
    binary = b"\x00\xff\x80binary\r\n"
    source.write_bytes(updated)
    (tmp_path / "data.bin").write_bytes(binary)

    patch = predict.extract_patch(tmp_path)
    git("reset", "--hard", "HEAD")
    git("apply", "--binary", "-", input=patch.encode("utf-8"))

    assert source.read_bytes() == updated
    assert (tmp_path / "data.bin").read_bytes() == binary


def test_build_client_names_the_unsupported_provider(monkeypatch):
    monkeypatch.setattr(predict, "load_env_files", lambda: [])

    with pytest.raises(RuntimeError) as excinfo:
        predict.build_client("deepseeek", None, 30)

    message = str(excinfo.value)
    assert "不支持的 provider：deepseeek" in message
    assert "deepseek、openai、claude、gemini" in message


def test_summarize_only_runs_without_evaluation_arguments(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "submitted_instances": 4,
                "completed_instances": 3,
                "resolved_instances": 1,
                "unresolved_instances": 2,
                "empty_patch_instances": 1,
                "error_instances": 0,
            }
        ),
        encoding="utf-8",
    )

    assert evaluate.main(["--summarize-only", str(report)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "submitted": 4,
        "completed": 3,
        "resolved": 1,
        "unresolved": 2,
        "empty_patch": 1,
        "error": 0,
        "resolve_rate": 0.25,
    }


def test_evaluation_still_requires_predictions_and_run_id(capsys):
    with pytest.raises(SystemExit) as excinfo:
        evaluate.main(["--run-id", "only-half-of-the-arguments"])

    assert excinfo.value.code == 2
    assert "--predictions" in capsys.readouterr().err


def test_force_lf_writes_uses_utf8_for_harness_text_outputs(tmp_path):
    original_write_text = Path.write_text
    original_open = builtins.open
    original_python_utf8 = os.environ.get("PYTHONUTF8")
    try:
        evaluate.force_lf_writes()
        script = tmp_path / "eval.sh"
        script.write_text("echo ë ০\r\necho two\r\n")
        output = tmp_path / "test_output.txt"
        with open(output, "w") as handle:
            handle.write("Unicode: ë ০")

        assert script.read_bytes() == "echo ë ০\necho two\n".encode()
        assert output.read_bytes() == "Unicode: ë ০".encode()
        with open(output) as handle:
            assert handle.read() == "Unicode: ë ০"
        assert os.environ["PYTHONUTF8"] == "1"
    finally:
        Path.write_text = original_write_text
        builtins.open = original_open
        if original_python_utf8 is None:
            os.environ.pop("PYTHONUTF8", None)
        else:
            os.environ["PYTHONUTF8"] = original_python_utf8


def test_predict_one_exports_empty_patch_diagnostics(monkeypatch, tmp_path):
    metadata = {
        "status": "max_steps",
        "replan_count": 2,
        "parse_error_count": 3,
        "parse_repair_count": 4,
        "parse_error_context_omitted_count": 5,
        "parse_error_context_omitted_chars": 600,
        "truncation_count": 7,
        "edit_guard_block_count": 8,
        "edit_noop_count": 9,
        "repeat_search_block_count": 10,
        "edit_state_revisit_count": 11,
        "edit_cycle_block_count": 12,
    }
    workspace_root = _prepare_predict(
        monkeypatch,
        tmp_path,
        {"metadata": metadata, "steps": [{}, {}]},
    )

    record = predict.predict_one(
        _instance(),
        workspace_root=workspace_root,
        provider="deepseek",
        model=None,
        max_steps=60,
        temperature=0.0,
        timeout=30,
        trace_dir=None,
        keep_workspace=True,
    )

    assert record["dm_diagnostics_version"] == 1
    assert record["dm_steps"] == 2
    assert record["dm_replans"] == 2
    assert record["dm_parse_errors"] == 3
    assert record["dm_parse_repairs"] == 4
    assert record["dm_parse_error_context_omitted_count"] == 5
    assert record["dm_parse_error_context_omitted_chars"] == 600
    assert record["dm_truncations"] == 7
    assert record["dm_edit_guard_blocks"] == 8
    assert record["dm_edit_noops"] == 9
    assert record["dm_repeat_search_blocks"] == 10
    assert record["dm_edit_state_revisits"] == 11
    assert record["dm_edit_cycle_blocks"] == 12
    capabilities = _FakeAgent.last_kwargs["capabilities"]
    assert len(capabilities) == 1
    assert isinstance(capabilities[0], SWEProgressLoopGuard)


def test_predict_one_marks_diagnostics_unmeasured_after_agent_exception(monkeypatch, tmp_path):
    workspace_root = _prepare_predict(monkeypatch, tmp_path, RuntimeError("boom"))

    record = predict.predict_one(
        _instance(),
        workspace_root=workspace_root,
        provider="deepseek",
        model=None,
        max_steps=60,
        temperature=0.0,
        timeout=30,
        trace_dir=None,
        keep_workspace=True,
    )

    assert record["dm_status"] == "agent_exception"
    assert record["dm_patch_chars"] > 0
    assert "dm_diagnostics_version" not in record
    assert "dm_parse_errors" not in record
    assert "dm_repeat_search_blocks" not in record
    assert "dm_edit_cycle_blocks" not in record


def test_materialize_workspace_refuses_existing_checkout(tmp_path, monkeypatch):
    workspace = tmp_path / "previous-checkout"
    workspace.mkdir()
    original = workspace / "work.py"
    original.write_text("unsaved changes", encoding="utf-8")
    monkeypatch.setattr(predict, "ensure_image", lambda _: pytest.fail("must refuse before Docker"))

    with pytest.raises(FileExistsError):
        predict.materialize_workspace("owner__repo-1", workspace)

    assert original.read_text(encoding="utf-8") == "unsaved changes"


@pytest.mark.parametrize("keep_workspace", [True, False])
def test_predictions_preserve_previous_workspaces(monkeypatch, tmp_path, keep_workspace):
    workspace_root = _prepare_predict(monkeypatch, tmp_path, {"metadata": {}, "steps": []})
    previous = workspace_root / _instance()["instance_id"]
    previous.mkdir(parents=True)
    original = previous / "work.py"
    original.write_text("previous attempt", encoding="utf-8")

    for _ in range(2):
        predict.predict_one(
            _instance(),
            workspace_root=workspace_root,
            provider="deepseek",
            model=None,
            max_steps=5,
            temperature=0.0,
            timeout=30,
            trace_dir=None,
            keep_workspace=keep_workspace,
        )

    assert original.read_text(encoding="utf-8") == "previous attempt"
    attempts = [path for path in workspace_root.iterdir() if path != previous]
    assert len(attempts) == (2 if keep_workspace else 0)


def test_workspace_cleanup_failure_does_not_discard_prediction(monkeypatch, tmp_path, capsys):
    workspace_root = _prepare_predict(monkeypatch, tmp_path, {"metadata": {}, "steps": []})

    def fail_cleanup(path):
        raise PermissionError("busy file")

    monkeypatch.setattr(predict, "_force_rmtree", fail_cleanup)

    record = predict.predict_one(
        _instance(),
        workspace_root=workspace_root,
        provider="deepseek",
        model=None,
        max_steps=5,
        temperature=0.0,
        timeout=30,
        trace_dir=None,
        keep_workspace=False,
    )

    assert record["model_patch"] == "diff --git a/a b/a\n"
    assert "busy file" in capsys.readouterr().err
    assert len(list(workspace_root.iterdir())) == 1


@pytest.mark.parametrize("failure_stage", [None, "client", "agent"])
def test_prediction_trace_is_closed_on_success_and_failure(monkeypatch, tmp_path, failure_stage):
    result = (
        RuntimeError("agent failed") if failure_stage == "agent" else {"metadata": {}, "steps": []}
    )
    workspace_root = _prepare_predict(monkeypatch, tmp_path, result)
    writers = []

    class RecordingWriter(TraceWriter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            writers.append(self)

    monkeypatch.setattr(predict, "TraceWriter", RecordingWriter)
    if failure_stage == "client":

        def fail_client(*args):
            raise ValueError("client failed")

        monkeypatch.setattr(predict, "build_client", fail_client)

    kwargs = dict(
        workspace_root=workspace_root,
        provider="deepseek",
        model=None,
        max_steps=5,
        temperature=0.0,
        timeout=30,
        trace_dir=tmp_path / "traces",
        keep_workspace=True,
    )
    if failure_stage == "client":
        with pytest.raises(ValueError, match="client failed"):
            predict.predict_one(_instance(), **kwargs)
    else:
        predict.predict_one(_instance(), **kwargs)

    assert len(writers) == 1
    assert writers[0]._handle is None


def _event_bus_with_progress_guard(trace_writer=None):
    bus = EventBus()
    guard = SWEProgressLoopGuard()
    guard.install(
        CapabilityContext(
            event_bus=bus,
            client_for=lambda _phase: None,
            trace_writer=trace_writer,
        )
    )
    return bus


def _run_guarded_write(
    bus: EventBus,
    metadata: dict[str, Any],
    *,
    tool_name: str,
    arguments: dict[str, Any],
    step_number: int,
    runner: Callable[[dict[str, Any]], str],
    content_anchor_safe: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    event = BeforeToolCallEvent(
        tool_name=tool_name,
        arguments=dict(arguments),
        step_number=step_number,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=content_anchor_safe,
    )
    block = bus.emit_before_tool_call(event)
    if block is not None:
        return block, None
    observation = runner(event.arguments)
    final_observation = bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=tool_name,
            arguments=event.arguments,
            observation=observation,
            step_number=step_number,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )
    return None, final_observation


def _seed_content_edit_revisit(bus: EventBus, metadata: dict[str, Any]) -> None:
    for step_number, old_string, new_string in [(1, "A", "B"), (2, "B", "A")]:
        block, _ = _run_guarded_write(
            bus,
            metadata,
            tool_name="edit_file",
            arguments={
                "path": "app.py",
                "old_string": old_string,
                "new_string": new_string,
            },
            step_number=step_number,
            runner=edit_file,
            content_anchor_safe=True,
        )
        assert block is None


def test_repeat_search_guard_replays_cache_and_invalidates_on_file_change(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir()
    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    trace_path = tmp_path / "repeat-search.jsonl"
    writer = TraceWriter(trace_path)
    bus = _event_bus_with_progress_guard(writer)
    metadata: dict[str, Any] = {}
    suffix = bus.emit_run_start(
        RunStartEvent(
            task="fix",
            attempt=1,
            run_id="run",
            prompt_suffix="existing suffix",
            metadata=metadata,
        )
    )
    arguments = {"path": "pkg/mod.py", "pattern": "def target"}

    first = BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 1, "run", metadata)
    assert bus.emit_before_tool_call(first) is None
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation="found at line 10",
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    repeated = BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
    block = bus.emit_before_tool_call(repeated)

    assert suffix == "existing suffix"
    assert block is not None and block["block"] is True
    assert "step 1" in block["reason"]
    assert "> found at line 10" in block["reason"]
    assert metadata["progress_loop_guard_enabled"] is True
    assert metadata["repeat_search_block_count"] == 1

    # 无论改写来自哪个工具，只要目标文件内容变化，同一搜索就重新放行。
    target.write_text("def target():\n    return 2\n", encoding="utf-8")
    assert (
        bus.emit_before_tool_call(
            BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 3, "run", metadata)
        )
        is None
    )
    writer.close()

    events = load_trace_events(trace_path)
    repeat_events = [event for event in events if event["event"] == "swebench_repeat_search_block"]
    assert len(repeat_events) == 1
    assert repeat_events[0]["payload"]["first_success_step"] == 1


def test_repeat_search_guard_replays_full_bounded_observation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("mod.py").write_text("target = 1\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    arguments = {"path": "mod.py", "pattern": "target"}
    observation = "x" * 2000 + "\nLATE_MATCH_EVIDENCE"
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation=observation,
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    block = bus.emit_before_tool_call(
        BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
    )

    assert block is not None
    assert "LATE_MATCH_EVIDENCE" in block["reason"]


def test_repeat_search_guard_does_not_cache_failed_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    arguments = {"path": "missing.py", "pattern": "target"}
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation="文件 missing.py 不存在。",
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    assert (
        bus.emit_before_tool_call(
            BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
        )
        is None
    )


def test_repeat_search_trace_failure_does_not_change_block_decision(tmp_path, monkeypatch):
    class BrokenTrace:
        def record(self, _event, _payload):
            raise OSError("disk unavailable")

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "mod.py"
    target.write_text("target = 1\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard(BrokenTrace())
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    arguments = {"path": "mod.py", "pattern": "target"}
    bus.emit_after_tool_result(
        AfterToolResultEvent(
            tool_name=_SEARCH_ACTION,
            arguments=dict(arguments),
            observation="found",
            step_number=1,
            run_id="run",
            tool_succeeded=True,
            metadata=metadata,
        )
    )

    block = bus.emit_before_tool_call(
        BeforeToolCallEvent(_SEARCH_ACTION, dict(arguments), 2, "run", metadata)
    )

    assert block is not None and block["block"] is True
    assert metadata["repeat_search_block_count"] == 1


def test_edit_cycle_prediction_requires_canonical_valid_content_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("A\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    _seed_content_edit_revisit(bus, metadata)

    create_with_extra_edit_keys = BeforeToolCallEvent(
        tool_name="create_file",
        arguments={
            "path": "app.py",
            "content": "C\n",
            "old_string": "A",
            "new_string": "B",
        },
        step_number=3,
        run_id="run",
        metadata=metadata,
    )
    conflicting_edit_modes = BeforeToolCallEvent(
        tool_name="edit_file",
        arguments={
            "path": "app.py",
            "old_string": "A",
            "new_string": "B",
            "operation": "replace",
            "line_start": 1,
            "line_end": 1,
            "content": "C",
        },
        step_number=4,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=True,
    )
    noncanonical_edit_tool = BeforeToolCallEvent(
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "A", "new_string": "B"},
        step_number=5,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=False,
    )

    assert bus.emit_before_tool_call(create_with_extra_edit_keys) is None
    assert bus.emit_before_tool_call(conflicting_edit_modes) is None
    assert bus.emit_before_tool_call(noncanonical_edit_tool) is None
    assert metadata["edit_cycle_block_count"] == 0


def test_edit_cycle_prediction_supports_omitted_new_string_deletion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("xy\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))

    first_block, _ = _run_guarded_write(
        bus,
        metadata,
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "y"},
        step_number=1,
        runner=edit_file,
        content_anchor_safe=True,
    )
    undo_block, undo_observation = _run_guarded_write(
        bus,
        metadata,
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "x", "new_string": "xy"},
        step_number=2,
        runner=edit_file,
        content_anchor_safe=True,
    )
    repeated_delete = BeforeToolCallEvent(
        tool_name="edit_file",
        arguments={"path": "app.py", "old_string": "y"},
        step_number=3,
        run_id="run",
        metadata=metadata,
        content_anchor_safe=True,
    )

    assert first_block is None
    assert undo_block is None
    assert undo_observation is not None
    assert "will be skipped before execution" in undo_observation
    block = bus.emit_before_tool_call(repeated_delete)
    assert block is not None and block["block"] is True
    assert Path("app.py").read_text(encoding="utf-8") == "xy\n"
    assert metadata["edit_cycle_block_count"] == 1


def test_line_number_edit_revisits_are_diagnostic_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("A\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))
    actions = [
        {"path": "app.py", "operation": "replace", "line_start": 1, "line_end": 1, "content": "B"},
        {"path": "app.py", "operation": "replace", "line_start": 1, "line_end": 1, "content": "A"},
        {"path": "app.py", "operation": "replace", "line_start": 1, "line_end": 1, "content": "B"},
    ]

    observations: list[str] = []
    for step_number, arguments in enumerate(actions, start=1):
        block, observation = _run_guarded_write(
            bus,
            metadata,
            tool_name="edit_file",
            arguments=arguments,
            step_number=step_number,
            runner=edit_file,
            content_anchor_safe=True,
        )
        assert block is None
        assert observation is not None
        observations.append(observation)

    assert "diagnostics only" in observations[1]
    assert "will be skipped" not in observations[1]
    assert metadata["edit_state_revisit_count"] == 2
    assert metadata["edit_cycle_block_count"] == 0


def test_create_file_revisits_are_diagnostic_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("A\n", encoding="utf-8")
    bus = _event_bus_with_progress_guard()
    metadata: dict[str, Any] = {}
    bus.emit_run_start(RunStartEvent(task="fix", attempt=1, run_id="run", metadata=metadata))

    observations: list[str] = []
    for step_number, content in enumerate(["B\n", "A\n", "B\n"], start=1):
        block, observation = _run_guarded_write(
            bus,
            metadata,
            tool_name="create_file",
            arguments={"path": "app.py", "content": content},
            step_number=step_number,
            runner=create_file,
        )
        assert block is None
        assert observation is not None
        observations.append(observation)

    assert "diagnostics only" in observations[1]
    assert "will be skipped" not in observations[1]
    assert metadata["edit_state_revisit_count"] == 2
    assert metadata["edit_cycle_block_count"] == 0


class _ScriptedClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def respond(self, _messages, **_extra):
        return self.responses.pop(0)


def _action(action: str, action_input: Any) -> str:
    return json.dumps(
        {"thought": "step", "action": action, "action_input": action_input},
        ensure_ascii=False,
    )


_SEARCH_ACTION = "search_in_file"


def test_progress_loop_guard_breaks_scripted_search_fixed_point(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir()
    target.write_text("target = 1\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []
    client = _ScriptedClient(
        [
            _action(_SEARCH_ACTION, {"path": "pkg/mod.py", "pattern": "target"}),
            _action(_SEARCH_ACTION, {"path": "pkg/mod.py", "pattern": "target"}),
            _action("finish", "done"),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool(
                _SEARCH_ACTION,
                "search",
                lambda arguments: calls.append(dict(arguments)) or "found",
            )
        ],
        enable_planning=False,
        enable_compression=False,
        capabilities=[SWEProgressLoopGuard()],
    )

    result = agent.run("fix", max_steps=3)

    assert len(calls) == 1
    assert result["metadata"]["repeat_search_block_count"] == 1
    assert result["steps"][1]["observation"].startswith("Skipped exact duplicate search #1")


def test_progress_loop_guard_allows_one_undo_then_blocks_edit_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_text("value = 1\n", encoding="utf-8")
    client = _ScriptedClient(
        [
            _action("read_file", {"path": "app.py"}),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 1", "new_string": "value = 2"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 2", "new_string": "value = 1"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 1", "new_string": "value = 2"},
            ),
            _action(
                "edit_file",
                {"path": "app.py", "old_string": "value = 1", "new_string": "value = 3"},
            ),
            _action("finish", "done"),
        ]
    )
    agent = ReactAgent(
        client,
        [
            Tool("read_file", "read", read_file),
            Tool("edit_file", "edit", edit_file),
        ],
        enable_planning=False,
        enable_compression=False,
        capabilities=[SWEProgressLoopGuard()],
    )

    result = agent.run("fix", max_steps=6)

    assert Path("app.py").read_text(encoding="utf-8") == "value = 3\n"
    assert result["metadata"]["edit_state_revisit_count"] == 1
    assert result["metadata"]["edit_cycle_block_count"] == 1
    assert "Edit-state revisit #1" in result["steps"][2]["observation"]
    assert result["steps"][3]["observation"].startswith("Skipped edit-state cycle #1")
