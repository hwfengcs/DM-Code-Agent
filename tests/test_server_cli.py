"""``dm-agent-web`` 入口的行为测试。

这一层不需要 fastapi：参数校验、token 生成、横幅打印全部发生在起 uvicorn 之前，
所以只测到 ``uvicorn.run`` 之前的那段，不真的开端口。唯一走到 ``uvicorn.run`` 的用例
把它换成了桩，缺 ``[web]`` extra 时自行跳过。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dm_agent.server.cli import _print_banner, build_parser, main
from dm_agent.server.settings import ServerSettings


def test_defaults_are_the_conservative_ones() -> None:
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.read_only is False
    assert args.no_token is False
    # 默认不给固定 token —— main() 会生成一个一次性的。
    assert args.token == ""


def test_no_token_is_rejected_on_non_loopback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--no-token", "--host", "0.0.0.0"]) == 2
    assert "loopback" in capsys.readouterr().err


def test_no_token_conflicts_with_token(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--no-token", "--token", "abc"]) == 2
    assert "互斥" in capsys.readouterr().err


def test_non_loopback_without_token_fails_before_binding(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """非 loopback + 无 token 必须在构造配置时就失败，而不是先把端口开出去。

    这里给 --token 传空串，main() 会自动生成一个，所以要真正触发这条路径得让
    generate_token 返回空。这模拟的是「有人把 fail closed 那道检查改坏了」。
    """
    monkeypatch.setattr("dm_agent.server.cli.generate_token", lambda: "")
    assert main(["--host", "203.0.113.5"]) == 2
    assert "token" in capsys.readouterr().err


def test_banner_prints_the_clickable_url(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """横幅里必须有那条带 token 的地址——它是用户唯一的入口。"""
    settings = ServerSettings(sessions_dir=tmp_path, port=9123, token="tok-xyz", read_only=True)
    _print_banner(settings)
    out = capsys.readouterr().out
    assert "http://127.0.0.1:9123/?token=tok-xyz" in out
    assert "只读展厅" in out
    # 只读模式不该出现「会真实读写文件」这句警告。
    assert "真实读写文件" not in out


def test_banner_warns_about_write_access_when_not_read_only(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    settings = ServerSettings(sessions_dir=tmp_path, token="t", read_only=False)
    _print_banner(settings)
    out = capsys.readouterr().out
    assert "完整工作台" in out
    assert "真实读写文件" in out
    assert str(settings.workspace) in out


def test_banner_flags_missing_token(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    _print_banner(ServerSettings(sessions_dir=tmp_path, token=""))
    assert "未启用 token" in capsys.readouterr().out


def test_server_is_started_with_a_bounded_shutdown_and_no_access_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """对话页开着 SSE 流时按 Ctrl+C，也必须能走到关停清理。

    SSE 流要等子进程退出才结束，子进程要等 lifespan 关停才被收掉；uvicorn 默认先无限期
    等连接关闭，于是两边互相等，agent 子进程成了孤儿。等待必须有上限。

    访问日志必须关：SSE 的 token 在查询参数里，访问日志会把它原样打出来。
    """
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    captured: dict[str, object] = {}

    def fake_run(_app: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    # main() 会把 ./.env 读进 os.environ，测试里不该碰调用目录的任何文件。
    monkeypatch.setattr("dm_agent.paths.load_env_files", lambda: [])
    monkeypatch.chdir(tmp_path)

    sessions = tmp_path / "sessions"
    assert (
        main(["--sessions-dir", str(sessions), "--workspace", str(tmp_path), "--token", "t"]) == 0
    )

    timeout = captured["timeout_graceful_shutdown"]
    assert isinstance(timeout, (int, float)) and 0 < timeout <= 10
    assert captured["access_log"] is False
