from __future__ import annotations

import json
from pathlib import Path

import pytest

from dm_agent.cli import parse_args
from dm_agent.extensions import (
    ExtensionDiscoveryError,
    ProjectTrustDecision,
    ProjectTrustStore,
    discover_extensions,
)


class FakeEntryPoint:
    def __init__(self, name: str, setup, value: str = "example:setup") -> None:
        self.name = name
        self.value = value
        self._setup = setup

    def load(self):
        return self._setup


def _write_tool_extension(path: Path, result: str, *, name: str = "priority_tool") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "from dm_agent.tools import Tool",
                "",
                "def setup(api):",
                f"    api.register_tool(Tool({name!r}, 'extension tool', lambda arguments: {result!r}))",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_discovery_loads_three_sources_and_applies_priority(monkeypatch, tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    explicit = tmp_path / "explicit.py"

    def entry_setup(api):
        from dm_agent.tools import Tool

        api.register_tool(Tool("priority_tool", "entry", lambda arguments: "entry"))

    monkeypatch.setattr(
        "dm_agent.extensions.discovery.metadata.entry_points",
        lambda **kwargs: [FakeEntryPoint("entry", entry_setup)],
    )
    _write_tool_extension(home / ".dm_agent" / "extensions" / "global.py", "global")
    _write_tool_extension(project / ".dm_agent" / "extensions" / "project.py", "project")
    _write_tool_extension(explicit, "explicit")

    result = discover_extensions(
        project_root=project,
        home_dir=home,
        explicit_paths=[explicit],
        trust_prompt=lambda path: ProjectTrustDecision.LOAD_ONCE,
    )

    tools = {tool.name: tool for tool in result.registry.get_tools()}
    assert "list_directory" in tools
    assert tools["priority_tool"].execute({}) == "explicit"
    assert len(result.loaded) == 5
    assert result.failures == []


def test_project_extension_is_not_imported_before_trust(monkeypatch, tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    marker = tmp_path / "executed.txt"
    extension = project / ".dm_agent" / "extensions" / "malicious.py"
    extension.parent.mkdir(parents=True)
    extension.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')",
                "def setup(api):",
                "    return None",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])

    result = discover_extensions(project_root=project, home_dir=home)

    assert not marker.exists()
    assert any("未获信任" in item for item in result.skipped)


def test_persistent_project_trust_and_denial(monkeypatch, tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    trust_path = tmp_path / "trust.json"
    _write_tool_extension(project / ".dm_agent" / "extensions" / "trusted.py", "trusted")
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])

    first = discover_extensions(
        project_root=project,
        home_dir=home,
        trust_store_path=trust_path,
        trust_prompt=lambda path: ProjectTrustDecision.TRUST,
    )
    second = discover_extensions(
        project_root=project,
        home_dir=home,
        trust_store_path=trust_path,
        trust_prompt=lambda path: pytest.fail("persisted trust should skip prompt"),
    )

    assert any(tool.name == "priority_tool" for tool in first.registry.get_tools())
    assert any(tool.name == "priority_tool" for tool in second.registry.get_tools())
    payload = json.loads(trust_path.read_text(encoding="utf-8"))
    assert list(payload["projects"].values()) == [True]

    ProjectTrustStore(trust_path).set(project, trusted=False)
    denied = discover_extensions(
        project_root=project,
        home_dir=home,
        trust_store_path=trust_path,
        trust_prompt=lambda path: pytest.fail("persisted denial should skip prompt"),
    )
    assert not any(tool.name == "priority_tool" for tool in denied.registry.get_tools())


def test_no_extensions_skips_external_discovery(monkeypatch, tmp_path):
    marker = tmp_path / "executed.txt"
    user_extension = tmp_path / "home" / ".dm_agent" / "extensions" / "user.py"
    user_extension.parent.mkdir(parents=True)
    user_extension.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\ndef setup(api): pass\n",
        encoding="utf-8",
    )

    def unexpected_entry_points(**kwargs):
        raise AssertionError("entry points must not be queried")

    monkeypatch.setattr(
        "dm_agent.extensions.discovery.metadata.entry_points", unexpected_entry_points
    )
    result = discover_extensions(
        project_root=tmp_path / "project",
        home_dir=tmp_path / "home",
        no_extensions=True,
    )

    assert result.loaded == ["builtin"]
    assert not marker.exists()
    assert [tool.name for tool in result.registry.get_tools()][-1] == "task_complete"


def test_explicit_extension_failure_is_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])
    invalid = tmp_path / "invalid.py"
    invalid.write_text("value = 1\n", encoding="utf-8")

    with pytest.raises(ExtensionDiscoveryError, match="显式扩展加载失败"):
        discover_extensions(
            project_root=tmp_path / "project",
            home_dir=tmp_path / "home",
            explicit_paths=[invalid],
        )


def test_cli_extension_flags(monkeypatch):
    monkeypatch.setattr("dm_agent.cli.args.load_config_from_file", lambda: {})

    disabled = parse_args(["task", "--no-extensions"])
    explicit = parse_args(["task", "--extension", "one.py", "--extension", "two.py"])

    assert disabled.no_extensions is True
    assert disabled.extension_paths == []
    assert explicit.no_extensions is False
    assert explicit.extension_paths == [Path("one.py"), Path("two.py")]

    with pytest.raises(SystemExit):
        parse_args(["task", "--no-extensions", "--extension", "one.py"])
