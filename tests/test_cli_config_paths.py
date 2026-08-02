"""配置文件与 ``.env`` 的落点解析。

这些测试存在的唯一理由是 **pip 全局安装**：在 editable 安装下，「相对包位置算路径」
和「相对工作目录算路径」恰好重合，所以下面每一条断言在修复前都是「碰巧通过」的。
真正的回归守卫是 ``test_config_paths_never_land_inside_the_package``——
它直接钉死「配置不许写进 site-packages」这条。

``conftest.py`` 的 ``isolate_user_home`` 已经把 ``~`` 指向 tmp，但这里仍然显式传
``home_dir`` / ``cwd``：路径解析函数的可注入性本身就是被测行为之一。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dm_agent import paths
from dm_agent.cli.config import Config, load_config_from_file, save_config_to_file


def test_user_config_lives_under_the_shared_dm_agent_dir(tmp_path: Path) -> None:
    """用户级配置与扩展目录、信任文件同一个家。"""
    assert paths.user_config_path(tmp_path) == tmp_path / ".dm_agent" / "config.json"
    assert paths.user_env_path(tmp_path) == tmp_path / ".dm_agent" / ".env"
    assert paths.user_data_dir(tmp_path) == tmp_path / ".dm_agent"


def test_project_config_is_relative_to_cwd_not_the_package(tmp_path: Path) -> None:
    """项目级配置跟着**工作目录**走。"""
    assert paths.project_config_path(tmp_path) == tmp_path / "config.json"


def test_project_config_wins_over_user_config(tmp_path: Path) -> None:
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    (project / "config.json").write_text("{}", encoding="utf-8")
    (home / ".dm_agent").mkdir(parents=True)
    (home / ".dm_agent" / "config.json").write_text("{}", encoding="utf-8")

    assert paths.resolve_config_read_path(cwd=project, home_dir=home) == project / "config.json"


def test_user_config_is_the_fallback(tmp_path: Path) -> None:
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    (home / ".dm_agent").mkdir(parents=True)
    user_config = home / ".dm_agent" / "config.json"
    user_config.write_text("{}", encoding="utf-8")

    assert paths.resolve_config_read_path(cwd=project, home_dir=home) == user_config


def test_no_config_anywhere_reads_as_none(tmp_path: Path) -> None:
    """都没有时返回 None，由调用方用硬编码默认值。"""
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    home.mkdir()
    assert paths.resolve_config_read_path(cwd=project, home_dir=home) is None


def test_writes_go_back_to_whichever_file_was_read(tmp_path: Path) -> None:
    """写回来源——否则用户会遇到「我明明改了却没生效」。"""
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    (project / "config.json").write_text("{}", encoding="utf-8")

    assert paths.resolve_config_write_path(cwd=project, home_dir=home) == project / "config.json"


def test_writes_fall_back_to_user_level_when_nothing_exists(tmp_path: Path) -> None:
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    home.mkdir()

    write_path = paths.resolve_config_write_path(cwd=project, home_dir=home)
    assert write_path == home / ".dm_agent" / "config.json"


def test_config_paths_never_land_inside_the_package(tmp_path: Path) -> None:
    """**回归守卫**：配置绝不能落在包安装目录里。

    修复前 ``CONFIG_FILE`` 是 ``Path(__file__).parents[2]``，全局安装后等于
    ``site-packages/``——污染别人的 site-packages，系统 Python 下还可能直接
    权限失败。这条断言在 editable 安装下同样有意义：它比对的是包目录，
    而包目录此刻正好在仓库里。
    """
    package_dir = Path(paths.__file__).resolve().parent

    for candidate in (
        paths.user_config_path(tmp_path),
        paths.project_config_path(tmp_path),
        paths.resolve_config_write_path(cwd=tmp_path, home_dir=tmp_path),
        paths.user_env_path(tmp_path),
    ):
        assert package_dir not in candidate.resolve().parents


def test_save_then_load_round_trips_through_the_user_level_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端到端：干净目录里保存 → 落用户级 → 再读回来。"""
    workdir, home = tmp_path / "work", tmp_path / "home"
    workdir.mkdir()
    home.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    save_config_to_file(Config(api_key="", provider="openai", model="gpt-5", max_steps=42))

    written = home / ".dm_agent" / "config.json"
    assert written.is_file()
    assert not (workdir / "config.json").exists()

    loaded = load_config_from_file()
    assert loaded["provider"] == "openai"
    assert loaded["max_steps"] == 42
    # API key 只从环境变量读，永远不该被写进配置文件。
    assert "api_key" not in loaded


def test_save_creates_the_user_dir_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首次运行时 ``~/.dm_agent`` 还不存在，保存不能因此失败。"""
    workdir, home = tmp_path / "work", tmp_path / "home"
    workdir.mkdir()
    home.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert not (home / ".dm_agent").exists()

    save_config_to_file(Config(api_key=""))

    assert (home / ".dm_agent" / "config.json").is_file()


def test_corrupt_config_degrades_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """坏配置只告警不抛异常——不能让一个手抖的逗号挡住整个 CLI。"""
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "config.json").write_text("{not json,", encoding="utf-8")
    monkeypatch.chdir(workdir)

    assert load_config_from_file() == {}


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.json"
    paths.atomic_write_json(target, {"provider": "deepseek"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"provider": "deepseek"}
    assert [item.name for item in target.parent.iterdir()] == ["config.json"]


def test_env_files_load_project_first_then_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """项目级 ``.env`` 压过用户级；两个文件里的不同变量都要生效。"""
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    (home / ".dm_agent").mkdir(parents=True)
    (project / ".env").write_text(
        "DM_TEST_SHARED=project\nDM_TEST_ONLY_PROJECT=1\n", encoding="utf-8"
    )
    (home / ".dm_agent" / ".env").write_text(
        "DM_TEST_SHARED=user\nDM_TEST_ONLY_USER=1\n", encoding="utf-8"
    )
    for name in ("DM_TEST_SHARED", "DM_TEST_ONLY_PROJECT", "DM_TEST_ONLY_USER"):
        monkeypatch.delenv(name, raising=False)

    loaded = paths.load_env_files(cwd=project, home_dir=home)

    assert loaded == [project / ".env", home / ".dm_agent" / ".env"]
    import os

    assert os.environ["DM_TEST_SHARED"] == "project"
    assert os.environ["DM_TEST_ONLY_PROJECT"] == "1"
    assert os.environ["DM_TEST_ONLY_USER"] == "1"


def test_existing_env_vars_are_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式导出的环境变量始终最高优先级。

    ``conftest.py`` 的 ``block_real_api_keys`` 正是靠这条语义保证测试不会花钱。
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("DM_TEST_PRESET=from_file\n", encoding="utf-8")
    monkeypatch.setenv("DM_TEST_PRESET", "from_environment")

    paths.load_env_files(cwd=project, home_dir=tmp_path / "home")

    import os

    assert os.environ["DM_TEST_PRESET"] == "from_environment"


def test_missing_env_files_are_not_an_error(tmp_path: Path) -> None:
    assert paths.load_env_files(cwd=tmp_path / "nope", home_dir=tmp_path / "also-nope") == []


def test_env_file_with_utf8_bom_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """带 BOM 的 ``.env`` 必须照样生效——这是 Windows 上最容易踩的一脚。

    PowerShell 的 ``Set-Content -Encoding utf8``、``>`` 重定向和记事本的「UTF-8」
    另存全都写 BOM，而 dotenv 默认按 utf-8 读，会把 BOM 并进第一个键名
    （``\\ufeffDEEPSEEK_API_KEY``）。症状是 key 明明配了却报「缺少 API key」，
    用户基本不可能自己诊断出来，所以按 utf-8-sig 读。
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_bytes(b"\xef\xbb\xbfDM_TEST_BOM=survived\n")
    monkeypatch.delenv("DM_TEST_BOM", raising=False)

    paths.load_env_files(cwd=project, home_dir=tmp_path / "home")

    import os

    assert os.environ["DM_TEST_BOM"] == "survived"
    assert not [key for key in os.environ if key.startswith("﻿")]
